import nuke
import os
import re
import logging
from core import context
from core.env import get_project_config

logger = logging.getLogger("skyfall.validator")

# 허용 색심도 (EXR 기준)
_ALLOWED_COLORSPACE_KEYWORDS = ("aces", "linear", "acescg")
_ALLOWED_EXTENSIONS = (".exr",)
_REQUIRED_BIT_DEPTH = "16"  # Nuke datatype 문자열에 포함되어야 함


class PublishValidator:
    """
    SKYFALL Strict Validator
    Ensures all rendering/publishing meets studio standards.
    """
    def __init__(self, write_node=None):
        self.node = write_node or nuke.thisNode()
        self.ctx = context.get_current()
        self.cfg = get_project_config(self.ctx.project) if self.ctx.project else {}
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

        self.check_resolution()
        self.check_naming()
        self.check_output_path_exists()
        self.check_frame_range()
        self.check_file_format()

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
                f"Naming Error: File must match '{shot_code}_<task>_v###.exr' "
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
        """
        use_limit 여부와 무관하게 Write 노드 렌더 범위를 검사합니다.
        use_limit=False면 Nuke 프로젝트 전체 범위로 렌더되므로, 그 범위도 검사합니다.
        """
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

    def check_file_format(self):
        """파일 확장자(EXR 필수), 색심도(16-bit 이상), 압축(ZIP1), 출력 색공간(ACEScct) 검사."""
        file_path = self.node['file'].value()
        clean_path = re.sub(r"(%\d+d|#+)", "0000", file_path)
        _, ext = os.path.splitext(clean_path)

        if ext.lower() not in _ALLOWED_EXTENSIONS:
            self.errors.append(
                f"Format Error: Only EXR is allowed for publish (got '{ext}'). "
                f"MOV/JPG/etc. are not accepted."
            )
            return

        # 비트 뎁스 확인 (16-bit half 또는 32-bit float)
        if 'datatype' in self.node.knobs():
            datatype = self.node['datatype'].value()
            if _REQUIRED_BIT_DEPTH not in datatype and "32" not in datatype:
                self.errors.append(
                    f"Bit Depth Error: EXR must be 16-bit half or 32-bit float "
                    f"(got: '{datatype}'). 8-bit EXR is not allowed."
                )

        # 압축 방식 확인 (ZIP1 필수 — Netflix 납품 스펙)
        if 'compression' in self.node.knobs():
            compression = self.node['compression'].value()
            expected_compressor = self.cfg.get("output_compressor", "zip1").lower()
            if expected_compressor not in compression.lower():
                self.errors.append(
                    f"Compression Error: Must use '{expected_compressor.upper()}' compression "
                    f"(got: '{compression}'). Netflix delivery spec requires ZIP1."
                )

        # 출력 색공간 확인 (project.yml의 output_colorspace 기준)
        if 'colorspace' in self.node.knobs():
            cs = self.node['colorspace'].value()
            expected_cs = self.cfg.get("output_colorspace", "ACES - ACEScct")
            if expected_cs.lower() not in cs.lower():
                self.errors.append(
                    f"Colorspace Error: Output must be '{expected_cs}' "
                    f"(got: '{cs}'). project.yml output_colorspace 설정을 확인하세요."
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


def run_manual():
    """메뉴에서 수동으로 검증을 실행합니다."""
    validator = PublishValidator()
    if validator.validate_all():
        nuke.message("<font color='green'><b>VALIDATION PASSED</b></font>\n\nReady to publish.")
    else:
        nuke.message(
            f"<font color='red'><b>VALIDATION FAILED</b></font>\n\n{validator.get_error_message()}"
        )
