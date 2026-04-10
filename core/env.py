import os
import json
import logging
from pathlib import Path

logger = logging.getLogger("skyfall.env")


def get_pipeline_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def get_token_data() -> dict:
    token_path = get_pipeline_root() / "config" / "token_cache.json"
    if not token_path.exists():
        return {}
    try:
        with open(token_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logger.warning("Token cache is malformed. Please run 'kitsu_login.py' again.")
        return {}


def get_shows_root() -> Path:
    return Path(os.getenv("SKYFALL_SHOWS_DIR", "/Volumes/skyfall/shows"))


def get_kitsu_url() -> str:
    """Kitsu API base URL. Override with KITSU_API_URL environment variable."""
    return os.getenv("KITSU_API_URL", "https://shows.skyfall.studio/api")


def get_project_config(project_name: str) -> dict:
    """
    project.yml에서 프로젝트 설정을 읽어 반환합니다.
    파일이 없거나 파싱 실패 시 빈 dict를 반환합니다.

    project.yml 예시:
        project_name: AAD
        fps: 24.0
        resolution: [1920, 1080]
        working_colorspace: ACEScg
    """
    config_path = get_shows_root() / project_name / "project.yml"
    if not config_path.exists():
        logger.debug(f"No project.yml found for '{project_name}', using defaults.")
        return {}
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # PyYAML 없으면 간단한 key: value 파서로 폴백
        return _parse_simple_yaml(config_path)
    except Exception as e:
        logger.warning(f"Could not read project.yml for '{project_name}': {e}")
        return {}


def _parse_simple_yaml(path: Path) -> dict:
    """PyYAML 없을 때 단순 key: value 형식만 파싱하는 폴백 파서."""
    result = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' in line:
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip()
                # 숫자 변환
                try:
                    if '.' in value:
                        result[key] = float(value)
                    elif value.startswith('['):
                        # 리스트 파싱: [1920, 1080]
                        items = value.strip('[]').split(',')
                        result[key] = [int(x.strip()) for x in items]
                    else:
                        result[key] = int(value)
                except (ValueError, TypeError):
                    result[key] = value
    except Exception as e:
        logger.warning(f"Fallback YAML parse failed for {path}: {e}")
    return result


_OCIO_ROOT = Path("/Volumes/skyfall/opt/skyfall-dev/config/ocio")

# 등록된 OCIO config 목록
# project.yml의 ocio_config 키로 참조
OCIO_CONFIGS = {
    "aces_ww": _OCIO_ROOT / "aces_ww" / "config.ocio",  # ww_aces_config OCIO v1 (전 쇼 공통)
}


def get_ocio_config() -> str:
    """
    전역 OCIO config 경로를 반환합니다.
    OCIO 환경변수 → current.ocio 심링크 순으로 조회합니다.
    """
    env_ocio = os.getenv("OCIO")
    if env_ocio:
        return env_ocio
    default = _OCIO_ROOT / "current.ocio"
    return str(default) if default.exists() else ""


def get_ocio_config_for_project(project_name: str) -> str:
    """
    쇼별 OCIO config 경로를 반환합니다.
    우선순위:
      1. project.yml의 ocio_config_path (쇼 내부 config/ocio/config.ocio)
      2. project.yml의 ocio_config 키 → OCIO_CONFIGS 중앙 경로
      3. 전역 OCIO 환경변수 / current.ocio 심링크

    project.yml 예시:
        ocio_config: aces_ww
        ocio_config_path: /Volumes/skyfall/shows/AAA/config/ocio/config.ocio
    """
    cfg = get_project_config(project_name)

    # 1. 쇼 내부 경로 우선
    show_path = cfg.get("ocio_config_path", "")
    if show_path and Path(show_path).exists():
        return show_path

    # 2. 중앙 config 키
    config_key = cfg.get("ocio_config", "")
    if config_key:
        path = OCIO_CONFIGS.get(config_key)
        if path and path.exists():
            return str(path)
        if path:
            logger.warning(
                f"OCIO config '{config_key}' for '{project_name}' not found at {path}."
            )

    return get_ocio_config()


def get_project_mount() -> Path:
    """DCC 독립적 프로젝트 루트 반환"""
    return get_shows_root()
