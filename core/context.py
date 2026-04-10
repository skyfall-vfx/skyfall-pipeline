import os
import re
from pathlib import Path

class Context:
    """
    SKYFALL 2026: DCC-Agnostic Context Handler
    Determines Project, Episode, Sequence, and Shot from the environment or path.
    """
    def __init__(self, path=None):
        self.path = Path(path or os.getcwd()).as_posix()
        self.project = os.getenv("SKYFALL_PROJECT")
        self.episode = os.getenv("SKYFALL_EPISODE")
        self.sequence = os.getenv("SKYFALL_SEQUENCE")
        self.shot = os.getenv("SKYFALL_SHOT")
        
        if not all([self.project, self.shot]):
            self._parse_from_path()

    def _parse_from_path(self):
        # SKYFALL structure:
        #   With episode:    /shows/SHOW/EP01/SEQ/SHOT/...  (일반: EP + 숫자)
        #                    /shows/SHOW/E101/SEQ/SHOT/...  (Netflix: E + 3자리)
        #   Without episode: /shows/SHOW/SEQ/SHOT/...
        # Episode 코드: EP01, EP03, E101, E102 등 E[P]?\d+ 패턴
        ep_pattern = r"/(projects|shows)/([^/]+)/(E[P]?\d+)/([^/]+)/([^/]+)"
        match = re.search(ep_pattern, self.path)
        if match:
            self.project = match.group(2)
            self.episode = match.group(3)
            self.sequence = match.group(4)
            self.shot = match.group(5)
            return

        # No episode level: /shows/SHOW/SEQ/SHOT/...
        pattern_simple = r"/(projects|shows)/([^/]+)/([^/]+)/([^/]+)"
        match_s = re.search(pattern_simple, self.path)
        if match_s:
            self.project = match_s.group(2)
            self.sequence = match_s.group(3)
            self.shot = match_s.group(4)

    @property
    def is_valid(self):
        return all([self.project, self.sequence, self.shot])

    @property
    def shot_code(self):
        """EP01_S000_0000 형태의 샷 코드 반환"""
        if self.episode:
            return f"{self.episode}_{self.sequence}_{self.shot}"
        return f"{self.sequence}_{self.shot}"

    def get_shot_root(self):
        if not self.is_valid: return None
        from core.env import get_shows_root
        mount = get_shows_root()

        if self.episode:
            return f"{mount}/{self.project}/{self.episode}/{self.sequence}/{self.shot}"
        else:
            return f"{mount}/{self.project}/{self.sequence}/{self.shot}"

    def to_dict(self):
        return {
            "project": self.project,
            "episode": self.episode,
            "sequence": self.sequence,
            "shot": self.shot
        }

def get_current():
    # Detect if we are in Nuke
    try:
        import nuke
        if nuke.root().name() != "Root":
            return Context(nuke.root().name())
    except ImportError:
        pass
    
    # Detect if we are in Maya
    try:
        import maya.cmds as cmds
        scene = cmds.file(q=True, sn=True)
        if scene:
            return Context(scene)
    except ImportError:
        pass

    return Context()
