import nuke
import os
import re
import logging
from pathlib import Path
from core import context
from core.env import get_project_config, get_ocio_config_for_project

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
    plate_dir = str(Path(shot_root) / "plate")

    if not os.path.isdir(plate_dir):
        nuke.message(f"Plate folder missing:\n{plate_dir}")
        return

    cfg = get_project_config(ctx.project) if ctx.project else {}

    # 쇼별 OCIO config — Nuke Root에 적용
    if ctx.project:
        ocio_path = get_ocio_config_for_project(ctx.project)
        if ocio_path:
            try:
                nuke.root()['colorManagement'].setValue('OCIO')
                nuke.root()['OCIO_config'].setValue('custom')
                nuke.root()['customOCIOConfigPath'].setValue(ocio_path)
                logger.info(f"OCIO config set: {ocio_path}")
            except Exception as e:
                logger.warning(f"OCIO config 적용 실패: {e}")

    # 1. EXR 시퀀스 감지 시도
    nuke_path, first, last = _detect_sequence(plate_dir)

    if nuke_path:
        read = nuke.createNode("Read")
        read["file"].setValue(nuke_path)
        read["first"].setValue(first)
        read["last"].setValue(last)
        read["origfirst"].setValue(first)
        read["origlast"].setValue(last)
        _apply_colorspace(read, cfg)
        read.autoplace()
        logger.info(f"EXR sequence loaded: {nuke_path} [{first}-{last}]")
        nuke.tprint(f"[SKYFALL] Plate Loaded (sequence): {nuke_path} [{first}-{last}]")
        return

    # 2. 단일 파일 폴백
    target = _find_best_single_file(plate_dir)
    if not target:
        nuke.message(f"No plate assets found in:\n{plate_dir}")
        return

    read = nuke.createNode("Read")
    read["file"].setValue(target)
    _apply_colorspace(read, cfg)
    read.autoplace()
    logger.info(f"Single file loaded: {target}")
    nuke.tprint(f"[SKYFALL] Plate Loaded: {target}")


def _apply_colorspace(read_node, cfg: dict):
    """
    플레이트 Read 노드에 카메라 입력 색공간을 적용합니다.
    project.yml의 camera_colorspace → OCIO input colorspace
    없으면 working_colorspace 폴백
    """
    # 플레이트 입력은 카메라 색공간 (LogC, S-Log3 등)
    colorspace = cfg.get("camera_colorspace") or cfg.get("working_colorspace", "")
    if not colorspace:
        return
    try:
        if 'colorspace' in read_node.knobs():
            read_node['colorspace'].setValue(colorspace)
            logger.info(f"Colorspace set: {colorspace}")
    except Exception as e:
        logger.warning(f"Could not set colorspace '{colorspace}': {e}")
