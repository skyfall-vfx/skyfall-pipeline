import os
import sys
import argparse
from pathlib import Path

pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.env import get_shows_root, get_project_config, OCIO_CONFIGS
from services.kitsu import KitsuAPI


def setup_show_ocio(show_root: Path, ocio_config_key: str):
    """
    쇼 내부 config/ocio/config.ocio 를 생성합니다.
    LUT는 복사하지 않고 중앙 경로를 절대경로로 참조합니다.
    """
    src_config = OCIO_CONFIGS.get(ocio_config_key)
    if not src_config or not src_config.exists():
        print(f"[SKYFALL] ⚠️  OCIO config '{ocio_config_key}' 없음.")
        return None

    dst_dir = show_root / "config" / "ocio"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_config = dst_dir / "config.ocio"

    if dst_config.exists():
        print(f"[SKYFALL] OCIO config 이미 존재: {dst_config}")
        return dst_config

    luts_abs = str(src_config.parent / "luts")
    content = src_config.read_text()
    content = content.replace("search_path: luts", f"search_path: {luts_abs}")

    dst_config.write_text(content)
    print(f"[SKYFALL] OCIO config 생성: {dst_config}")
    return dst_config


def create_kitsu_project(show_name: str, fps: str, resolution: str) -> bool:
    kitsu = KitsuAPI()
    existing = kitsu.get_project(show_name)
    if existing:
        print(f"[SKYFALL] Kitsu: 프로젝트 '{show_name}' 이미 존재합니다.")
        return True

    result = kitsu._post("/data/projects", {
        "name": show_name,
        "production_type": "tvshow",
        "production_style": "vfx",
        "fps": fps,
        "resolution": resolution,
    })

    if result and result.get("id"):
        print(f"[SKYFALL] ✅ Kitsu: 프로젝트 '{show_name}' 생성 완료 (ID: {result['id']})")
        return True
    else:
        print(f"[SKYFALL] ❌ Kitsu: 프로젝트 생성 실패")
        return False


