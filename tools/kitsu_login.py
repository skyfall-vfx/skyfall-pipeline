import os
import sys
import json
import logging
import requests
import getpass
from pathlib import Path

# Add pipeline root to sys.path
pipeline_root = Path(__file__).resolve().parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.env import get_pipeline_root, get_kitsu_url

logger = logging.getLogger("skyfall.kitsu_login")


def login(base_url: str, email: str, password: str):
    login_url = f"{base_url.rstrip('/')}/auth/login"
    print(f"Connecting to {login_url} ...")

    try:
        response = requests.post(
            login_url,
            json={"email": email, "password": password},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        access_token = data.get("access_token")
        if not access_token:
            print("❌ Login Failed: No access token in response.")
            logger.error(f"Login response has no access_token: {data}")
            return

        config_dir = get_pipeline_root() / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        token_file = config_dir / "token_cache.json"

        with open(token_file, "w") as f:
            json.dump({"access_token": access_token}, f, indent=4)

        # 토큰 파일을 소유자만 읽을 수 있도록 권한 설정
        os.chmod(token_file, 0o600)

        print(f"✅ Login Successful! Token saved to {token_file}")

    except requests.exceptions.ConnectionError:
        print(f"❌ Connection Error: 서버에 연결할 수 없습니다. URL을 확인하세요: {base_url}")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        if status == 401:
            print("❌ Login Failed: 이메일 또는 비밀번호가 올바르지 않습니다.")
        else:
            print(f"❌ Login Error ({status}): {e.response.text[:200]}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Login Error: {e}")


if __name__ == "__main__":
    print("=== SKYFALL Kitsu Login ===")
    default_url = get_kitsu_url()

    url = default_url
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        use_custom = input(f"Use default URL [{default_url}]? (y/n): ").lower()
        if use_custom == 'n':
            url = input("Enter API Base URL (e.g., https://example.com/api): ")

    email = input("Email: ")
    password = getpass.getpass("Password: ")
    login(url, email, password)
