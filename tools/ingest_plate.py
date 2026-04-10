"""
SKYFALL Plate Ingest
exchange/from_client 구조에서 plates/{shot_code}/{version}/ 로 복사합니다.

from_client/ 하위를 재귀 스캔하므로 폴더 구조가 자유롭습니다.
  260410/E103_S002_0290_org_v001/
  20241111_dataout/plate/E103_S002_0290_org_v001/
  260410_feedback/E103_S002_0290_org_v002/

Usage:
  # 폴더 목록 확인
  python3 tools/ingest_plate.py AAA --list

  # 키워드로 필터 (부분 매칭)
  python3 tools/ingest_plate.py AAA --folder 260410 --dry-run
  python3 tools/ingest_plate.py AAA --folder 260410
  python3 tools/ingest_plate.py AAA --folder dataout --dry-run

  # 전체 스캔
  python3 tools/ingest_plate.py AAA --dry-run
  python3 tools/ingest_plate.py AAA
"""
import re
import sys
import shutil
import argparse
from pathlib import Path
from datetime import datetime

pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.env import get_shows_root

# 샷 폴더/파일명 패턴: E103_S002_0290_org_v001
_FOLDER_PATTERN = re.compile(
    r"^(E[P]?\d+_S\d+_\d+)_([a-zA-Z0-9]+)_(v\d+)$",
    re.IGNORECASE,
)

# 인제스트 대상 타입 (나머지는 스킵)
_PLATE_TYPES = {"org", "plate"}

# 별도 처리 대상 타입
_EDITOR_TYPES = {"editor"}


def list_folders(from_client_root: Path):
    """from_client/ 최상위 폴더 목록을 출력합니다."""
    dirs = sorted([d for d in from_client_root.iterdir()
                   if d.is_dir() and not d.name.startswith(".")])
    if not dirs:
        print(f"  (폴더 없음)")
        return
    for d in dirs:
        print(f"  {d.name}")


