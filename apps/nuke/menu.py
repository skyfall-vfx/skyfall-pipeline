import nuke
import os
import logging
from pathlib import Path

logger = logging.getLogger("skyfall.menu")


def _build_gizmo_menu(parent_menu, gizmo_dir: Path):
    """gizmo_dir 안의 .gizmo / .nk 파일을 메뉴에 등록합니다."""
    if not gizmo_dir.exists():
        return
    for f in sorted(gizmo_dir.iterdir()):
        if f.suffix in (".gizmo", ".nk") and not f.name.startswith("."):
            name = f.stem
            path_str = str(f)
            parent_menu.addCommand(
                name,
                f"nuke.createNode('{name}')" if f.suffix == ".gizmo"
                else f"nuke.nodePaste('{path_str}')"
            )


def build_menu():
    main_menu = nuke.menu("Nuke")
    sky_menu = main_menu.addMenu("SKYFALL")

    # Pipeline
    sky_menu.addCommand("Pipeline/Check Context",
        "from core import context; nuke.message(str(context.get_current().to_dict()))")
    sky_menu.addCommand("Pipeline/Sync from Kitsu",
        "from services import kitsu; kitsu.KitsuAPI().sync_dcc_settings()")

    sky_menu.addCommand("-", "", "")

    # Asset Management
    sky_menu.addCommand("Asset/Load Plate",
        "from apps.nuke import loader; loader.load_plate()")

    # Publish
    sky_menu.addCommand("Publish/Check Assets",
        "from apps.nuke import validator; validator.run_manual()")
    sky_menu.addCommand("Publish/Smart Publish",
        "nuke.message('Validator Initializing...')")

    sky_menu.addCommand("-", "", "")

    # 공용 파이프라인 Gizmos
    pipeline_root = Path(__file__).resolve().parent.parent
    common_gizmos = pipeline_root / "apps" / "nuke" / "gizmos"
    if common_gizmos.exists():
        gizmo_menu = sky_menu.addMenu("Gizmos/Common")
        _build_gizmo_menu(gizmo_menu, common_gizmos)

    # 프로젝트별 Gizmos (스크립트 로드 후 컨텍스트 확인)
    _refresh_project_gizmo_menu(sky_menu)

def _refresh_project_gizmo_menu(sky_menu=None):
    """현재 쇼의 config/nuke/gizmos 를 SKYFALL > Gizmos/Project 메뉴에 등록합니다."""
    try:
        from core import context
        from core.env import get_shows_root
        ctx = context.get_current()
        if not (ctx.is_valid and ctx.project):
            return
        show_gizmos = get_shows_root() / ctx.project / "config" / "nuke" / "gizmos"
        show_scripts = get_shows_root() / ctx.project / "config" / "nuke" / "scripts"

        if sky_menu is None:
            sky_menu = nuke.menu("Nuke").findItem("SKYFALL")
        if not sky_menu:
            return

        # 기존 항목 교체 방지: 프로젝트 메뉴를 항상 새로 만듦
        label = f"Gizmos/{ctx.project}"
        proj_menu = sky_menu.addMenu(label)
        _build_gizmo_menu(proj_menu, show_gizmos)

        label_s = f"Scripts/{ctx.project}"
        script_menu = sky_menu.addMenu(label_s)
        _build_gizmo_menu(script_menu, show_scripts)

    except Exception as e:
        logger.debug(f"Project gizmo menu skipped: {e}")


def setup_callbacks():
    """
    On Script Load: Auto Sync Context and Settings
    beforeRender: Strict Validation
    """
    from services import kitsu
    from apps.nuke import validator
    
    def on_load_sync():
        # Only sync if script is NOT "Root" (saved)
        if nuke.root().name() == "Root":
            return
        try:
            kitsu.KitsuAPI().sync_dcc_settings()
        except RuntimeError as e:
            # 토큰 없음 등 예상된 에러 — 조용히 로그만
            logger.debug(f"Kitsu sync skipped: {e}")
        except Exception as e:
            logger.warning(f"Kitsu sync failed on script load: {e}")
    
    nuke.addOnScriptLoad(on_load_sync)
    nuke.addOnScriptLoad(_refresh_project_gizmo_menu)

    # Strict Validator: Hook to all Write nodes
    nuke.addBeforeRender(validator.validate_render)
