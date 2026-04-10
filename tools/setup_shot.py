"""
SKYFALL Shot Setup
샷 폴더 구조, plate 심링크, Nuke 스크립트를 생성합니다.
(Kitsu 등록은 update_kitsu.py에서 처리)

Usage:
  # 단일 샷
  python3 tools/setup_shot.py AAB EP01_S004_0002 --first 1001 --last 1100

  # ingest된 전체 샷 일괄 생성 (plates/ 폴더 기준)
  python3 tools/setup_shot.py AAB --all

  # dry-run
  python3 tools/setup_shot.py AAB --all --dry-run
"""
import os
import sys
import argparse
from pathlib import Path

pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.env import get_shows_root
from tools.create_nk import create_nk


def _collect_ingested_shots(show_root: Path) -> list[str]:
    """
    plates/ 하위 폴더에서 인제스트된 샷 코드를 수집합니다.
    버전 서브폴더(v001 등)에 파일이 있어야 유효한 샷으로 인식합니다.
    """
    plates_root = show_root / "plates"
    if not plates_root.exists():
        return []

    shots = []
    for shot_dir in sorted(plates_root.iterdir()):
        if not shot_dir.is_dir() or shot_dir.name.startswith("."):
            continue
        if shot_dir.name == "ingest_log":
            continue
        # 버전 서브폴더에 실제 파일이 있는지 확인
        has_files = any(
            f.suffix in (".exr", ".mov")
            for ver_dir in shot_dir.iterdir()
            if ver_dir.is_dir()
            for f in ver_dir.iterdir()
        )
        if has_files:
            shots.append(shot_dir.name)
    return shots


def setup_shot(show: str, shot_code: str, frame_in: int, frame_out: int,
               dry_run: bool = False, task: str = "comp"):
    """
    SKYFALL Shot Setup — ingest_plate 이후 샷 단위로 실행.
    1. 로컬 폴더 생성 + plate 심링크
    2. Nuke 베이스 스크립트 생성 (create_nk 호출)
    """
    parts = shot_code.split('_')
    if len(parts) == 3:
        episode, sequence, shot = parts
        rel_path = f"{episode}/{sequence}/{shot}"
    elif len(parts) == 2:
        episode = None
        sequence, shot = parts
        rel_path = f"{sequence}/{shot}"
    else:
        print(f"  ❌ shot_code 형식 오류: {shot_code}")
        return

    show_root = get_shows_root() / show
    if not show_root.exists():
        print(f"❌ Show '{show}' 없음. 먼저 init_show.py를 실행하세요.")
        return

    shot_path = show_root / rel_path

    if dry_run:
        status = "✅ 생성 예정" if not shot_path.exists() else "⏭  이미 존재"
        print(f"  {status}: {shot_code}")
        return

    print(f"  {shot_code}", end="  ")

    # 1. 폴더 생성
    for folder in ["comp/nk", "comp/render/v001", "comp/review/v001", "roto", "prep", "fx"]:
        (shot_path / folder).mkdir(parents=True, exist_ok=True)

    # 2. Plate 심링크
    central_plate_dir = show_root / "plates" / shot_code
    central_plate_dir.mkdir(parents=True, exist_ok=True)

    local_plate_link = shot_path / "plate"
    if not local_plate_link.exists():
        ups = "../../../" if episode else "../../"
        rel_target = f"{ups}plates/{shot_code}"
        os.symlink(rel_target, local_plate_link)

    # 3. Nuke 스크립트 생성
    # 새 버전 플레이트가 들어왔으면 nk 재생성 (force)
    nk_dir = shot_path / task / "nk"
    nk_v001 = nk_dir / f"{shot_code}_{task}_v001.nk"
    force = False
    if nk_v001.exists():
        # nk 파일보다 새로운 플레이트 버전이 있는지 확인
        nk_mtime = nk_v001.stat().st_mtime
        plate_newer = any(
            f.stat().st_mtime > nk_mtime
            for ver_dir in central_plate_dir.iterdir()
            if ver_dir.is_dir()
            for f in ver_dir.iterdir()
            if f.suffix in (".exr", ".mov")
        )
        if plate_newer:
            force = True
            print(f"(새 플레이트 감지 → nk 재생성) ", end="")
    create_nk(show, shot_code, frame_in=frame_in, frame_out=frame_out, force=force, task=task)


def setup_all(show: str, frame_in: int, frame_out: int, dry_run: bool = False, task: str = "comp"):
    """plates/ 폴더 기준으로 인제스트된 전체 샷을 일괄 생성합니다."""
    show_root = get_shows_root() / show
    if not show_root.exists():
        print(f"❌ Show '{show}' 없음.")
        sys.exit(1)

    shots = _collect_ingested_shots(show_root)
    if not shots:
        print(f"[SKYFALL] ❌ plates/ 에 인제스트된 샷이 없습니다.")
        print(f"           먼저 ingest_plate.py 를 실행하세요.")
        sys.exit(1)

    tag = "(DRY RUN) " if dry_run else ""
    print(f"\n[SKYFALL] setup_shot {tag}— {show}  ({len(shots)}샷)")
    print()

    for shot_code in shots:
        setup_shot(show, shot_code, frame_in, frame_out, dry_run=dry_run, task=task)

    print()
    if dry_run:
        print(f"[SKYFALL] DRY RUN 완료 — 실제 생성 없음")
        print(f"          실제 실행: --dry-run 제거")
    else:
        print(f"[SKYFALL] ✅ 완료 — {len(shots)}샷 생성")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKYFALL Shot Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "실행 순서:",
            "  1. init_show    — 쇼 생성",
            "  2. ingest_plate — 플레이트 복사",
            "  3. setup_shot   — 샷 폴더 + nk 생성",
            "  4. update_kitsu — Kitsu 등록 + description + editor",
            "  5. Nuke 열기",
            "",
            "예시:",
            "  # 단일 샷",
            "  python3 tools/setup_shot.py AAB EP01_S004_0002 --first 1001 --last 1100",
            "",
            "  # 전체 샷 일괄 (ingest된 샷 자동 감지)",
            "  python3 tools/setup_shot.py AAB --all --dry-run",
            "  python3 tools/setup_shot.py AAB --all",
            "",
            "  # nk 버전업",
            "  python3 tools/create_nk.py AAB EP01_S004_0002 --new-version",
        ])
    )
    parser.add_argument("show",           help="Show 코드 (예: AAB)")
    parser.add_argument("shot_code",      nargs="?", help="샷 코드. --all 이면 생략 가능")
    parser.add_argument("--first",        type=int, default=1001, help="시작 프레임 (기본: 1001)")
    parser.add_argument("--last",         type=int, default=1100, help="마지막 프레임 (기본: 1100)")
    parser.add_argument("--all",          action="store_true", help="ingest된 전체 샷 일괄 생성")
    parser.add_argument("--task",         default="comp", help="태스크 타입 (comp/roto/prep, 기본: comp)")
    parser.add_argument("--dry-run",      action="store_true", help="실제 생성 없이 확인만")
    args = parser.parse_args()

    if args.all:
        setup_all(args.show, args.first, args.last, dry_run=args.dry_run, task=args.task)
    else:
        if not args.shot_code:
            parser.error("shot_code 를 지정하거나 --all 을 사용하세요.")
        print(f"\n[SKYFALL] Shot 생성: {args.show} > {args.shot_code} [{args.task}]")
        setup_shot(args.show, args.shot_code, args.first, args.last, task=args.task)
        print(f"[SKYFALL] ✅ 완료")
