"""
SKYFALL Excel → 내부 CSV 변환
클라이언트 Excel을 내부 표준 포맷(shots.csv, notes.csv)으로 변환합니다.

Usage:
  python3 tools/convert_excel.py AAB --folder 260206
  python3 tools/convert_excel.py AAB --folder 260206/00_desc
  python3 tools/convert_excel.py AAB --folder 260206 --dry-run
  python3 tools/convert_excel.py AAB --folder 260206 --force   # 기존 CSV 덮어쓰기
"""
import csv
import sys
import argparse
from pathlib import Path

pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.env import get_shows_root, get_project_config
from services.excel_parser import find_excel, parse_excel
from services.kitsu_utils import resolve_folder
from tools.create_nk import _mov_frame_range


_SHOTS_FIELDS = ["shot_code", "description", "frame_in", "frame_out", "colorspace"]
_NOTES_FIELDS = ["shot_code", "task", "note", "status", "assignee"]

# 클라이언트 status → Kitsu status 매핑
_STATUS_MAP = {
    "wtg": "todo",   "waiting": "todo",
    "rdy": "todo",   "ready": "todo",
    "todo": "todo",
    "wip": "wip",    "ip": "wip",     "in progress": "wip",
    "change": "wip",
    "retake": "retake", "rtk": "retake",
    "done": "done",  "fin": "done",   "final": "done",  "approved": "done",
    "hold": "todo",  "omit": "todo",
}

# VFX_Work 첫 줄에서 태스크 타입 추출
_TASK_KEYWORDS = {
    "comp": "comp", "compositing": "comp",
    "matte": "matte", "matte painting": "matte", "mp": "matte",
    "roto": "roto", "rotoscoping": "roto",
    "prep": "prep",
    "fx": "fx", "effect": "fx", "effects": "fx",
    "paint": "prep", "cleanup": "prep",
}


def _detect_frame_range(plates_dir: Path, shot_code: str, fps: float) -> tuple[int, int]:
    """plates/{shot_code}/ 에서 ffprobe로 실제 프레임 레인지를 감지합니다."""
    import re
    shot_plate = plates_dir / shot_code
    if not shot_plate.exists():
        return 0, 0

    ver_dirs = sorted([d for d in shot_plate.iterdir() if d.is_dir() and d.name.startswith("v")])
    if not ver_dirs:
        return 0, 0

    latest = ver_dirs[-1]

    # MOV
    movs = list(latest.glob("*.mov"))
    if movs:
        return _mov_frame_range(movs[0], fps)

    # EXR
    exrs = sorted(latest.glob("*.exr"))
    if exrs:
        frames = [int(m.group(1)) for f in exrs
                  if (m := re.search(r"\.(\d+)\.exr$", f.name, re.I))]
        if frames:
            nb = max(frames) - min(frames) + 1
            return 1001, 1001 + nb - 1

    return 0, 0


def _extract_task(vfx_work: str) -> tuple[str, str]:
    """
    VFX_Work 텍스트에서 태스크 타입과 실제 note를 분리합니다.
    반환: (task, note)
    """
    lines = vfx_work.strip().split("\n")
    first_line = lines[0].strip().lower()

    # 첫 줄이 태스크 키워드인 경우
    if first_line in _TASK_KEYWORDS:
        task = _TASK_KEYWORDS[first_line]
        note = "\n".join(lines[1:]).strip()
        return task, note

    # 첫 줄이 "comp\n1) ..." 같은 형태
    # 또는 "matte\n1) ..." 형태
    first_word = first_line.split()[0] if first_line else ""
    if first_word in _TASK_KEYWORDS:
        task = _TASK_KEYWORDS[first_word]
        # 첫 단어만 태스크면 나머지는 note
        rest_of_first = lines[0].strip()[len(first_word):].strip()
        if rest_of_first:
            note = rest_of_first + "\n" + "\n".join(lines[1:]).strip()
        else:
            note = "\n".join(lines[1:]).strip()
        return task, note.strip()

    # 태스크 키워드 없으면 기본 comp
    return "comp", vfx_work.strip()


def _map_status(raw_status: str) -> str:
    """클라이언트 status를 Kitsu status로 매핑합니다."""
    if not raw_status:
        return "todo"
    return _STATUS_MAP.get(raw_status.strip().lower(), "todo")


