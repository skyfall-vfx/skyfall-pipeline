import os
import logging
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, Any, List, Optional
from core import context

logger = logging.getLogger("skyfall.kitsu")

_REQUEST_TIMEOUT = 30  # seconds


def _make_session() -> requests.Session:
    """timeout + 자동 retry가 적용된 requests Session을 반환합니다."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class KitsuAPI:
    """
    SKYFALL Kitsu Integration (Single Source of Truth)
    Server URL: KITSU_API_URL 환경변수 또는 env.get_kitsu_url() 기본값 사용
    """
    def __init__(self):
        from core.env import get_token_data, get_kitsu_url
        self.base_url = get_kitsu_url()
        tokens = get_token_data()
        self.token = os.getenv("KITSU_ACCESS_TOKEN") or tokens.get("access_token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self._session = _make_session()

    def _require_token(self):
        if not self.token:
            raise RuntimeError(
                "Kitsu access token이 없습니다. 먼저 'python3 tools/kitsu_login.py'를 실행하세요."
            )

    def _get(self, path: str) -> list:
        self._require_token()
        try:
            response = self._session.get(
                f"{self.base_url}{path}", headers=self.headers, timeout=_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"GET {path} HTTP {e.response.status_code}: {e.response.text[:200]}")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"GET {path} 요청 실패: {e}")
            return []

    def _post(self, path: str, payload: dict) -> Optional[dict]:
        self._require_token()
        try:
            response = self._session.post(
                f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            msg = e.response.text
            if "Task already exists" in msg:
                return {"message": "Task already exists."}
            logger.error(f"POST {path} HTTP {e.response.status_code}: {msg[:200]}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"POST {path} 요청 실패: {e}")
            return None

    def _put(self, path: str, payload: dict) -> Optional[dict]:
        self._require_token()
        try:
            response = self._session.put(
                f"{self.base_url}{path}", headers=self.headers, json=payload, timeout=_REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"PUT {path} HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"PUT {path} 요청 실패: {e}")
            return None

    def get_project(self, name: str) -> Optional[Dict]:
        projects = self._get("/data/projects")
        return next((p for p in projects if p.get('name') == name or p.get('code') == name), None)

    def get_shot_data(self, project_id: str, shot_name: str,
                      episode: str = None, sequence: str = None) -> Optional[Dict]:
        """샷을 조회합니다. episode/sequence가 주어지면 정확 매칭합니다."""
        shots = self._get(f"/data/projects/{project_id}/shots")
        if not episode and not sequence:
            return next((s for s in shots if s.get('name') == shot_name), None)

        # episode/sequence의 entity id를 먼저 찾아서 parent 체인으로 정확 매칭
        entities = self._get(f"/data/entities?project_id={project_id}")
        ep_id = None
        seq_id = None
        if episode:
            ep_ent = next((e for e in entities if e.get('name') == episode), None)
            ep_id = ep_ent['id'] if ep_ent else None
        if sequence:
            seq_ent = next((e for e in entities
                           if e.get('name') == sequence
                           and e.get('parent_id') == ep_id), None)
            seq_id = seq_ent['id'] if seq_ent else None

        parent_id = seq_id or ep_id
        return next((s for s in shots
                     if s.get('name') == shot_name
                     and s.get('parent_id') == parent_id), None)

    def _get_entity_types(self) -> dict:
        types = self._get("/data/entity-types")
        return {t['name'].lower(): t['id'] for t in types}

    def get_or_create_entity(self, project_id: str, name: str, type_id: str,
                              parent_id: str = None, extra_data: dict = None) -> Optional[dict]:
        entities = self._get(f"/data/entities?project_id={project_id}")
        existing = next(
            (e for e in entities
             if e['name'] == name
             and e.get('parent_id') == parent_id
             and e.get('entity_type_id') == type_id),
            None
        )
        if existing:
            return existing

        payload = {"project_id": project_id, "name": name, "entity_type_id": type_id}
        if parent_id:
            payload["parent_id"] = parent_id
        if extra_data:
            payload["data"] = extra_data

        result = self._post("/data/entities", payload)
        if result:
            logger.info(f"Kitsu Entity Created: {name}")
            print(f"[SKYFALL] Kitsu Entity Created: {name}")
        return result

    def _get_task_statuses(self) -> dict:
        statuses = self._get("/data/task-status")
        if not statuses:
            statuses = self._get("/data/task-statuses")
        return {s['short_name'].lower(): s['id'] for s in statuses}

    def _get_task_types(self) -> dict:
        types = self._get("/data/task-types")
        return {t['name'].lower(): t['id'] for t in types}

    def _ensure_project_task_types(self, project_id: str, task_type_ids: list):
        """프로젝트에 Task Type을 등록하여 Kitsu UI 컬럼이 표시되도록 합니다."""
        current = self._get(f"/data/projects/{project_id}/task-types")
        existing_ids = {t['id'] for t in current if isinstance(t, dict) and 'id' in t}

        added = 0
        for t_id in task_type_ids:
            if t_id in existing_ids:
                continue
            try:
                r = self._session.post(
                    f"{self.base_url}/data/projects/{project_id}/settings/task-types",
                    headers=self.headers,
                    json={"task_type_id": t_id},
                    timeout=_REQUEST_TIMEOUT,
                )
                if r.status_code in (200, 201):
                    added += 1
                else:
                    logger.warning(f"Task type {t_id} 등록 실패: {r.status_code} {r.text[:100]}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Task type {t_id} 등록 중 오류: {e}")

        if added > 0:
            print(f"[SKYFALL] Project task types registered: {added} added.")

    def _get_shot_tasks(self, shot_id: str) -> list:
        """샷에 연결된 태스크 조회."""
        try:
            r = self._session.get(
                f"{self.base_url}/data/shots/{shot_id}/tasks",
                headers=self.headers,
                timeout=_REQUEST_TIMEOUT,
            )
            if r.status_code == 200:
                result = r.json()
                return result if isinstance(result, list) else []
            else:
                logger.warning(f"Shot tasks 조회 실패 (Status {r.status_code})")
                return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Shot tasks 조회 중 오류: {e}")
            return []

    def _create_task_for_shot(self, project_id: str, shot_id: str, task_type_id: str) -> bool:
        """샷에 태스크를 생성합니다."""
        try:
            r = self._session.post(
                f"{self.base_url}/actions/projects/{project_id}/task-types/{task_type_id}/shots/create-tasks",
                headers=self.headers,
                json={},
                timeout=_REQUEST_TIMEOUT,
            )
            if r.status_code in (200, 201):
                result = r.json()
                if isinstance(result, list):
                    created = [t for t in result if t.get('entity_id') == shot_id]
                    return len(created) > 0
                return True
            else:
                logger.warning(f"create-tasks 실패: {r.status_code} {r.text[:150]}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Task 생성 중 오류: {e}")
            return False

    def assign_default_tasks(self, project_id: str, shot_id: str, extra_tasks: list = None):
        task_types = self._get_task_types()
        task_statuses = self._get_task_statuses()
        todo_status_id = task_statuses.get('todo') or task_statuses.get('rts')

        # 기본 Task Type + 추가 태스크
        standard_tasks = ['compositing']
        if extra_tasks:
            for t in extra_tasks:
                if t not in standard_tasks:
                    standard_tasks.append(t)
        matched_ids = [task_types[n] for n in standard_tasks if n in task_types]

        self._ensure_project_task_types(project_id, matched_ids)

        existing_tasks = self._get_shot_tasks(shot_id)
        existing_type_ids = {
            t.get('task_type_id') for t in existing_tasks
            if isinstance(t, dict) and t.get('task_type_id')
        }

        for t_name in standard_tasks:
            t_id = task_types.get(t_name)
            if not t_id:
                logger.warning(f"Task type '{t_name}' not found on server. Skipping.")
                print(f"[SKYFALL] ⚠️  Task type '{t_name}' not found on server.")
                continue

            if t_id in existing_type_ids:
                print(f"[SKYFALL] Task '{t_name.upper()}' already exists.")
            else:
                ok = self._create_task_for_shot(project_id, shot_id, t_id)
                if ok:
                    print(f"[SKYFALL] ✅ Task Created: '{t_name.upper()}' -> TODO")
                else:
                    print(f"[SKYFALL] ❌ Failed to create Task '{t_name.upper()}'")

    def get_or_create_shot(self, project_name: str, episode: str, sequence: str, shot: str,
                            frame_in: int = 1001, frame_out: int = 1100,
                            extra_tasks: list = None) -> Optional[dict]:
        """
        Episode -> Sequence -> Shot 계층을 Kitsu에 생성합니다 (없으면).
        토큰이 없으면 RuntimeError를 발생시킵니다.
        """
        self._require_token()

        print(f"[SKYFALL] Syncing Kitsu: {project_name} / {episode} / {sequence} / {shot}...")

        proj = self.get_project(project_name)
        if not proj:
            print(f"[SKYFALL] ❌ Project '{project_name}' not found in Kitsu. Please create it first.")
            return None

        proj_id = proj['id']
        types = self._get_entity_types()
        ep_type = types.get('episode')
        seq_type = types.get('sequence')
        shot_type = types.get('shot')

        parent_id = None

        if episode and ep_type:
            ep_ent = self.get_or_create_entity(proj_id, episode, ep_type)
            parent_id = ep_ent['id'] if ep_ent else None

        if sequence and seq_type:
            seq_ent = self.get_or_create_entity(proj_id, sequence, seq_type, parent_id)
            parent_id = seq_ent['id'] if seq_ent else parent_id

        shot_ent = None
        if shot and shot_type:
            shot_ent = self.get_or_create_entity(
                proj_id, shot, shot_type, parent_id,
                extra_data={"frame_in": frame_in, "frame_out": frame_out}
            )

        if shot_ent and shot_ent.get('id'):
            # 기존 샷도 frame_in/frame_out 업데이트
            self.update_shot_data(shot_ent['id'], {"frame_in": frame_in, "frame_out": frame_out})
            self.assign_default_tasks(proj_id, shot_ent['id'], extra_tasks=extra_tasks)

        return shot_ent

    def update_shot_description(self, shot_id: str, description: str) -> bool:
        """샷의 description을 업데이트합니다."""
        result = self._put(f"/data/entities/{shot_id}", {"description": description})
        return result is not None

    def update_shot_data(self, shot_id: str, data: dict) -> bool:
        """샷의 data 필드를 업데이트합니다 (frame_in, frame_out 등)."""
        result = self._put(f"/data/entities/{shot_id}", {"data": data})
        return result is not None

    def get_task_for_shot(self, shot_id: str, task_type_name: str = "compositing") -> Optional[Dict]:
        """샷에 연결된 특정 타입의 태스크를 반환합니다."""
        tasks = self._get_shot_tasks(shot_id)
        task_types = self._get_task_types()
        target_id = task_types.get(task_type_name.lower())
        if not target_id:
            return None
        return next(
            (t for t in tasks if t.get("task_type_id") == target_id),
            None
        )

    def set_main_preview(self, shot_id: str, preview_id: str) -> bool:
        """샷의 메인 썸네일을 preview로 설정합니다."""
        result = self._put(f"/data/entities/{shot_id}", {"preview_file_id": preview_id})
        return result is not None

    def get_comments(self, task_id: str) -> list:
        """태스크의 기존 comment 목록을 반환합니다."""
        return self._get(f"/data/tasks/{task_id}/comments") or []

    def add_comment(self, task_id: str, text: str, status_name: str = "todo") -> Optional[Dict]:
        """태스크에 코멘트를 추가합니다."""
        statuses = self._get_task_statuses()
        status_id = statuses.get(status_name) or statuses.get("rts")
        payload = {"task_status_id": status_id, "comment": text}
        return self._post(f"/actions/tasks/{task_id}/comment", payload)

    def publish_preview(self, task_id: str, comment_text: str, file_path: str,
                        status_name: str = "todo") -> Optional[str]:
        """태스크에 comment + preview를 한번에 publish합니다. (revision 자동 생성)"""
        self._require_token()
        statuses = self._get_task_statuses()
        status_id = statuses.get(status_name) or statuses.get("rts")

        url = f"{self.base_url}/actions/tasks/{task_id}/comment"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            with open(file_path, "rb") as f:
                data = {"task_status_id": status_id, "text": comment_text}
                files = {"file": (Path(file_path).name, f, "video/quicktime")}
                r = self._session.post(url, headers=headers, data=data, files=files, timeout=120)
            if r.status_code in (200, 201):
                result = r.json()
                previews = result.get("previews", [])
                preview_id = previews[0].get("id") if previews else None
                logger.info(f"Published preview: {file_path} (id={preview_id})")
                return preview_id
            else:
                logger.error(f"Publish failed: {r.status_code} {r.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Publish error: {e}")
            return None

    def upload_preview(self, task_id: str, comment_id: str, file_path: str) -> Optional[str]:
        """
        코멘트에 preview를 업로드합니다.
        1단계: add-preview로 preview 엔티티 생성
        2단계: /pictures/preview-files/{id}로 실제 파일 업로드 (인코딩 트리거)
        """
        self._require_token()
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            # 1. preview 엔티티 생성
            url1 = f"{self.base_url}/actions/tasks/{task_id}/comments/{comment_id}/add-preview"
            r1 = self._session.post(url1, headers=headers, json={}, timeout=_REQUEST_TIMEOUT)
            if r1.status_code not in (200, 201):
                logger.error(f"add-preview failed: {r1.status_code} {r1.text[:200]}")
                return None
            preview_id = r1.json().get("id")

            # 2. 실제 파일 업로드 (인코딩 트리거)
            url2 = f"{self.base_url}/pictures/preview-files/{preview_id}"
            with open(file_path, "rb") as f:
                files = {"file": (Path(file_path).name, f, "video/quicktime")}
                r2 = self._session.post(url2, headers=headers, files=files, timeout=300)
            if r2.status_code in (200, 201):
                logger.info(f"Preview uploaded: {file_path} (id={preview_id})")
                return preview_id
            else:
                logger.error(f"File upload failed: {r2.status_code} {r2.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Preview upload error: {e}")
            return None

    def get_preview_status(self, preview_id: str) -> str:
        """preview 인코딩 상태를 반환합니다. (processing, ready, broken)"""
        try:
            r = self._session.get(
                f"{self.base_url}/data/preview-files/{preview_id}",
                headers=self.headers, timeout=_REQUEST_TIMEOUT,
            )
            if r.status_code == 200:
                return r.json().get("status", "unknown")
        except requests.exceptions.RequestException:
            pass
        return "unknown"

    def wait_for_preview(self, preview_id: str, timeout: int = 300, interval: int = 3) -> bool:
        """preview 인코딩이 완료될 때까지 대기합니다."""
        import time
        elapsed = 0
        while elapsed < timeout:
            status = self.get_preview_status(preview_id)
            if status == "ready":
                return True
            if status == "broken":
                logger.error(f"Preview encoding failed: {preview_id}")
                return False
            time.sleep(interval)
            elapsed += interval
        logger.error(f"Preview encoding timeout ({timeout}s): {preview_id}")
        return False

    def sync_dcc_settings(self):
        ctx = context.get_current()
        if not ctx.is_valid:
            return

        project = self.get_project(ctx.project)
        if not project:
            return

        shot = self.get_shot_data(project['id'], ctx.shot, episode=ctx.episode, sequence=ctx.sequence)
        if not shot:
            return

        data = shot.get('data', {})
        f_start = int(data.get('frame_in', 1001))
        f_end = int(data.get('frame_out', 1100))
        fps = float(project.get('fps', 24))

        try:
            import nuke
            nuke.root()['first_frame'].setValue(f_start)
            nuke.root()['last_frame'].setValue(f_end)
            nuke.root()['fps'].setValue(fps)
            print(f"[SKYFALL] Nuke Project Synced: {f_start}-{f_end} @ {fps}fps")
        except ImportError:
            pass