def init_show(show_name: str, fps: float, resolution: list,
              ocio_config: str, camera: str,
              output_colorspace: str, output_compressor: str, output_bit_depth: int,
              review_colorspace: str, review_resolution: list,
              workflow: str = "uhd",
              shows_dir: str = None):

    shows_root = Path(shows_dir) if shows_dir else get_shows_root()
    show_root = shows_root / show_name

    if show_root.exists():
        print(f"[SKYFALL] Warning: Show '{show_name}' already exists at {show_root}")

    # 1. 폴더 생성
    folders = [
        "assets/2D", "assets/3D",
        "config/luts", "config/ocio",
        "config/nuke/gizmos", "config/nuke/scripts",
        "dailies", "deliveries",
        "editorial/xml", "editorial/offline",
        "exchange/from_client", "exchange/to_client", "exchange/vendor",
        "plates/ingest_log", "scripts",
    ]
    for f in folders:
        (show_root / f).mkdir(parents=True, exist_ok=True)
        print(f"Created: {show_root / f}")

    # 2. project.yml 생성
    config_file = show_root / "project.yml"
    if not config_file.exists():
        yaml_content = f"""\
# SKYFALL Pipeline Project Config
project_name: {show_name}
fps: {fps}
resolution: [{resolution[0]}, {resolution[1]}]
working_colorspace: ACEScg

# OCIO config (aces_ww: ww_aces_config OCIO v1)
ocio_config: {ocio_config}

# 카메라 입력 색공간 (ww_aces_config OCIO v1 기준)
# 주요 옵션:
#   ARRI Alexa 35 (V4):  "Input - ARRI - V4 LogC (EI800) - Wide Gamut4"
#   ARRI Alexa (V3):     "Input - ARRI - V3 LogC (EI800) - Wide Gamut"
#   Sony Venice/FX:      "Input - Sony - S-Log3 - S-Gamut3.Cine"
#   RED:                 "Input - RED - REDLog3G10 - REDWideGamutRGB"
#   Canon:               "Input - Canon - Canon-Log2 - Cinema Gamut Daylight"
#   Blackmagic:          "Input - BMD - BMDFilm WideGamut Gen5"
camera_colorspace: {camera}

# EXR 납품 출력
# 옵션: "ACES - ACES2065-1" | "ACES - ACEScct" | "Output - Rec.709"
output_colorspace: {output_colorspace}
output_compressor: {output_compressor}
output_bit_depth: {output_bit_depth}

# MOV 리뷰 출력 (Dailies / Client)
review_colorspace: {review_colorspace}
review_resolution: [{review_resolution[0]}, {review_resolution[1]}]
review_fps: {fps}

# 워크플로우: uhd (EXR Read/Write + MOV Review) | hd (MOV Read/Write)
workflow: {workflow}
"""
        config_file.write_text(yaml_content)
        print(f"Created: {config_file}")

    # 3. 쇼 내부 OCIO config 생성
    show_ocio = setup_show_ocio(show_root, ocio_config)
    if show_ocio:
        yml_text = config_file.read_text()
        if "ocio_config_path" not in yml_text:
            yml_text = yml_text.replace(
                f"ocio_config: {ocio_config}",
                f"ocio_config: {ocio_config}\nocio_config_path: {show_ocio.as_posix()}"
            )
            config_file.write_text(yml_text)

    print(f"\n[SKYFALL] ✅ Local show initialized: {show_name}")

    # 4. Kitsu 프로젝트 생성
    print(f"\n[SKYFALL] Syncing with Kitsu...")
    try:
        create_kitsu_project(show_name, str(fps), f"{resolution[0]}x{resolution[1]}")
    except RuntimeError as e:
        print(f"[SKYFALL] ⚠️  Kitsu 연동 건너뜀: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKYFALL Show 초기화",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join([
            "예시:",
            "  # 넷플릭스 (4K, ACES2065-1)",
            "  python3 init_show.py AAA \\",
            "    --fps 23.976 --resolution 3840x2160 \\",
            "    --camera 'ACES - ACES2065-1' \\",
            "    --output-colorspace 'ACES - ACES2065-1' \\",
            "    --review-resolution 1920x1080",
            "",
            "  # HD 드라마 (1080p, Rec.709)",
            "  python3 init_show.py BBB \\",
            "    --fps 23.976 --resolution 1920x1080 \\",
            "    --camera 'Input - ARRI - V3 LogC (EI800) - Wide Gamut' \\",
            "    --output-colorspace 'Output - Rec.709' \\",
            "    --review-resolution 1920x1080",
        ])
    )
    parser.add_argument("show_name", help="Show 코드 (예: AAA)")
    parser.add_argument("--fps", type=float, required=True,
                        help="FPS (예: 23.976, 29.97, 24)")
    parser.add_argument("--resolution", required=True,
                        help="작업 해상도 (예: 3840x2160, 1920x1080)")
    parser.add_argument("--camera", required=True,
                        help="카메라 입력 색공간 (OCIO colorspace 이름)")
    parser.add_argument("--output-colorspace", dest="output_colorspace", required=True,
                        help="EXR 납품 출력 색공간 (예: 'ACES - ACES2065-1', 'ACES - ACEScct')")
    parser.add_argument("--review-colorspace", dest="review_colorspace",
                        default="Output - Rec.709",
                        help="MOV 리뷰 색공간 (기본: 'Output - Rec.709')")
    parser.add_argument("--review-resolution", dest="review_resolution",
                        default="1920x1080",
                        help="MOV 리뷰 해상도 (기본: 1920x1080)")
    parser.add_argument("--ocio-config", dest="ocio_config",
                        choices=list(OCIO_CONFIGS.keys()),
                        default="aces_ww",
                        help="OCIO config (기본: aces_ww)")
    parser.add_argument("--output-compressor", dest="output_compressor",
                        default="zip1",
                        help="EXR 압축 방식 (기본: zip1)")
    parser.add_argument("--output-bit-depth", dest="output_bit_depth",
                        type=int, default=16,
                        help="EXR 비트뎁스 (기본: 16)")
    parser.add_argument("--workflow", dest="workflow",
                        choices=["uhd", "hd"], default="uhd",
                        help="워크플로우: uhd (EXR+MOV) | hd (MOV only, 기본: uhd)")
    args = parser.parse_args()

    try:
        w, h = args.resolution.lower().split("x")
        resolution = [int(w), int(h)]
    except ValueError:
        print("❌ Error: 해상도 형식 오류. 예: 3840x2160")
        sys.exit(1)

    try:
        rw, rh = args.review_resolution.lower().split("x")
        review_resolution = [int(rw), int(rh)]
    except ValueError:
        print("❌ Error: 리뷰 해상도 형식 오류. 예: 1920x1080")
        sys.exit(1)

    init_show(
        show_name=args.show_name,
        fps=args.fps,
        resolution=resolution,
        ocio_config=args.ocio_config,
        camera=args.camera,
        output_colorspace=args.output_colorspace,
        output_compressor=args.output_compressor,
        output_bit_depth=args.output_bit_depth,
        review_colorspace=args.review_colorspace,
        review_resolution=review_resolution,
        workflow=args.workflow,
    )