def convert(show: str, folder_filter: str, dry_run: bool = False, force: bool = False):
    """클라이언트 Excel → shots.csv + notes.csv 변환"""
    show_root = get_shows_root() / show
    from_client = show_root / "exchange" / "from_client"
    top_dirs = resolve_folder(from_client, folder_filter)

    cfg = get_project_config(show)
    fps = cfg.get("fps", 23.976)
    plates_dir = show_root / "plates"

    tag = "(DRY RUN) " if dry_run else ""
    print(f"\n[SKYFALL] Excel → CSV {tag}— {show}\n")

    for top_dir in top_dirs:
        print(f"  📂 {top_dir.name}")

        excel_path = find_excel(top_dir)
        if not excel_path:
            print(f"     (Excel 없음)")
            continue

        # CSV는 Excel이 있는 폴더에 생성
        csv_dir = excel_path.parent
        shots_csv = csv_dir / "shots.csv"
        notes_csv = csv_dir / "notes.csv"

        # 중복 실행 방지
        if not force and (shots_csv.exists() or notes_csv.exists()):
            print(f"     ⚠  CSV 이미 존재 (덮어쓰려면 --force)")
            if shots_csv.exists():
                print(f"        {shots_csv}")
            if notes_csv.exists():
                print(f"        {notes_csv}")
            continue

        print(f"  📋 Excel: {excel_path.name}")
        entries = parse_excel(excel_path)
        print(f"     {len(entries)}개 샷 파싱됨")

        if not entries:
            continue

        # ── shots.csv 생성 ──
        shots_rows = []
        for e in entries:
            shot_code = e.get("shot_code", "")

            # ffprobe로 실제 프레임 레인지 감지
            frame_in, frame_out = _detect_frame_range(plates_dir, shot_code, fps)
            if frame_in == 0:
                # plates에 없으면 Excel cut_duration으로 추정
                dur = e.get("cut_duration", "")
                if dur and dur.isdigit():
                    frame_in = 1001
                    frame_out = 1001 + int(dur) - 1

            shots_rows.append({
                "shot_code":   shot_code,
                "description": e.get("description", ""),
                "frame_in":    str(frame_in) if frame_in else "",
                "frame_out":   str(frame_out) if frame_out else "",
                "colorspace":  e.get("colorspace", ""),
            })

        # ── notes.csv 생성 ──
        notes_rows = []
        for e in entries:
            vfx_work = e.get("vfx_work", "")
            if not vfx_work:
                continue

            task, note = _extract_task(vfx_work)
            status = _map_status(e.get("status", ""))

            notes_rows.append({
                "shot_code": e.get("shot_code", ""),
                "task":      task,
                "note":      note,
                "status":    status,
                "assignee":  "",
            })

        if dry_run:
            print(f"\n     shots.csv ({len(shots_rows)}행):")
            for r in shots_rows[:3]:
                fr = f"[{r['frame_in']}-{r['frame_out']}]" if r['frame_in'] else "[미감지]"
                print(f"       {r['shot_code']}  {fr}  desc: {r['description'][:30]}...")
            if len(shots_rows) > 3:
                print(f"       ... +{len(shots_rows)-3}행")

            print(f"\n     notes.csv ({len(notes_rows)}행):")
            for r in notes_rows[:3]:
                print(f"       {r['shot_code']}  [{r['task']}] ({r['status']}) {r['note'][:30]}...")
            if len(notes_rows) > 3:
                print(f"       ... +{len(notes_rows)-3}행")
            continue

        # CSV 쓰기 (UTF-8 BOM — Excel 호환)
        with open(shots_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=_SHOTS_FIELDS)
            writer.writeheader()
            writer.writerows(shots_rows)
        print(f"  ✅ {shots_csv.name} ({len(shots_rows)}행)")

        with open(notes_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=_NOTES_FIELDS)
            writer.writeheader()
            writer.writerows(notes_rows)
        print(f"  ✅ {notes_csv.name} ({len(notes_rows)}행)")

    print(f"\n[SKYFALL] {'DRY RUN 완료' if dry_run else '✅ 완료'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKYFALL Excel → CSV 변환 (shots.csv + notes.csv)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "생성 파일:",
            "  shots.csv — shot_code, description, frame_in, frame_out, colorspace",
            "  notes.csv — shot_code, task, note, status, assignee",
            "",
            "예시:",
            "  python3 tools/convert_excel.py AAB --folder 260206",
            "  python3 tools/convert_excel.py AAB --folder 260206 --dry-run",
            "  python3 tools/convert_excel.py AAB --folder 260206 --force",
        ])
    )
    parser.add_argument("show",       help="Show 코드 (예: AAB)")
    parser.add_argument("--folder",   required=True, help="from_client 폴더")
    parser.add_argument("--force",    action="store_true", help="기존 CSV 덮어쓰기")
    parser.add_argument("--dry-run",  action="store_true", help="실제 생성 없이 확인만")
    args = parser.parse_args()

    convert(args.show, args.folder, dry_run=args.dry_run, force=args.force)
