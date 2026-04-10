"""
SKYFALL Kitsu Preview Upload
editor MOV를 Kitsu COMPOSITING 태스크에 preview로 업로드합니다.

Usage:
  # editor MOV → Kitsu preview 업로드
  python3 tools/update_kitsu_preview.py AAB --folder 260410

  # 서브폴더 지정
  python3 tools/update_kitsu_preview.py AAB --folder 260410/01_editor

  # dry-run
  python3 tools/update_kitsu_preview.py AAB --folder 260410 --dry-run
"""
import sys
import argparse
from pathlib import Path

pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.env import get_shows_root
from services.kitsu import KitsuAPI
from services.kitsu_utils import parse_shot_code, resolve_folder, find_editors


_TASK_MAP = {
    "comp": "compositing", "compositing": "compositing",
    "roto": "rotoscoping", "rotoscoping": "rotoscoping",
    "prep": "prep", "matte": "matte painting",
    "fx": "fx",
}


def upload_previews(show: str, kitsu: KitsuAPI, folder_filter: str,
                    task_name: str = "comp", dry_run: bool = False):
    """editor MOV를 Kitsu 태스크에 preview로 업로드합니다."""
    show_root = get_shows_root() / show
    from_client = show_root / "exchange" / "from_client"
    top_dirs = resolve_folder(from_client, folder_filter)

    task_type = _TASK_MAP.get(task_name.lower(), task_name)
    tag = "(DRY RUN) " if dry_run else ""
    print(f"\n[SKYFALL] Kitsu Preview ({task_type.upper()}) {tag}— {show}\n")

    for top_dir in top_dirs:
        print(f"  📂 {top_dir.name}")

        editors = find_editors(top_dir)
        if not editors:
            print(f"     (Editor 없음)")
            continue

        print(f"  🎬 Editor: {len(editors)}개")

        for shot_code, (editor_path, version) in sorted(editors.items()):
            episode, sequence, shot = parse_shot_code(shot_code)
            if not sequence:
                continue

            if dry_run:
                print(f"     {shot_code}  → {editor_path.name} ({version})")
                continue

            proj = kitsu.get_project(show)
            if not proj:
                print(f"     ❌ Kitsu project '{show}' 없음")
                return

            shot_data = kitsu.get_shot_data(proj["id"], shot, episode=episode, sequence=sequence)
            if not shot_data:
                print(f"     ⚠  {shot_code} — Kitsu 샷 없음")
                continue

            task = kitsu.get_task_for_shot(shot_data["id"], task_type)
            if not task:
                print(f"     {shot_code}  ⚠  {task_type.upper()} 태스크 없음")
                continue

            # Comment + Preview 업로드 (2단계: add-preview → 파일 업로드)
            comment = kitsu.add_comment(
                task["id"],
                f"Editor guide: {editor_path.name} ({version})"
            )
            if comment and comment.get("id"):
                preview_id = kitsu.upload_preview(
                    task["id"], comment["id"], str(editor_path)
                )
                if preview_id:
                    kitsu.set_main_preview(shot_data["id"], preview_id)
                    print(f"     {shot_code}  ✅ preview: {editor_path.name} ({version})")
                else:
                    print(f"     {shot_code}  ❌ preview 업로드 실패")
            else:
                print(f"     {shot_code}  ❌ comment 생성 실패")

    print(f"\n[SKYFALL] {'DRY RUN 완료' if dry_run else '✅ 완료'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKYFALL Kitsu Preview Upload (editor MOV → task preview)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "예시:",
            "  python3 tools/update_kitsu_preview.py AAB --folder 260410",
            "  python3 tools/update_kitsu_preview.py AAB --folder 260410 --task roto",
            "  python3 tools/update_kitsu_preview.py AAB --folder 260410/01_editor",
            "  python3 tools/update_kitsu_preview.py AAB --folder 260410 --dry-run",
        ])
    )
    parser.add_argument("show",       help="Show 코드 (예: AAB)")
    parser.add_argument("--folder",   required=True, help="from_client 폴더 (editor MOV 위치)")
    parser.add_argument("--task",     default="comp", help="태스크 타입 (comp/roto/prep/matte/fx, 기본: comp)")
    parser.add_argument("--dry-run",  action="store_true", help="실제 처리 없이 확인만")
    args = parser.parse_args()

    kitsu = KitsuAPI()
    upload_previews(args.show, kitsu, args.folder, task_name=args.task, dry_run=args.dry_run)
