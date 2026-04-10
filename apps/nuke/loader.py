import nuke
import os
import re
import logging
from pathlib import Path
from core import context
from core.env import get_project_config

logger = logging.getLogger("skyfall.loader")

_ALLOWED_EXTENSIONS = {".exr", ".mov", ".mp4", ".tif", ".tiff", ".dpx", ".mxf"}


def _parse_version(filename: str) -> int:
    """파일명에서 버전 번호를 추출합니다. (예: plate_v003.exr -> 3)"""
    match = re.search(r"v(\d+)", filename, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _detect_sequence(plate_dir: str) -> tuple[str, int, int] | tuple[None, None, None]:
    """
    EXR 시퀀스를 감지하여 (nuke_path, first_frame, last_frame)을 반환합니다.
    시퀀스가 없으면 (None, None, None)을 반환합니다.

    예: shot_plate_v001.0001.exr -> shot_plate_v001.%04d.exr, 1, 100
    """
    files = [f for f in os.listdir(plate_dir) if f.endswith(".exr") and not f.startswith(".")]
    if not files:
        return None, None, None

    # 프레임 번호 패턴: 파일명 끝 부분의 숫자 그룹
    frame_pattern = re.compile(r"^(.+?)\.(\d+)\.exr$", re.IGNORECASE)
    sequences: dict[str, list[int]] = {}

    for f in files:
        m = frame_pattern.match(f)
        if m:
            base, frame_str = m.group(1), m.group(2)
            sequences.setdefault(base, []).append(int(frame_str))

    if not sequences:
        return None, None, None

    # 버전이 가장 높은 시퀀스 선택
    best_base = max(sequences.keys(), key=_parse_version)
    frames = sorted(sequences[best_base])
    frame_len = len(str(frames[0]))  # 자릿수 맞추기 (예: 0001 -> 4자리)
    nuke_path = os.path.join(plate_dir, f"{best_base}.%0{frame_len}d.exr")
    return nuke_path, frames[0], frames[-1]


def _find_best_single_file(plate_dir: str) -> str | None:
    """
    EXR 시퀀스가 없을 때 단일 파일 중 가장 높은 버전을 반환합니다.
    버전 번호 기준 정렬 → 없으면 mtime 기준.
    """
    files = [
        f for f in os.listdir(plate_dir)
        if not f.startswith(".")
        and os.path.splitext(f)[1].lower() in _ALLOWED_EXTENSIONS
    ]
    if not files:
        return None

    versioned = [f for f in files if re.search(r"v\d+", f, re.IGNORECASE)]
    if versioned:
        return os.path.join(plate_dir, max(versioned, key=_parse_version))

    # 버전 번호 없으면 수정 시간 기준
    return os.path.join(
        plate_dir,
        max(files, key=lambda f: os.path.getmtime(os.path.join(plate_dir, f)))
    )


def load_plate():
    ctx = context.get_current()
    if not ctx.is_valid:
        nuke.message("Please save your script in the correct pipeline structure first.")
        return

    shot_root = ctx.get_shot_root()
    plate_base = Path(shot_root) / "plate"

    if not plate_base.is_dir():
        nuke.message(f"Plate folder missing:\n{plate_base}")
        return

    # 버전 서브폴더가 있으면 최신 버전 사용
    ver_dirs = sorted([d for d in plate_base.iterdir() if d.is_dir() and d.name.startswith("v")])
    plate_dir = str(ver_dirs[-1]) if ver_dirs else str(plate_base)

    cfg = get_project_config(ctx.project) if ctx.project else {}

    # OCIO는 nk 파일에 이미 설정되어 있으므로 loader에서 변경하지 않음

    # 1. EXR 시퀀스 감지 시도
    nuke_path, first, last = _detect_sequence(plate_dir)

    if nuke_path:
        read = nuke.createNode("Read")
        read["file"].setValue(nuke_path)
        read["first"].setValue(first)
        read["last"].setValue(last)
        read["origfirst"].setValue(first)
        read["origlast"].setValue(last)
        read.autoplace()
        logger.info(f"EXR sequence loaded: {nuke_path} [{first}-{last}]")
        nuke.tprint(f"[SKYFALL] Plate Loaded (sequence): {nuke_path} [{first}-{last}]")
        return

    # 2. 단일 파일 폴백 (MOV 등)
    target = _find_best_single_file(plate_dir)
    if not target:
        nuke.message(f"No plate assets found in:\n{plate_dir}")
        return

    camera_cs = cfg.get("camera_colorspace", "")

    if target.lower().endswith((".mov", ".mp4")):
        # MOV: 기존 Read_PLATE에서 프레임 정보 가져오기
        existing_read = nuke.toNode("Read_PLATE")
        if existing_read:
            orig_last = int(existing_read["last"].value())
            frame_in = int(nuke.root()["first_frame"].value())
        else:
            # ffprobe fallback (절대 경로)
            try:
                import subprocess
                result = subprocess.run(
                    ["/opt/homebrew/bin/ffprobe", "-v", "quiet",
                     "-select_streams", "v:0", "-count_packets",
                     "-show_entries", "stream=nb_read_packets",
                     "-of", "csv=p=0", target],
                    capture_output=True, text=True, timeout=10
                )
                orig_last = int(result.stdout.strip().split(",")[-1])
            except Exception:
                orig_last = 100
            frame_in = 1001

        # 기존 Read_PLATE와 동일한 nk 포맷으로 생성
        cs = camera_cs or "default"
        nuke.tprint(f"[SKYFALL] Load Plate cfg: {cfg}")
        nuke.tprint(f"[SKYFALL] Load Plate colorspace: {cs}")
        nuke.tprint(f"[SKYFALL] Load Plate project: {ctx.project}")
        nk_str = (
            f'Read {{\n'
            f' inputs 0\n'
            f' file_type mov\n'
            f' file {target}\n'
            f' before black\n'
            f' last {orig_last}\n'
            f' after black\n'
            f' frame_mode "start at"\n'
            f' frame {frame_in}\n'
            f' origlast {orig_last}\n'
            f' origset true\n'
            f' colorspace "{cs}"\n'
            f' name Read_loaded\n'
            f' label PLATE\n'
            f'}}\n'
        )

        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".nk", mode="w", delete=False)
        tmp.write(nk_str)
        tmp.close()
        nuke.scriptSource(tmp.name)
        os.unlink(tmp.name)
        loaded = nuke.toNode("Read_loaded")
        if loaded:
            loaded.autoplace()
    else:
        read = nuke.createNode("Read")
        read["file"].setValue(target)
        read.autoplace()
    logger.info(f"Single file loaded: {target}")
    nuke.tprint(f"[SKYFALL] Plate Loaded: {target}")


