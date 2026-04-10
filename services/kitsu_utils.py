"""
SKYFALL Kitsu 공통 유틸리티
update_kitsu_shots / update_kitsu_comment / update_kitsu_preview 에서 공유합니다.
"""
import re
import sys
from pathlib import Path


def parse_shot_code(shot_code: str):
    """샷 코드에서 (episode, sequence, shot)을 파싱합니다."""
    parts = shot_code.split("_")
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        return None, parts[0], parts[1]
    return None, None, None


def collect_ingested_shots(show_root: Path) -> list[str]:
    """plates/ 하위에서 인제스트된 샷 코드를 수집합니다."""
    plates_root = show_root / "plates"
    if not plates_root.exists():
        return []
    shots = []
    for shot_dir in sorted(plates_root.iterdir()):
        if not shot_dir.is_dir() or shot_dir.name.startswith("."):
            continue
        if shot_dir.name == "ingest_log":
            continue
        has_files = any(
            f.suffix in (".exr", ".mov")
            for ver_dir in shot_dir.iterdir()
            if ver_dir.is_dir()
            for f in ver_dir.iterdir()
        )
        if has_files:
            shots.append(shot_dir.name)
    return shots


def resolve_folder(from_client: Path, folder_filter: str) -> list[Path]:
    """
    from_client/ 하위에서 폴더를 필터합니다.
    - folder_filter에 /가 포함되면 서브폴더 직접 지정
    - 없으면 부분 문자열 매칭
    """
    if not from_client.exists():
        print(f"[SKYFALL] ❌ exchange/from_client 폴더 없음")
        sys.exit(1)

    if "/" in folder_filter:
        direct_path = from_client / folder_filter
        if direct_path.is_dir():
            return [direct_path]
        else:
            print(f"[SKYFALL] ❌ 폴더 없음: {direct_path}")
            sys.exit(1)

    top_dirs = sorted([d for d in from_client.iterdir()
                       if d.is_dir() and not d.name.startswith(".")])
    matched = [d for d in top_dirs if folder_filter in d.name]
    if not matched:
        print(f"[SKYFALL] ❌ '{folder_filter}' 매칭 폴더 없음")
        sys.exit(1)
    return matched


# editor 파일 패턴: EP01_S004_0002_editor_v001.mov
_EDITOR_PATTERN = re.compile(
    r"^(E[P]?\d+_S\d+_\d+)_editor_(v\d+)\.(mov|mp4)$",
    re.IGNORECASE,
)


def find_editors(folder: Path) -> dict[str, tuple[Path, str]]:
    """폴더에서 editor MOV 파일을 재귀 스캔합니다. {shot_code: (file_path, version)}"""
    editors = {}
    for f in folder.rglob("*"):
        if f.is_file():
            m = _EDITOR_PATTERN.match(f.name)
            if m:
                shot_code = m.group(1).upper()
                version = m.group(2).lower()
                editors[shot_code] = (f, version)
    return editors