def scan_delivery(from_client_root: Path, folder_filter: str = None) -> list[dict]:
    """
    from_client/ 하위를 재귀 스캔해서 _FOLDER_PATTERN 폴더를 찾습니다.
    folder_filter: 부분 문자열 매칭으로 최상위 폴더를 필터합니다.
    반환: [{ folder_label, shot_code, type, version, folder, files, file_format }, ...]
    """
    deliveries = []

    top_dirs = sorted([d for d in from_client_root.iterdir()
                       if d.is_dir() and not d.name.startswith(".")])

    if folder_filter and "/" in folder_filter:
        direct_path = from_client_root / folder_filter
        if direct_path.is_dir():
            top_dirs = [direct_path]
        else:
            print(f"[SKYFALL] ❌ 폴더 없음: {direct_path}")
            sys.exit(1)
    elif folder_filter:
        matched = [d for d in top_dirs if folder_filter in d.name]
        if not matched:
            print(f"[SKYFALL] ❌ '{folder_filter}' 포함하는 폴더가 없습니다.")
            print(f"           from_client 폴더 목록:")
            for d in top_dirs:
                print(f"             {d.name}")
            sys.exit(1)
        top_dirs = matched

    # 파일명 패턴: EP01_S004_0002_org_v001.mov / .exr
    _FILE_PATTERN = re.compile(
        r"^(E[P]?\d+_S\d+_\d+)_([a-zA-Z0-9]+)_(v\d+)\.(mov|exr)$",
        re.IGNORECASE,
    )

    def _add_delivery(shot_code, file_type, version, files, file_format, label):
        """deliveries에 추가. 중복(같은 shot+type+version) 방지."""
        key = (shot_code, file_type, version)
        if any((d["shot_code"], d["type"], d["version"]) == key for d in deliveries):
            return
        if file_type in _EDITOR_TYPES:
            deliveries.append({
                "folder_label": label,
                "shot_code":    shot_code,
                "type":         file_type,
                "version":      version,
                "folder":       files[0].parent if files else None,
                "files":        files,
                "file_format":  file_format,
                "skip":         "editor",
            })
        elif file_type in _PLATE_TYPES:
            deliveries.append({
                "folder_label": label,
                "shot_code":    shot_code,
                "type":         file_type,
                "version":      version,
                "folder":       files[0].parent if files else None,
                "files":        files,
                "file_format":  file_format,
                "skip":         None,
            })
        # 그 외 타입은 무시

    def _scan_dir(directory: Path, label: str):
        has_shot_files = False

        # ── 파일 직접 포함 구조 ───────────────────────────────
        # {shot_code}_{type}_{version}.mov 형태로 파일이 직접 있는 경우
        file_groups: dict[tuple, list] = {}
        for f in sorted(directory.iterdir()):
            if f.is_dir() or f.name.startswith("."):
                continue
            fm = _FILE_PATTERN.match(f.name)
            if fm:
                shot_code = fm.group(1).upper()
                file_type = fm.group(2).lower()
                version   = fm.group(3).lower()
                ext       = fm.group(4).lower()
                key = (shot_code, file_type, version, ext)
                file_groups.setdefault(key, []).append(f)
                has_shot_files = True

        for (shot_code, file_type, version, ext), files in sorted(file_groups.items()):
            fmt = "exr" if ext == "exr" else "mov"
            _add_delivery(shot_code, file_type, version, sorted(files), fmt, label)

        # ── 샷별 하위 폴더 구조 ──────────────────────────────
        # {shot_code}_{type}_{version}/ 폴더 안에 파일이 있는 경우
        for entry in sorted(directory.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            m = _FOLDER_PATTERN.match(entry.name)
            if m:
                shot_code = m.group(1).upper()
                file_type = m.group(2).lower()
                version   = m.group(3).lower()

                files = sorted(entry.glob("*.exr"))
                file_format = "exr"
                if not files:
                    files = sorted(entry.glob("*.mov"))
                    file_format = "mov"
                if not files:
                    continue
                _add_delivery(shot_code, file_type, version, files, file_format, label)
            elif not has_shot_files:
                # 패턴 불일치 폴더 → 재귀 (파일 직접 포함 구조가 아닐 때만)
                _scan_dir(entry, label)

    for top_dir in top_dirs:
        _scan_dir(top_dir, top_dir.name)

    return deliveries


def _update_nk_plate(show_root: Path, ep: str, seq: str, shot: str,
                     shot_code: str, actual_seq_filename: str):
    """
    comp/nk/{shot_code}_comp_v*.nk 의 Read_PLATE file 경로를
    실제 인제스트된 파일명으로 업데이트합니다.
    """
    nk_dir     = show_root / ep / seq / shot / "comp" / "nk"
    plate_link = show_root / ep / seq / shot / "plate"

    nk_files = sorted(nk_dir.glob(f"{shot_code}_comp_v*.nk")) if nk_dir.exists() else []
    if not nk_files:
        return

    new_path = f"{plate_link.as_posix()}/{actual_seq_filename}"

    for nk_file in nk_files:
        content = nk_file.read_text()
        new_content = re.sub(
            rf'(file\s+){re.escape(str(plate_link))}/[^\n]+',
            f'file {new_path}',
            content
        )
        if new_content != content:
            nk_file.write_text(new_content)
            print(f"       ✅ nk 업데이트: {nk_file.name}")
            print(f"          → plate/{actual_seq_filename}")


def ingest(show: str, folder_filter: str = None, dry_run: bool = False):
    shows_root  = get_shows_root()
    show_root   = shows_root / show
    plates_root = show_root / "plates"
    from_client = show_root / "exchange" / "from_client"

    if not from_client.exists():
        print(f"[SKYFALL] ❌ exchange/from_client 폴더 없음: {from_client}")
        sys.exit(1)

    deliveries = scan_delivery(from_client, folder_filter)

    if not deliveries:
        print(f"[SKYFALL] ❌ 인식 가능한 납품 폴더가 없습니다.")
        print(f"           샷 폴더 형식: {{shot_code}}_{{type}}_{{version}}")
        print(f"           예: E103_S002_0290_org_v001")
        sys.exit(1)

    print(f"\n[SKYFALL] Plate Ingest {'(DRY RUN) ' if dry_run else ''}— {show}")
    print(f"  from_client: {from_client}")
    print(f"  plates:      {plates_root}")
    print()

    current_label = None
    total_copied  = 0
    log_lines     = []

    for d in deliveries:
        if d["folder_label"] != current_label:
            current_label = d["folder_label"]
            print(f"  📂 {current_label}")

        shot_code   = d["shot_code"]
        file_type   = d["type"]
        version     = d["version"]
        files       = d["files"]
        file_format = d["file_format"]
        dest_dir    = plates_root / shot_code / version

        # 에디터 가이드 — 스킵 출력 후 다음으로
        if d.get("skip") == "editor":
            print(f"     {shot_code}  [{file_type}_{version}]  ⏭  editor (스킵 — Kitsu 업로드 대상)")
            log_lines.append(f"{current_label}|{shot_code}|{file_type}|{version}|{len(files)}|0|0|SKIP(editor)")
            continue

        if file_format == "exr":
            frames = [int(m.group(1)) for f in files
                      if (m := re.search(r"\.(\d+)\.exr$", f.name, re.I))]
            first, last = (min(frames), max(frames)) if frames else (0, 0)
            info = f"{len(files)}프레임  [{first}-{last}]"
        else:
            frames = []
            first = last = 0
            info = f"MOV  {len(files)}파일"

        print(f"     {shot_code}  [{file_type}_{version}]  {info}")

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            copied = skipped = 0
            for src in files:
                dest = dest_dir / src.name
                if dest.exists():
                    skipped += 1
                else:
                    shutil.copy2(src, dest)
                    copied += 1
            total_copied += copied
            status = f"복사 {copied}  스킵 {skipped}"
            if skipped:
                print(f"       → 복사 {copied}  스킵 {skipped}")
            else:
                print(f"       → {copied}개 복사 완료")
        else:
            status = "DRY RUN"

        # 샷 폴더 확인 + nk 업데이트
        parts = shot_code.split("_")
        if len(parts) == 3:
            ep, seq, shot = parts
        else:
            log_lines.append(f"{current_label}|{shot_code}|{file_type}|{version}|{len(files)}|{first}|{last}|{status}")
            continue

        plate_link = show_root / ep / seq / shot / "plate"
        if not plate_link.exists():
            print(f"       →  다음 단계: python3 tools/setup_shot.py {show} {shot_code}")
        elif not dry_run:
            if file_format == "exr":
                frame_len  = len(str(first)) if frames else 4
                actual_seq = f"{version}/{shot_code}_{file_type}_{version}.%0{frame_len}d.exr"
            else:
                actual_seq = f"{version}/{files[0].name}"
            _update_nk_plate(show_root, ep, seq, shot, shot_code, actual_seq)

        log_lines.append(f"{current_label}|{shot_code}|{file_type}|{version}|{len(files)}|{first}|{last}|{status}")

    print()

    if not dry_run and log_lines:
        log_dir   = plates_root / "ingest_log"
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file  = log_dir / f"ingest_{timestamp}.log"
        log_file.write_text(
            "folder|shot_code|type|version|files|first|last|status\n" +
            "\n".join(log_lines)
        )
        print(f"  📋 로그: {log_file}")
        print(f"[SKYFALL] ✅ 완료 — {total_copied}개 파일 복사")
    elif dry_run:
        print(f"[SKYFALL] DRY RUN 완료 — 실제 복사 없음")
        print(f"          실제 실행: --dry-run 제거")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKYFALL Plate Ingest (exchange/from_client → plates/)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "실행 순서:",
            "  1. init_show    — 쇼 생성",
            "  2. ingest_plate — 플레이트 복사",
            "  3. setup_shot   — 샷 폴더 + nk 생성",
            "  4. Nuke 열기",
            "",
            "예시:",
            "  python3 tools/ingest_plate.py AAA --list",
            "  python3 tools/ingest_plate.py AAA --folder 260410 --dry-run",
            "  python3 tools/ingest_plate.py AAA --folder 260410",
            "  python3 tools/ingest_plate.py AAA --folder dataout --dry-run",
            "  python3 tools/ingest_plate.py AAA --dry-run",
            "  python3 tools/ingest_plate.py AAA",
        ])
    )
    parser.add_argument("show",       help="Show 코드 (예: AAA)")
    parser.add_argument("--folder",   help="from_client 폴더 키워드 필터 (부분 매칭, 예: 260410, dataout)")
    parser.add_argument("--list",     action="store_true", help="from_client 폴더 목록만 출력")
    parser.add_argument("--dry-run",  action="store_true", help="실제 복사 없이 결과 미리 확인")
    args = parser.parse_args()

    from_client = get_shows_root() / args.show / "exchange" / "from_client"

    if args.list:
        print(f"\n[SKYFALL] from_client 폴더 목록 — {args.show}")
        print(f"  {from_client}\n")
        list_folders(from_client)
        sys.exit(0)

    ingest(args.show, folder_filter=args.folder, dry_run=args.dry_run)
