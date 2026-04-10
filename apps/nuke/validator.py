import nuke
import os
import re
import logging
from core import context
from core.env import get_project_config

logger = logging.getLogger("skyfall.validator")


class PublishValidator:
    """
    SKYFALL Strict Validator
    워크플로우(uhd/hd)에 따라 검증 기준이 달라집니다.
    """
    def __init__(self, write_node=None):
        self.node = write_node or nuke.thisNode()
        self.ctx = context.get_current()
        self.cfg = get_project_config(self.ctx.project) if self.ctx.project else {}
        self.workflow = self.cfg.get("workflow", "uhd")
        self.errors = []

    def validate_all(self) -> bool:
        self.errors = []

        # 1. Context
        if not self.ctx.is_valid:
            self.errors.append("Invalid Pipeline Context: Script is not saved in a correct shot folder.")
            return False

        # 2. Write node 'file' 노브 존재 확인
        if 'file' not in self.node.knobs():
            self.errors.append(f"Node '{self.node.name()}' has no 'file' knob. Is this a Write node?")
            return False

        node_name = self.node.name()

        # Write_REVIEW는 별도 검증
        if "REVIEW" in node_name:
            self.check_review_node()
        else:
            # Write_PUBLISH 또는 기타 Write
            self.check_resolution()
            self.check_naming()
            self.check_output_path_exists()
            self.check_frame_range()
            if self.workflow == "uhd":
                self.check_exr_format()
            else:
                self.check_mov_format()

        return len(self.errors) == 0

    def check_resolution(self):
        res_cfg = self.cfg.get("resolution", [1920, 1080])
        target_res = tuple(res_cfg) if isinstance(res_cfg, list) else (1920, 1080)
        actual_res = (self.node.width(), self.node.height())
        if actual_res != target_res:
            self.errors.append(
                f"Resolution Mismatch: Expected {target_res[0]}x{target_res[1]}, got {actual_res[0]}x{actual_res[1]}"
            )

    def check_naming(self):
        file_path = self.node['file'].value()
        file_name = os.path.basename(file_path)
        shot_code = self.ctx.shot_code

        # 파일명은 반드시 shot_code_<task>_v###. 형식
        pattern = rf"^{re.escape(shot_code)}_[a-zA-Z0-9]+_v\d{{3}}\."
        if not re.match(pattern, file_name):
            self.errors.append(
                f"Naming Error: File must match '{shot_code}_<task>_v###' "
                f"(got: '{file_name}')"
            )

        # 버전 폴더 필수: /v001/ ~ /v999/
        if not re.search(r"/v\d{3}/", file_path):
            self.errors.append(
                "Structure Error: Write path must include a version folder (e.g., .../render/v001/filename.exr)"
            )

    def check_output_path_exists(self):
        """렌더 출력 디렉토리가 실제로 존재하는지 확인합니다."""
        file_path = self.node['file'].value()
        out_dir = os.path.dirname(file_path)
        if not os.path.isdir(out_dir):
            self.errors.append(
                f"Output Directory Missing: '{out_dir}'\n"
                f"  Please create the version folder before rendering."
            )

    def check_frame_range(self):
        """Write 노드 렌더 범위를 검사합니다."""
        root = nuke.root()
        proj_first = int(root['first_frame'].value())
        proj_last = int(root['last_frame'].value())

        if self.node['use_limit'].value():
            first = int(self.node['first'].value())
            last = int(self.node['last'].value())
        else:
            first = proj_first
            last = proj_last

        if first != proj_first or last != proj_last:
            self.errors.append(
                f"Frame Range Mismatch: Write node renders {first}-{last}, "
                f"but project is {proj_first}-{proj_last}."
            )

    def check_exr_format(self):
        """UHD: EXR 포맷, 16-bit, 압축, 컬러스페이스 검사."""
        file_path = self.node['file'].value()
        clean_path = re.sub(r"(%\d+d|#+)", "0000", file_path)
        _, ext = os.path.splitext(clean_path)

        if ext.lower() != ".exr":
            self.errors.append(
                f"Format Error: UHD publish requires EXR (got '{ext}')."
            )
            return

        # 비트 뎁스 확인 (16-bit half 또는 32-bit float)
        if 'datatype' in self.node.knobs():
            datatype = self.node['datatype'].value()
            if "16" not in datatype and "32" not in datatype:
                self.errors.append(
                    f"Bit Depth Error: EXR must be 16-bit half or 32-bit float "
                    f"(got: '{datatype}')."
                )

        # 압축 방식
        if 'compression' in self.node.knobs():
            compression = self.node['compression'].value()
            expected = self.cfg.get("output_compressor", "zip1").lower()
            if expected not in compression.lower():
                self.errors.append(
                    f"Compression Error: Must use '{expected.upper()}' "
                    f"(got: '{compression}')."
                )

        # 출력 색공간
        self._check_colorspace("output_colorspace")

    def check_mov_format(self):
        """HD: MOV 포맷, 코덱, 컬러스페이스 검사."""
        file_path = self.node['file'].value()
        clean_path = re.sub(r"(%\d+d|#+)", "0000", file_path)
        _, ext = os.path.splitext(clean_path)

        if ext.lower() not in (".mov", ".mp4"):
            self.errors.append(
                f"Format Error: HD publish requires MOV (got '{ext}')."
            )
            return

        # 출력 색공간
        self._check_colorspace("output_colorspace")

    def check_review_node(self):
        """Write_REVIEW 노드 검증 (UHD/HD 공통)."""
        self.check_naming()
        self.check_output_path_exists()
        self.check_frame_range()

        # 리뷰 해상도 확인
        review_res = self.cfg.get("review_resolution", [1920, 1080])
        target_res = tuple(review_res) if isinstance(review_res, list) else (1920, 1080)
        actual_res = (self.node.width(), self.node.height())
        if actual_res != target_res:
            self.errors.append(
                f"Review Resolution Mismatch: Expected {target_res[0]}x{target_res[1]}, got {actual_res[0]}x{actual_res[1]}"
            )

    def _check_colorspace(self, config_key: str):
        """Write 노드의 colorspace를 project.yml 기준으로 검사합니다."""
        if 'colorspace' not in self.node.knobs():
            return
        cs = self.node['colorspace'].value()
        expected_cs = self.cfg.get(config_key, "")
        if expected_cs and expected_cs.lower() not in cs.lower():
            self.errors.append(
                f"Colorspace Error: Expected '{expected_cs}' "
                f"(got: '{cs}'). project.yml {config_key} 설정을 확인하세요."
            )

    def get_error_message(self) -> str:
        return "\n".join([f"• {err}" for err in self.errors])


