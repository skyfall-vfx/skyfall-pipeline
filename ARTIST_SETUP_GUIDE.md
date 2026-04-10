# SKYFALL Pipeline 2026
## 아티스트 설치 가이드

**대상:** 합성 아티스트 (Nuke 사용자)  
**소요 시간:** 약 3분  
**작성일:** 2026-04-09

---

## 준비 사항

- Mac 또는 Linux 머신
- 공유 스토리지 `/Volumes/skyfall` 마운트 확인
- Kitsu 계정 (PM에게 문의)

---

## Step 1 — 파이프라인 설치 (최초 1회)

터미널을 열고 아래 명령어 **한 줄**을 복사해서 실행합니다.

```bash
bash /Volumes/skyfall/opt/skyfall-dev/setup_artist.sh
```

성공하면 아래와 같이 출력됩니다:

```
╔══════════════════════════════════════════╗
║    SKYFALL Pipeline 2026 — Artist Setup  ║
╚══════════════════════════════════════════╝

✅ Pipeline found: /Volumes/skyfall/opt/skyfall-dev/pipeline
✅ init.py: SKYFALL 경로 추가됨
✅ menu.py: SKYFALL 메뉴 코드 추가됨

🎉 설정 완료! Nuke를 재시작하면 SKYFALL 메뉴가 나타납니다.
```

> 이미 설치된 상태에서 다시 실행해도 중복 추가되지 않습니다. 안전합니다.

---

## Step 2 — Kitsu 로그인 (최초 1회)

파이프라인이 Kitsu 서버에 접근하려면 로그인이 필요합니다.  
아래 명령어를 터미널에서 실행하세요:

```bash
python3 /Volumes/skyfall/opt/skyfall-dev/pipeline/tools/kitsu_login.py
```

```
=== SKYFALL Kitsu Login ===
Use default URL [https://shows.skyfall.studio/api]? (y/n): y
Email: artist@skyfall.studio
Password:
✅ Login Successful!
```

> 로그인 후 토큰이 저장되어 이후 자동으로 사용됩니다.  
> 토큰은 본인 컴퓨터에만 저장되며 다른 사람과 공유되지 않습니다.

---

## Step 3 — Nuke 실행 및 확인

Nuke를 재시작합니다. 상단 메뉴에 **SKYFALL** 메뉴가 나타나면 설치 완료입니다.

```
Nuke 메뉴바: File  Edit  Layout  Cache  ...  SKYFALL  Help
                                                ↑
                                          이게 보이면 성공!
```

---

## SKYFALL 메뉴 사용법

### Pipeline

| 메뉴 항목 | 설명 |
|---|---|
| Check Context | 현재 스크립트가 어떤 샷으로 인식되는지 확인 |
| Sync from Kitsu | Kitsu에서 FPS / 프레임 범위를 다시 불러옴 |

### Asset

| 메뉴 항목 | 설명 |
|---|---|
| Load Plate | 현재 샷의 플레이트를 자동으로 Read 노드로 불러옴 |

### Publish

| 메뉴 항목 | 설명 |
|---|---|
| Check Assets | 렌더 전 파일명/해상도/프레임/포맷 검증 |

---

## 작업 방법 (일반 워크플로)

### 1. 올바른 위치에 Nuke 스크립트 저장

반드시 아래 경로에 저장해야 파이프라인이 샷을 인식합니다:

```
/Volumes/skyfall/shows/{쇼}/{에피소드}/{시퀀스}/{샷}/comp/nk/스크립트명.nk
```

**예시:**
```
/Volumes/skyfall/shows/AAD/EP01/S010/0010/comp/nk/EP01_S010_0010_comp_v001.nk
```

> setup_shot.py로 샷을 셋업하면 이 경로와 기본 Nuke 스크립트가 자동 생성됩니다.  
> PM 또는 파이프라인 TD에게 문의하세요.

### 2. Nuke 스크립트 열기

스크립트를 열면 자동으로:
- 프레임 범위 동기화 (Kitsu 기준)
- FPS 적용 (23.976 등 프로젝트 설정)

### 3. 플레이트 로드

```
SKYFALL → Asset → Load Plate
```

`plate/` 폴더에 있는 가장 높은 버전의 플레이트를 자동 로드합니다.

### 4. 렌더 출력 경로 규칙

렌더 Write 노드의 출력 경로는 아래 규칙을 따라야 합니다:

```
.../comp/render/v001/EP01_S010_0010_comp_v001.%04d.exr
```

| 규칙 | 예시 |
|---|---|
| 버전 폴더 필수 | `/v001/`, `/v002/` ... |
| 파일명 = 샷코드_작업명_버전 | `EP01_S010_0010_comp_v001` |
| 포맷 = EXR 전용 | `.exr` |
| 비트뎁스 = 16bit half 이상 | 32bit float 도 가능 |

### 5. 렌더 전 검증

```
SKYFALL → Publish → Check Assets
```

문제가 있으면 구체적인 이유와 함께 표시됩니다.  
모든 항목 통과 후 렌더하세요.

---

## 자주 생기는 문제

**Q. SKYFALL 메뉴가 안 보여요.**  
→ setup_artist.sh를 실행했는지 확인하고 Nuke를 완전히 재시작하세요.

---

**Q. `[SKYFALL] Failed to load menu` 메시지가 뜨면서 메뉴가 안 나와요.**  
→ 스토리지가 마운트되었는지 확인하세요:
```bash
ls /Volumes/skyfall/opt/skyfall-dev/pipeline/
```
파일 목록이 나오면 정상, 에러가 나면 IT에 스토리지 마운트를 요청하세요.

---

**Q. `Sync from Kitsu`가 동작하지 않아요.**  
→ 로그인 토큰이 만료된 것입니다. 다시 로그인하세요:
```bash
python3 /Volumes/skyfall/opt/skyfall-dev/pipeline/tools/kitsu_login.py
```

---

**Q. Load Plate를 눌렀는데 아무것도 안 불러와요.**  
→ 플레이트 원본 파일이 없는 것입니다. PM에게 플레이트 인제스트를 요청하세요.  
플레이트 경로: `/Volumes/skyfall/shows/{쇼}/plates/{샷코드}/`

---

**Q. 렌더가 PUBLISH DENIED로 막혔어요.**  
→ `SKYFALL → Publish → Check Assets`로 구체적인 이유를 확인하세요.  
가장 흔한 원인:
- 버전 폴더(`v001/`)를 아직 만들지 않음
- 파일명이 샷코드로 시작하지 않음
- EXR이 아닌 포맷 사용

---

**Q. setup_artist.sh를 실수로 두 번 실행했어요.**  
→ 괜찮습니다. 중복 체크가 되어 있어 이미 추가된 내용은 다시 추가하지 않습니다.

---

## 설치 확인 방법

터미널에서 아래 명령어로 설치 상태를 확인할 수 있습니다:

```bash
grep -n "SKYFALL" ~/.nuke/init.py ~/.nuke/menu.py
```

아래와 같이 출력되면 정상입니다:

```
/Users/사용자명/.nuke/init.py:6:# ── SKYFALL Pipeline ──
/Users/사용자명/.nuke/menu.py:7:# ── SKYFALL Pipeline ──
```

---

## 문의

- Slack: **#pipeline** 채널
- 파이프라인 TD에게 직접 문의

---

*SKYFALL Pipeline 2026 — Artist Setup Guide*
