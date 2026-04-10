# SKYFALL Pipeline 2026
## 아티스트 설치 가이드

**대상:** 합성 아티스트 (Nuke 사용자)  
**소요 시간:** 약 3분  
**최종 업데이트:** 2026-04-10

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

### Gizmos / Scripts

프로젝트별 기즈모와 스크립트가 자동으로 등록됩니다.
- `SKYFALL > Gizmos > Common` — 공통 기즈모
- `SKYFALL > Gizmos > {프로젝트명}` — 쇼 전용 기즈모

---

## 워크플로우별 작업 방법

### UHD 프로젝트 (Netflix 등)

```
Read_PLATE (EXR) → 합성 작업 → Write_PUBLISH (EXR, ACES2065-1)
                              → Write_REVIEW (MOV, ProRes422, 1920x1080)
```

- 입력: EXR 시퀀스 (3840x2160)
- 출력 2개: EXR 납품용 + MOV 리뷰용
- 컬러: OCIO ACES 자동 적용

### HD 프로젝트 (드라마 등)

```
Read_PLATE (MOV) → 합성 작업 → Write_REVIEW (MOV, ProRes422, 1920x1080)
```

- 입력: MOV (1920x1080)
- 출력 1개: MOV 리뷰/납품용
- 프레임: 타임라인 1001부터 시작 (자동 매핑)

> 어떤 워크플로우인지는 PM이 프로젝트 생성 시 설정합니다. 아티스트가 신경 쓸 필요 없습니다.

---

## 작업 방법 (공통)

### 1. Nuke 스크립트 열기

PM이 생성한 nk 파일을 열면 됩니다:

```
/Volumes/skyfall/shows/{쇼}/{에피소드}/{시퀀스}/{샷}/comp/nk/
```

**예시:**
```
/Volumes/skyfall/shows/AAB/EP01/S005/0060/comp/nk/EP01_S005_0060_comp_v001.nk
```

스크립트를 열면 자동으로:
- OCIO 컬러 설정 적용
- 프레임 범위 설정 (1001~)
- FPS 적용 (23.976 등)
- 플레이트 Read 노드 연결

### 2. 플레이트 확인

스크립트를 열면 이미 Read_PLATE가 연결되어 있습니다.
수동으로 로드하려면:

```
SKYFALL → Asset → Load Plate
```

### 3. 렌더 출력 경로 규칙

Write 노드의 출력 경로는 아래 규칙을 따라야 합니다:

**UHD:**
```
Write_PUBLISH: .../comp/render/v001/EP01_S005_0060_comp_v001.%04d.exr
Write_REVIEW:  .../comp/review/v001/EP01_S005_0060_comp_v001.mov
```

**HD:**
```
Write_REVIEW:  .../comp/review/v001/EP01_S005_0060_comp_v001.mov
```

| 규칙 | 예시 |
|---|---|
| 버전 폴더 필수 | `/v001/`, `/v002/` ... |
| 파일명 = 샷코드_작업명_버전 | `EP01_S005_0060_comp_v001` |
| UHD EXR = 16bit half | Zip1 압축 |
| HD MOV = ProRes422 | Rec.709 |

### 4. 렌더 전 검증

```
SKYFALL → Publish → Check Assets
```

검사 항목:
- 파일명이 샷코드로 시작하는지
- 해상도가 프로젝트 설정과 일치하는지
- EXR 포맷/비트뎁스가 맞는지 (UHD)
- 프레임 범위가 전체인지

모든 항목 통과 후 렌더하세요.

### 5. 버전업

v001 작업이 끝나고 v002를 시작하려면 PM에게 요청하거나:

```bash
python3 /Volumes/skyfall/opt/skyfall-dev/pipeline/tools/create_nk.py {쇼} {샷코드} --new-version
```

---

## 자주 생기는 문제

**Q. SKYFALL 메뉴가 안 보여요.**  
→ setup_artist.sh를 실행했는지 확인하고 Nuke를 완전히 재시작하세요.

---

**Q. Nuke에서 MOV 플레이트가 검게 보여요.**  
→ PM에게 nk 파일 재생성을 요청하세요:
```bash
python3 tools/create_nk.py {쇼} --all --force
```

---

**Q. "out of frame range" 에러가 나요.**  
→ HD 프로젝트에서 프레임 설정 문제입니다. 위와 동일하게 nk 재생성을 요청하세요.

---

**Q. `Sync from Kitsu`가 동작하지 않아요.**  
→ 로그인 토큰이 만료된 것입니다:
```bash
python3 /Volumes/skyfall/opt/skyfall-dev/pipeline/tools/kitsu_login.py
```

---

**Q. Load Plate를 눌렀는데 아무것도 안 불러와요.**  
→ 플레이트가 아직 인제스트되지 않은 것입니다. PM에게 문의하세요.

---

**Q. 렌더가 PUBLISH DENIED로 막혔어요.**  
→ `SKYFALL → Publish → Check Assets`로 구체적인 이유를 확인하세요.  
가장 흔한 원인:
- 버전 폴더(`v001/`)가 없음
- 파일명이 샷코드로 시작하지 않음
- EXR이 아닌 포맷 사용 (UHD 프로젝트)

---

## 설치 확인 방법

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
