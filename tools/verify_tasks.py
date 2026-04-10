import sys
import logging
from pathlib import Path

# Add pipeline root to sys.path
pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.env import get_token_data, get_kitsu_url
from services.kitsu import KitsuAPI

logger = logging.getLogger("skyfall.verify_tasks")


def verify_shot_tasks(shot_id: str):
    token_data = get_token_data()
    if not token_data.get("access_token"):
        print("❌ Error: Token cache not found. Please run kitsu_login.py first.")
        sys.exit(1)

    kitsu = KitsuAPI()
    base_url = get_kitsu_url()

    print(f"🕵️  Verifying tasks for Shot ID: {shot_id}")
    print(f"   Querying: {base_url}/data/tasks?entity_id={shot_id}")

    tasks = kitsu._get(f"/data/tasks?entity_id={shot_id}")

    print("\n--- RESULT ---")
    if tasks:
        import json
        print("✅ Tasks found:")
        print(json.dumps(tasks, indent=2))
    else:
        print("❌ No tasks found (empty list or request failed).")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 verify_tasks.py <SHOT_ID>")
        sys.exit(1)

    verify_shot_tasks(sys.argv[1])


if __name__ == "__main__":
    main()
