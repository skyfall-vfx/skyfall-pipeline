"""
SKYFALL Nuke init.py
Nuke 시작 시 자동 실행됩니다.

등록 순서:
  1. 파이프라인 공용 gizmos / scripts
  2. 현재 쇼의 config/nuke/gizmos / scripts (SKYFALL_SHOW 환경변수 기준)
"""
import nuke
import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger("skyfall.nuke.init")

# ── 파이프라인 루트 ────────────────────────────────────────
_pipeline_root = Path(__file__).resolve().parent.parent.parent
if str(_pipeline_root) not in sys.path:
    sys.path.insert(0, str(_pipeline_root))

# ── 1. 파이프라인 공용 경로 등록 ──────────────────────────
_common_gizmos  = _pipeline_root / "pipeline" / "apps" / "nuke" / "gizmos"
_common_scripts = _pipeline_root / "pipeline" / "apps" / "nuke" / "scripts"

for _p in [_common_gizmos, _common_scripts]:
    if _p.exists():
        nuke.pluginAddPath(str(_p))
        logger.debug(f"Plugin path added (common): {_p}")

# ── 2. 프로젝트별 경로 등록 ───────────────────────────────
from core.env import get_shows_root

def _register_show_paths(show: str):
    show_nuke = get_shows_root() / show / "config" / "nuke"
    for sub in ["gizmos", "scripts"]:
        p = show_nuke / sub
        if p.exists():
            nuke.pluginAddPath(str(p))
            nuke.tprint(f"[SKYFALL] Plugin path: {p}")

# SKYFALL_SHOW 환경변수가 있으면 즉시 등록
_show = os.getenv("SKYFALL_SHOW", "")
if _show:
    _register_show_paths(_show)

# 스크립트 로드 시점에도 확인 (환경변수 없이 스크립트 경로로 감지)
def _on_script_load():
    script_path = nuke.root().name()
    if not script_path or script_path == "Root":
        return

    try:
        from core import context
        ctx = context.get_current()
        if ctx.is_valid and ctx.project:
            _register_show_paths(ctx.project)
    except Exception as e:
        logger.debug(f"Show path registration skipped: {e}")

nuke.addOnScriptLoad(_on_script_load)

# ── 3. 메뉴 / 콜백 설정 ───────────────────────────────────
try:
    from apps.nuke import menu
    menu.build_menu()
    menu.setup_callbacks()
except Exception as e:
    logger.warning(f"Menu setup failed: {e}")
