"""
SKYFALL Kitsu Shot Registration
Kitsu에 샷을 등록하고, Excel에서 description을 업데이트합니다.

Usage:
  # plates/ 기준 전체 샷 등록
  python3 tools/update_kitsu_shots.py AAB --all

  # Excel에서 description 업데이트
  python3 tools/update_kitsu_shots.py AAB --folder 260410

  # 둘 다
  python3 tools/update_kitsu_shots.py AAB --all --folder 260410

  # dry-run
  python3 tools/update_kitsu_shots.py AAB --all --dry-run
"""
import sys
import argparse
from pathlib import Path

pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

import csv

from core.env import get_shows_root, get_project_config
from services.kitsu import KitsuAPI
from services.kitsu_utils import parse_shot_code, collect_ingested_shots, resolve_folder
from tools.create_nk import _mov_frame_range


def _detect_frame_range(plates_dir: Path, shot_code: str, fps: float) -> tuple[int, int]:
    """plates/{shot_code}/ 에서 프레임 레인지를 감지합니다."""
    import re
    shot_plate = plates_dir / shot_code
    if not shot_plate.exists():
        return 1001, 1100

    ver_dirs = sorted([d for d in shot_plate.iterdir() if d.is_dir() and d.name.startswith("v")])
    if not ver_dirs:
        return 1001, 1100

    latest = ver_dirs[-1]

    movs = list(latest.glob("*.mov"))
    if movs:
        return _mov_frame_range(movs[0], fps)

    exrs = sorted(latest.glob("*.exr"))
    if exrs:
        frames = [int(m.group(1)) for f in exrs
                  if (m := re.search(r"\.(\d+)\.exr$", f.name, re.I))]
        if frames:
            nb = max(frames) - min(frames) + 1
            return 1001, 1001 + nb - 1

    return 1001, 1100


_TASK_MAP = {
    "comp": "compositing", "roto": "rotoscoping",
    "prep": "prep", "matte": "matte painting", "fx": "fx",
}


def register_shots(show: str, kitsu: KitsuAPI, dry_run: bool = False, extra_tasks: list = None):
    """plates/ 기준으로 전체 샷을 Kitsu에 등록합니다."""
    show_root = get_shows_root() / show
    shots = collect_ingested_shots(show_root)
    if not shots:
        print(f"[SKYFALL] plates/ 에 샷이 없습니다.")
        return

    cfg = get_project_config(show)
    fps = cfg.get("fps", 23.976)
    plates_dir = show_root / "plates"

    tag = "(DRY RUN) " if dry_run else ""
    print(f"\n[SKYFALL] Kitsu 샷 등록 {tag}— {show}  ({len(shots)}샷)\n")

    for shot_code in shots:
        episode, sequence, shot = parse_shot_code(shot_code)
        if not sequence:
            print(f"  ❌ shot_code 형식 오류: {shot_code}")
            continue

        frame_in, frame_out = _detect_frame_range(plates_dir, shot_code, fps)

        if dry_run:
            print(f"  {shot_code}  → 등록 예정 [{frame_in}-{frame_out}]")
            continue

        print(f"  {shot_code}", end="  ")
        try:
            kitsu.get_or_create_shot(show, episode, sequence, shot, frame_in, frame_out, extra_tasks=extra_tasks)
        except Exception as e:
            print(f"❌ {e}")


def update_description(show: str, kitsu: KitsuAPI, folder_filter: str,
                       dry_run: bool = False):
    """shots.csv에서 description을 읽어 Kitsu 샷에 업데이트합니다."""
    show_root = get_shows_root() / show
    from_client = show_root / "exchange" / "from_client"
    top_dirs = resolve_folder(from_client, folder_filter)

    tag = "(DRY RUN) " if dry_run else ""
    print(f"\n[SKYFALL] Kitsu Description {tag}— {show}\n")

    for top_dir in top_dirs:
        print(f"  📂 {top_dir.name}")

        shots_csv = top_dir / "shots.csv"
        if not shots_csv.exists():
            # 서브폴더 탐색
            found = list(top_dir.rglob("shots.csv"))
            if found:
                shots_csv = found[0]
            else:
                print(f"     (shots.csv 없음 — 먼저 convert_excel.py 실행)")
                continue

        with open(shots_csv, encoding="utf-8-sig") as f:
            entries = list(csv.DictReader(f))
        print(f"  📋 shots.csv: {len(entries)}개 샷")

        for entry in entries:
            shot_code = entry.get("shot_code", "").strip()
            if not shot_code:
                continue
            episode, sequence, shot = parse_shot_code(shot_code)
            if not sequence:
                continue

            desc_text = entry.get("description", "").strip()

            if dry_run:
                print(f"     {shot_code}  desc: {desc_text[:50]}...")
                continue

            proj = kitsu.get_project(show)
            if not proj:
                print(f"     ❌ Kitsu project '{show}' 없음")
                return

            shot_data = kitsu.get_shot_data(proj["id"], shot, episode=episode, sequence=sequence)
            if not shot_data:
                print(f"     ⚠  {shot_code} — Kitsu 샷 없음 (먼저 --all로 등록)")
                continue

            if desc_text:
                ok = kitsu.update_shot_description(shot_data["id"], desc_text)
                print(f"     {shot_code}  ✅ description" if ok else f"     {shot_code}  ❌ description")

    print(f"\n[SKYFALL] {'DRY RUN 완료' if dry_run else '✅ 완료'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKYFALL Kitsu Shot Registration + Description",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "예시:",
            "  # 전체 샷 Kitsu 등록 (frame range 자동 감지)",
            "  python3 tools/update_kitsu_shots.py AAB --all",
            "",
            "  # Excel에서 description 업데이트",
            "  python3 tools/update_kitsu_shots.py AAB --folder 260410",
            "  python3 tools/update_kitsu_shots.py AAB --folder 260410/00_desc",
            "",
            "  # 등록 + description 동시",
            "  python3 tools/update_kitsu_shots.py AAB --all --folder 260410",
        ])
    )
    parser.add_argument("show",       help="Show 코드 (예: AAB)")
    parser.add_argument("--all",      action="store_true", help="plates/ 기준 전체 샷 Kitsu 등록")
    parser.add_argument("--folder",   help="from_client 폴더 (Excel description 처리)")
    parser.add_argument("--task",     action="append", help="추가 태스크 (comp/roto/prep, 여러 번 사용 가능)")
    parser.add_argument("--dry-run",  action="store_true", help="실제 처리 없이 확인만")
    args = parser.parse_args()

    if not args.all and not args.folder:
        parser.error("--all 또는 --folder 중 하나를 지정하세요.")

    # 태스크 이름 → Kitsu 태스크 타입으로 변환
    extra_tasks = None
    if args.task:
        extra_tasks = [_TASK_MAP.get(t.lower(), t) for t in args.task]

    kitsu = KitsuAPI()

    if args.all:
        register_shots(args.show, kitsu, dry_run=args.dry_run, extra_tasks=extra_tasks)

    if args.folder:
        update_description(args.show, kitsu, args.folder, dry_run=args.dry_run)