def validate_render():
    """beforeRender 콜백 — 검증 실패 시 렌더를 중단합니다."""
    validator = PublishValidator()
    if not validator.validate_all():
        error_msg = validator.get_error_message()
        nuke.message(f"<font color='red'><b>PUBLISH DENIED</b></font>\n\n{error_msg}")
        raise RuntimeError(f"Publish Validation Failed:\n{error_msg}")


def smart_publish():
    """
    Smart Publish: 검증 → 렌더 → Kitsu preview 업로드
    1. 모든 Write 노드 검증
    2. 통과하면 렌더 실행
    3. 렌더 완료 후 review MOV를 Kitsu에 preview로 업로드
    """
    import threading

    write_nodes = [n for n in nuke.allNodes("Write")]
    if not write_nodes:
        nuke.message("Write 노드가 없습니다.")
        return

    # 1. 검증
    all_errors = []
    for wn in write_nodes:
        v = PublishValidator(write_node=wn)
        if not v.validate_all():
            all_errors.append(f"<b>{wn.name()}</b>\n{v.get_error_message()}")

    if all_errors:
        nuke.message(
            f"<font color='red'><b>PUBLISH DENIED</b></font>\n\n" + "\n\n".join(all_errors)
        )
        return

    # 2. 렌더 확인
    ctx = context.get_current()
    cfg = get_project_config(ctx.project) if ctx.project else {}
    workflow = cfg.get("workflow", "uhd")

    # 렌더할 Write 노드 결정
    review_node = nuke.toNode("Write_REVIEW")
    publish_node = nuke.toNode("Write_PUBLISH")

    render_nodes = []
    if workflow == "uhd" and publish_node:
        render_nodes.append(publish_node)
    if review_node:
        render_nodes.append(review_node)

    if not render_nodes:
        nuke.message("렌더할 Write 노드를 찾을 수 없습니다. (Write_REVIEW / Write_PUBLISH)")
        return

    node_names = ", ".join([n.name() for n in render_nodes])
    root = nuke.root()
    first = int(root['first_frame'].value())
    last = int(root['last_frame'].value())

    if not nuke.ask(f"Smart Publish\n\n"
                    f"렌더 노드: {node_names}\n"
                    f"프레임: {first} - {last}\n\n"
                    f"렌더를 시작하시겠습니까?"):
        return

    # 3. 렌더 실행
    try:
        for rn in render_nodes:
            nuke.execute(rn, first, last)
    except Exception as e:
        nuke.message(f"<font color='red'><b>RENDER FAILED</b></font>\n\n{e}")
        return

    # 4. Kitsu preview 업로드 (review MOV)
    if review_node and ctx.is_valid:
        review_path = review_node['file'].value()
        review_path = re.sub(r"%\d+d", "", review_path)

        if os.path.exists(review_path):
            try:
                from services.kitsu import KitsuAPI
                kitsu = KitsuAPI()

                # 태스크 자동 감지 (nk 파일명에서)
                script_name = os.path.basename(nuke.root().name())
                task_match = re.search(rf"{ctx.shot_code}_(\w+)_v\d+\.nk", script_name)
                task_name = task_match.group(1) if task_match else "comp"
                task_type = {"comp": "compositing", "roto": "rotoscoping",
                             "prep": "prep", "matte": "matte painting",
                             "fx": "fx"}.get(task_name, task_name)

                # 버전 감지 (nk 파일명에서)
                ver_match = re.search(r"_v(\d+)\.nk", script_name)
                ver_str = f"v{ver_match.group(1)}" if ver_match else "v001"

                preview_id = kitsu.publish_to_task(
                    ctx.project, ctx.shot_code, task_type,
                    review_path, f"Publish {ver_str}: {os.path.basename(review_path)}"
                )

                if preview_id:
                    nuke.message(
                        f"<font color='green'><b>SMART PUBLISH COMPLETE</b></font>\n\n"
                        f"렌더: {node_names}\n"
                        f"프레임: {first}-{last}\n"
                        f"Kitsu: preview 업로드 완료 ({ver_str})"
                    )
                    return
                else:
                    nuke.message(
                        f"<font color='green'><b>RENDER COMPLETE</b></font>\n\n"
                        f"렌더: {node_names}\n"
                        f"프레임: {first}-{last}\n\n"
                        f"<font color='orange'>Kitsu 업로드 실패 (샷/태스크 확인)</font>"
                    )
                    return

            except Exception as e:
                nuke.message(
                    f"<font color='green'><b>RENDER COMPLETE</b></font>\n\n"
                    f"렌더: {node_names}\n"
                    f"프레임: {first}-{last}\n\n"
                    f"<font color='orange'>Kitsu 업로드 실패: {e}</font>"
                )
                return

    nuke.message(
        f"<font color='green'><b>RENDER COMPLETE</b></font>\n\n"
        f"렌더: {node_names}\n"
        f"프레임: {first}-{last}\n\n"
        f"Kitsu 업로드는 수동으로 진행하세요."
    )


def run_manual():
    """메뉴에서 수동으로 검증을 실행합니다. 모든 Write 노드를 검사합니다."""
    write_nodes = [n for n in nuke.allNodes("Write")]
    if not write_nodes:
        nuke.message("Write 노드가 없습니다.")
        return

    all_errors = []
    for wn in write_nodes:
        validator = PublishValidator(write_node=wn)
        if not validator.validate_all():
            all_errors.append(f"<b>{wn.name()}</b>\n{validator.get_error_message()}")

    if not all_errors:
        nuke.message("<font color='green'><b>VALIDATION PASSED</b></font>\n\nAll Write nodes ready to publish.")
    else:
        nuke.message(
            f"<font color='red'><b>VALIDATION FAILED</b></font>\n\n" + "\n\n".join(all_errors)
        )
