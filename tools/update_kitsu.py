"""
SKYFALL Kitsu Update (Wrapper)
개별 도구를 순서대로 호출합니다.

먼저 convert_excel.py로 CSV를 생성한 후 실행합니다.

개별 실행:
  python3 tools/convert_excel.py AAB --folder 260410         # Excel → CSV 변환
  python3 tools/update_kitsu_shots.py AAB --all              # 샷 등록 + description
  python3 tools/update_kitsu_preview.py AAB --folder 260410  # editor preview
  python3 tools/update_kitsu_comment.py AAB --folder 260410  # notes comment

일괄 실행:
  python3 tools/update_kitsu.py AAB --all --folder 260410
"""
import sys
import argparse
from pathlib import Path

pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from services.kitsu import KitsuAPI
from tools.update_kitsu_shots import register_shots, update_description
from tools.update_kitsu_comment import update_comments
from tools.update_kitsu_preview import upload_previews


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKYFALL Kitsu Update (샷등록 + description + comment + preview)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "개별 도구:",
            "  update_kitsu_shots.py   — 샷 등록 + description",
            "  update_kitsu_comment.py — VFX_Work → comment",
            "  update_kitsu_preview.py — editor MOV → preview",
            "",
            "예시:",
            "  python3 tools/update_kitsu.py AAB --all --folder 260410",
            "  python3 tools/update_kitsu.py AAB --folder 260410",
        ])
    )
    parser.add_argument("show",       help="Show 코드 (예: AAB)")
    parser.add_argument("--all",      action="store_true", help="plates/ 기준 전체 샷 Kitsu 등록")
    parser.add_argument("--folder",   help="from_client 폴더 (Excel + editor 처리)")
    parser.add_argument("--dry-run",  action="store_true", help="실제 처리 없이 확인만")
    args = parser.parse_args()

    if not args.all and not args.folder:
        parser.error("--all 또는 --folder 중 하나를 지정하세요.")

    kitsu = KitsuAPI()

    if args.all:
        register_shots(args.show, kitsu, dry_run=args.dry_run)

    if args.folder:
        update_description(args.show, kitsu, args.folder, dry_run=args.dry_run)
        upload_previews(args.show, kitsu, args.folder, dry_run=args.dry_run)
        update_comments(args.show, kitsu, args.folder, dry_run=args.dry_run)
