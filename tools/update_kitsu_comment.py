"""
SKYFALL Kitsu Comment Update
Excel의 VFX_Work를 COMPOSITING 태스크 comment로 업데이트합니다.

Usage:
  # Excel에서 VFX_Work → comment 업데이트
  python3 tools/update_kitsu_comment.py AAB --folder 260410

  # 서브폴더 지정
  python3 tools/update_kitsu_comment.py AAB --folder 260410/00_desc

  # dry-run
  python3 tools/update_kitsu_comment.py AAB --folder 260410 --dry-run
"""
import sys
import argparse
from pathlib import Path

pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

import csv

from core.env import get_shows_root
from services.kitsu import KitsuAPI
from services.kitsu_utils import parse_shot_code, resolve_folder


def update_comments(show: str, kitsu: KitsuAPI, folder_filter: str,
                    dry_run: bool = False):
    """notes.csv의 내용을 Kitsu 태스크 comment로 업데이트합니다."""
    show_root = get_shows_root() / show
    from_client = show_root / "exchange" / "from_client"
    top_dirs = resolve_folder(from_client, folder_filter)

    tag = "(DRY RUN) " if dry_run else ""
    print(f"\n[SKYFALL] Kitsu Comment {tag}— {show}\n")

    for top_dir in top_dirs:
        print(f"  📂 {top_dir.name}")

        notes_csv = top_dir / "notes.csv"
        if not notes_csv.exists():
            print(f"     (notes.csv 없음 — 먼저 convert_excel.py 실행)")
            continue

        with open(notes_csv, encoding="utf-8-sig") as f:
            entries = list(csv.DictReader(f))
        print(f"  📋 notes.csv: {len(entries)}개 노트")

        for entry in entries:
            shot_code = entry.get("shot_code", "").strip()
            if not shot_code:
                continue
            episode, sequence, shot = parse_shot_code(shot_code)
            if not sequence:
                continue

            task_name = entry.get("task", "comp").strip() or "comp"
            note = entry.get("note", "").strip()
            if not note:
                continue

            # task 이름 매핑 (comp → compositing)
            task_type = {"comp": "compositing", "roto": "rotoscoping",
                         "prep": "prep", "matte": "matte painting",
                         "fx": "fx"}.get(task_name, task_name)

            if dry_run:
                print(f"     {shot_code}  [{task_name}] {note[:50]}...")
                continue

            proj = kitsu.get_project(show)
            if not proj:
                print(f"     ❌ Kitsu project '{show}' 없음")
                return

            shot_data = kitsu.get_shot_data(proj["id"], shot)
            if not shot_data:
                print(f"     ⚠  {shot_code} — Kitsu 샷 없음")
                continue

            task = kitsu.get_task_for_shot(shot_data["id"], task_type)
            if not task:
                print(f"     {shot_code}  ⚠  {task_type.upper()} 태스크 없음")
                continue

            comment = kitsu.add_comment(task["id"], note)
            if comment and comment.get("id"):
                print(f"     {shot_code}  ✅ [{task_name}] {note[:50]}")
            else:
                print(f"     {shot_code}  ❌ comment 생성 실패")

    print(f"\n[SKYFALL] {'DRY RUN 완료' if dry_run else '✅ 완료'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKYFALL Kitsu Comment Update (Excel VFX_Work → COMPOSITING comment)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "예시:",
            "  python3 tools/update_kitsu_comment.py AAB --folder 260410",
            "  python3 tools/update_kitsu_comment.py AAB --folder 260410/00_desc",
            "  python3 tools/update_kitsu_comment.py AAB --folder 260410 --dry-run",
        ])
    )
    parser.add_argument("show",       help="Show 코드 (예: AAB)")
    parser.add_argument("--folder",   required=True, help="from_client 폴더 (Excel 위치)")
    parser.add_argument("--dry-run",  action="store_true", help="실제 처리 없이 확인만")
    args = parser.parse_args()

    kitsu = KitsuAPI()
    update_comments(args.show, kitsu, args.folder, dry_run=args.dry_run)
