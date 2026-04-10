"""
SKYFALL Nuke Script Creator
템플릿으로 nk 파일을 생성하거나 버전업합니다.
workflow (project.yml) 에 따라 템플릿을 자동 선택합니다.

  uhd : EXR Read → Write_PUBLISH(EXR) + Write_REVIEW(MOV)
  hd  : MOV Read → Write_REVIEW(MOV)

Usage:
  # 신규 (v001, 이미 있으면 스킵)
  python3 tools/create_nk.py AAA E103_S002_0290

  # 슬레이트 포함 (UHD 전용)
  python3 tools/create_nk.py AAA E103_S002_0290 --slate

  # 새 버전 생성 (현재 최신 버전 + 1)
  python3 tools/create_nk.py AAA E103_S002_0290 --new-version

  # 전체 샷 일괄 재생성 (v001 없는 샷만)
  python3 tools/create_nk.py AAA --all

  # 전체 샷 강제 재생성 (v001 덮어쓰기)
  python3 tools/create_nk.py AAA --all --force
"""
import re
import sys
import argparse
import subprocess
from pathlib import Path

pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.env import get_shows_root, get_project_config, get_ocio_config_for_project


def _mov_frame_range(mov_path: Path, fps: float, start: int = 1001) -> tuple[int, int]:
    """
    ffprobe로 MOV 파일의 프레임 수를 읽어 (first, last) 반환합니다.
    ffprobe 실패 시 (start, start+99) 반환.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-select_streams", "v:0",
                "-count_packets",
                "-show_entries", "stream=nb_read_packets",
                "-of", "csv=p=0",
                str(mov_path),
            ],
            capture_output=True, text=True, timeout=10
        )
        nb = int(result.stdout.strip().split(",")[-1])
        return start, start + nb - 1
    except Exception:
        return start, start + 99


_TEMPLATES_DIR = pipeline_root / "apps" / "nuke" / "templates"
_VER_PAT   = re.compile(r"^v(\d+)$",       re.IGNORECASE)
_FRAME_PAT = re.compile(r"\.(\d+)\.exr$",  re.IGNORECASE)

_FORMAT_NAMES = {
    (3840, 2160): "UHD_4K",
    (4096, 2160): "DCI_4K",
    (2048, 1080): "DCI_2K",
    (1920, 1080): "HD_1080",
    (1280,  720): "HD_720",
}

def _format_name(width: int, height: int) -> str:
    return _FORMAT_NAMES.get((width, height), f"{width}x{height}")


def _select_template(workflow: str, slate: bool) -> Path:
    """workflow + slate 조합에 맞는 템플릿 파일을 반환합니다."""
    if workflow == "hd":
        name = "hd_comp.nk"
    elif slate:
        name = "uhd_comp_slate.nk"
    else:
        name = "uhd_comp.nk"
    return _TEMPLATES_DIR / name


def find_plate_path(central_plate_dir: Path, shot_code: str,
                    plate_link: Path, workflow: str = "uhd") -> str:
    """
    plates/{shot_code}/{version}/ 구조에서 최적 버전을 선택합니다.
    uhd: EXR sequence (.%04d.exr)
    hd : MOV 단일 파일 (.mov)
    우선순위: plate > org > 기타, 동일 타입이면 최신 버전 우선.
    없으면 placeholder 반환.
    """
    def _type_pri(name: str) -> int:
        return 0 if "_plate_" in name else (1 if "_org_" in name else 2)

    if central_plate_dir.exists():
        candidates = []
        for ver_dir in sorted(central_plate_dir.iterdir()):
            if not ver_dir.is_dir():
                continue
            m = _VER_PAT.match(ver_dir.name)
            if not m:
                continue
            ver_num = int(m.group(1))

            if workflow == "hd":
                # MOV 단일 파일
                mov_files = sorted(ver_dir.glob("*.mov"))
                if mov_files:
                    f = mov_files[0]
                    candidates.append((_type_pri(f.name), -ver_num, ver_dir.name, f.name))
            else:
                # EXR sequence
                exr_files = sorted(ver_dir.glob("*.exr"))
                if exr_files:
                    fm = _FRAME_PAT.search(exr_files[0].name)
                    if fm:
                        frame_len = len(fm.group(1))
                        base = _FRAME_PAT.sub(f".%0{frame_len}d.exr", exr_files[0].name)
                        candidates.append((_type_pri(base), -ver_num, ver_dir.name, base))

        if candidates:
            candidates.sort()
            _, _, ver_str, filename = candidates[0]
            return f"{plate_link.as_posix()}/{ver_str}/{filename}"

    if workflow == "hd":
        return f"{plate_link.as_posix()}/v001/{shot_code}_org_v001.mov"
    return f"{plate_link.as_posix()}/v001/{shot_code}_org_v001.%04d.exr"


def _next_nk_version(nk_dir: Path, shot_code: str) -> int:
    """comp/nk/ 에서 현재 최신 v번호 + 1 반환."""
    nums = []
    for f in nk_dir.glob(f"{shot_code}_comp_v*.nk"):
        m = re.search(r"_comp_v(\d+)\.nk$", f.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1 if nums else 1


def create_nk(show: str, shot_code: str,
              frame_in: int = 1001, frame_out: int = 1100,
              new_version: bool = False, force: bool = False,
              slate: bool = False) -> Path | None:
    """
    nk 파일을 생성합니다. 생성된 파일 Path 반환, 스킵 시 None 반환.

    new_version=True : 다음 버전 번호로 생성
    force=True       : 기존 파일 덮어쓰기
    slate=True       : 슬레이트 포함 템플릿 사용 (UHD 전용)
    """
    parts = shot_code.split("_")
    if len(parts) == 3:
        episode, sequence, shot = parts
    elif len(parts) == 2:
        episode = None
        sequence, shot = parts
    else:
        print(f"  ❌ shot_code 형식 오류: {shot_code}")
        return None

    show_root = get_shows_root() / show
    rel_path  = f"{episode}/{sequence}/{shot}" if episode else f"{sequence}/{shot}"
    shot_path = show_root / rel_path

    if not shot_path.exists():
        print(f"  ❌ 샷 폴더 없음: {shot_path}  (setup_shot 먼저 실행)")
        return None

    nk_dir    = shot_path / "comp" / "nk"
    render_dir = shot_path / "comp" / "render"
    review_dir = shot_path / "comp" / "review"
    plate_link = shot_path / "plate"
    central_plate_dir = show_root / "plates" / shot_code

    # 버전 결정
    ver_num = _next_nk_version(nk_dir, shot_code) if new_version else 1
    ver_str = f"v{ver_num:03d}"
    nk_file = nk_dir / f"{shot_code}_comp_{ver_str}.nk"

    if nk_file.exists() and not force:
        print(f"  ⏭  스킵 (이미 존재): {nk_file.name}")
        return None

    # project.yml
    cfg       = get_project_config(show)
    workflow  = cfg.get("workflow", "uhd")
    fps       = cfg.get("fps", 23.976)
    res       = cfg.get("resolution", [1920, 1080])
    width, height = (res[0], res[1]) if isinstance(res, list) else (1920, 1080)
    camera_cs = cfg.get("camera_colorspace", "Input - ARRI - V3 LogC (EI800) - Wide Gamut")
    output_cs = cfg.get("output_colorspace", "ACES - ACEScct")
    review_cs = cfg.get("review_colorspace", "Output - Rec.709")
    review_res = cfg.get("review_resolution", [1920, 1080])
    review_w, review_h = (review_res[0], review_res[1]) if isinstance(review_res, list) else (1920, 1080)

    # 폴더 생성 (워크플로우에 따라)
    review_vdir = review_dir / ver_str
    review_vdir.mkdir(parents=True, exist_ok=True)
    if workflow == "uhd":
        render_vdir = render_dir / ver_str
        render_vdir.mkdir(parents=True, exist_ok=True)
        render_path = f"{render_vdir.as_posix()}/{shot_code}_comp_{ver_str}.%04d.exr"
    else:
        render_path = ""

    plate_path  = find_plate_path(central_plate_dir, shot_code, plate_link, workflow)
    review_path = f"{review_vdir.as_posix()}/{shot_code}_comp_{ver_str}.mov"
    ocio_path   = get_ocio_config_for_project(show)

    orig_last = frame_out - frame_in + 1  # 기본값

    # HD: MOV 파일에서 실제 frame range 자동 감지
    if workflow == "hd":
        mov_files = list(central_plate_dir.rglob("*.mov"))
        if mov_files:
            frame_in, frame_out = _mov_frame_range(mov_files[0], fps, start=1001)
            orig_last = frame_out - frame_in + 1   # MOV 원본 프레임 수 (1-based)
            print(f"     ffprobe: {orig_last}프레임 [{frame_in}-{frame_out}]")

    template_path = _select_template(workflow, slate)
    if template_path.exists():
        nk_content = (template_path.read_text()
            .replace("{{SCRIPT_PATH}}",           nk_file.as_posix())
            .replace("{{FRAME_IN}}",              str(frame_in))
            .replace("{{FRAME_OUT}}",             str(frame_out))
            .replace("{{FPS}}",                   str(fps))
            .replace("{{WIDTH}}",                 str(width))
            .replace("{{HEIGHT}}",                str(height))
            .replace("{{FORMAT_NAME}}",           _format_name(width, height))
            .replace("{{OCIO_CONFIG_PATH}}",      ocio_path)
            .replace("{{PLATE_PATH}}",            plate_path)
            .replace("{{RENDER_PATH}}",           render_path)
            .replace("{{REVIEW_PATH}}",           review_path)
            .replace("{{REVIEW_WIDTH}}",          str(review_w))
            .replace("{{REVIEW_HEIGHT}}",         str(review_h))
            .replace("{{REVIEW_WIDTH_MINUS80}}",  str(review_w - 80))
            .replace("{{CAMERA_COLORSPACE}}",     camera_cs)
            .replace("{{OUTPUT_COLORSPACE}}",     output_cs)
            .replace("{{REVIEW_COLORSPACE}}",     review_cs)
            .replace("{{SHOW}}",                  show)
            .replace("{{SHOT_CODE}}",             shot_code)
            .replace("{{ORIG_LAST}}",             str(orig_last))
        )
    else:
        nk_content = (
            f"Root {{\n"
            f" name {nk_file.as_posix()}\n"
            f" first_frame {frame_in}\n"
            f" last_frame {frame_out}\n"
            f" fps {fps}\n"
            f"}}\n"
        )

    nk_file.write_text(nk_content)
    slate_tag = " [slate]" if slate and workflow == "uhd" else ""
    print(f"  📝 {nk_file.name}  [{frame_in}-{frame_out}]  {workflow}{slate_tag}")
    return nk_file


def _collect_shots(show_root: Path) -> list[str]:
    """show_root 하위 모든 샷 코드를 수집합니다. EP01/S001/0010 및 S001/0010 지원."""
    ep_pat  = re.compile(r"^E[P]?\d+$", re.IGNORECASE)
    seq_pat = re.compile(r"^S\d+$",     re.IGNORECASE)
    sht_pat = re.compile(r"^\d{4}$")

    shots = []
    for child in sorted(show_root.iterdir()):
        if not child.is_dir():
            continue
        if ep_pat.match(child.name):
            for seq_dir in sorted(child.iterdir()):
                if not seq_dir.is_dir() or not seq_pat.match(seq_dir.name):
                    continue
                for sht_dir in sorted(seq_dir.iterdir()):
                    if not sht_dir.is_dir() or not sht_pat.match(sht_dir.name):
                        continue
                    shots.append(f"{child.name}_{seq_dir.name}_{sht_dir.name}".upper())
        elif seq_pat.match(child.name):
            for sht_dir in sorted(child.iterdir()):
                if not sht_dir.is_dir() or not sht_pat.match(sht_dir.name):
                    continue
                shots.append(f"{child.name}_{sht_dir.name}".upper())
    return shots


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKYFALL Nuke Script Creator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "예시:",
            "  # 신규 nk 생성 (v001, 이미 있으면 스킵)",
            "  python3 tools/create_nk.py AAA E103_S002_0290",
            "",
            "  # 슬레이트 포함 (UHD 전용)",
            "  python3 tools/create_nk.py AAA E103_S002_0290 --slate",
            "",
            "  # 다음 버전으로 새 nk 생성 (v002, v003, ...)",
            "  python3 tools/create_nk.py AAA E103_S002_0290 --new-version",
            "",
            "  # 전체 샷 일괄 생성 (v001 없는 샷만)",
            "  python3 tools/create_nk.py AAA --all",
            "",
            "  # 전체 샷 강제 재생성 (v001 덮어쓰기)",
            "  python3 tools/create_nk.py AAA --all --force",
        ])
    )
    parser.add_argument("show",          help="Show 코드 (예: AAA)")
    parser.add_argument("shot_code",     nargs="?", help="샷 코드. --all 이면 생략 가능")
    parser.add_argument("--first",       type=int, default=1001, help="시작 프레임 (기본: 1001)")
    parser.add_argument("--last",        type=int, default=1100, help="마지막 프레임 (기본: 1100)")
    parser.add_argument("--new-version", action="store_true", help="최신 버전 + 1로 생성")
    parser.add_argument("--force",       action="store_true", help="기존 파일 덮어쓰기")
    parser.add_argument("--all",         action="store_true", help="쇼 전체 샷 일괄 처리")
    parser.add_argument("--slate",       action="store_true", help="슬레이트 포함 (UHD 전용)")
    args = parser.parse_args()

    show_root = get_shows_root() / args.show
    if not show_root.exists():
        print(f"❌ Show '{args.show}' 없음.")
        sys.exit(1)

    if args.all:
        shots = _collect_shots(show_root)
        if not shots:
            print("❌ 샷을 찾을 수 없습니다.")
            sys.exit(1)
        print(f"\n[SKYFALL] create_nk — {args.show}  ({len(shots)}샷)")
        for sc in shots:
            create_nk(args.show, sc,
                      frame_in=args.first, frame_out=args.last,
                      new_version=args.new_version, force=args.force,
                      slate=args.slate)
        print(f"\n[SKYFALL] ✅ 완료")
    else:
        if not args.shot_code:
            parser.error("shot_code 를 지정하거나 --all 을 사용하세요.")
        nk = create_nk(args.show, args.shot_code,
                       frame_in=args.first, frame_out=args.last,
                       new_version=args.new_version, force=args.force,
                       slate=args.slate)
        if nk:
            print(f"\n[SKYFALL] ✅ {nk}")
