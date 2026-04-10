# SKYFALL VFX Pipeline Manual

> Version 3.0 | 2026-04-10 | Phase 2.5 (Nuke + Ingest + Kitsu)

---

## 목차

1. [개요](#1-개요)
2. [시스템 구성도](#2-시스템-구성도)
3. [폴더 구조](#3-폴더-구조)
4. [워크플로우 다이어그램](#4-워크플로우-다이어그램)
5. [도구 사용법](#5-도구-사용법)
6. [내부 CSV 포맷](#6-내부-csv-포맷)
7. [Nuke 워크플로우](#7-nuke-워크플로우)
8. [프로젝트 설정 (project.yml)](#8-프로젝트-설정-projectyml)
9. [컬러 매니지먼트](#9-컬러-매니지먼트)
10. [Kitsu 연동](#10-kitsu-연동)
11. [트러블슈팅](#11-트러블슈팅)

---

## 1. 개요

SKYFALL Pipeline은 VFX 프로덕션을 위한 파이프라인 시스템입니다.

**지원 워크플로우:**

| 워크플로우 | 입력 | 출력 | 사용 예 |
|-----------|------|------|---------|
| **UHD** | EXR 시퀀스 (3840x2160) | EXR (ACES2065-1) + MOV (ProRes422 HD) | Netflix, 극장 |
| **HD** | MOV (1920x1080) | MOV (ProRes422 HD) | 드라마, 웹 |

**핵심 구성요소:**

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Nuke        │    │  Kitsu       │    │  OCIO v1     │
│  (합성)      │    │  (트래킹)    │    │  (컬러관리)  │
│              │    │              │    │              │
│  templates/  │    │  shows.      │    │  ww_aces_    │
│  validator   │    │  skyfall.    │    │  config      │
│  loader      │    │  studio      │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## 2. 시스템 구성도

```
                        SKYFALL Pipeline
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
    ┌─────▼─────┐      ┌─────▼─────┐      ┌─────▼─────┐
    │   tools/   │      │   apps/   │      │ services/ │
    │            │      │           │      │           │
    │ init_show  │      │ nuke/     │      │ kitsu.py  │
    │ ingest_    │      │  init.py  │      │ kitsu_    │
    │   plate    │      │  menu.py  │      │  utils.py │
    │ setup_shot │      │  loader   │      │ excel_    │
    │ create_nk  │      │  valid.   │      │  parser.py│
    │ convert_   │      │  templ/   │      │           │
    │   excel    │      │           │      └───────────┘
    │ update_    │      └───────────┘
    │  kitsu_*   │
    │ kitsu_login│
    └────────────┘
          │
    ┌─────▼─────┐
    │   core/   │
    │           │
    │ env.py    │
    │ context.py│
    └───────────┘
```

---

## 3. 폴더 구조

### 파이프라인 설치 경로

```
/Volumes/skyfall/opt/skyfall-dev/pipeline/
├── apps/
│   └── nuke/
│       ├── gizmos/              # 공통 기즈모
│       ├── scripts/             # 공통 스크립트
│       ├── templates/
│       │   ├── hd_comp.nk       # HD 워크플로우
│       │   ├── uhd_comp.nk      # UHD 워크플로우
│       │   └── uhd_comp_slate.nk # UHD + 슬레이트
│       ├── init.py              # Nuke 시작 스크립트
│       ├── menu.py              # 메뉴 구성
│       ├── loader.py            # 플레이트 로더
│       └── validator.py         # 퍼블리시 검증
├── core/
│   ├── env.py                   # 환경설정, 경로
│   └── context.py               # DCC 컨텍스트 감지
├── services/
│   ├── kitsu.py                 # Kitsu API
│   ├── kitsu_utils.py           # Kitsu 공통 유틸리티
│   └── excel_parser.py          # Excel 파서
├── tools/
│   ├── init_show.py             # 쇼 생성
│   ├── ingest_plate.py          # 플레이트 입고
│   ├── setup_shot.py            # 샷 폴더 생성
│   ├── create_nk.py             # Nuke 스크립트 생성
│   ├── convert_excel.py         # Excel → CSV 변환
│   ├── update_kitsu.py          # Kitsu 업데이트 (wrapper)
│   ├── update_kitsu_shots.py    # Kitsu 샷 등록 + description
│   ├── update_kitsu_preview.py  # Kitsu editor preview 업로드
│   ├── update_kitsu_comment.py  # Kitsu comment 생성
│   ├── kitsu_login.py           # Kitsu 로그인
│   └── verify_tasks.py          # Kitsu 태스크 확인 (디버깅용)
└── config/
    ├── ocio/                    # OCIO 설정
    └── token_cache.json         # Kitsu 인증 토큰
```

### 쇼 폴더 구조

```
/Volumes/skyfall/shows/AAB/
├── project.yml                  # 프로젝트 설정
├── config/
│   ├── ocio/config.ocio         # 쇼 전용 OCIO
│   └── nuke/
│       ├── gizmos/              # 쇼 전용 기즈모
│       └── scripts/             # 쇼 전용 스크립트
├── plates/                      # 중앙 플레이트 저장소
│   ├── EP01_S004_0002/
│   │   ├── v001/
│   │   │   └── EP01_S004_0002_org_v001.mov
│   │   └── v002/
│   │       └── EP01_S004_0002_org_v002.mov
│   └── ingest_log/
├── exchange/
│   ├── from_client/             # 클라이언트 납품 수신
│   │   └── 260206/
│   │       ├── description.xlsx  # 클라이언트 Excel
│   │       ├── shots.csv         # 내부 표준 (convert_excel 생성)
│   │       ├── notes.csv         # 내부 표준 (convert_excel 생성)
│   │       ├── 01_editor/
│   │       │   └── EP01_S004_0002_editor_v001.mov
│   │       └── 02_plate/
│   │           └── EP01_S004_0002_org_v001.mov
│   └── to_client/               # 납품 발송
├── EP01/                        # 에피소드
│   └── S004/                    # 시퀀스
│       └── 0002/                # 샷
│           ├── plate → ../../../plates/EP01_S004_0002  (심링크)
│           ├── comp/
│           │   ├── nk/
│           │   │   └── EP01_S004_0002_comp_v001.nk
│           │   ├── render/v001/
│           │   └── review/v001/
│           ├── roto/
│           ├── prep/
│           └── fx/
├── assets/ (2D, 3D)
├── dailies/
├── deliveries/
└── editorial/
```

---

## 4. 워크플로우 다이어그램

### 전체 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                     최초 1회: 프로젝트 생성                       │
│                                                                 │
│  python3 tools/init_show.py AAB --workflow hd --fps 23.976 ...  │
│                                                                 │
│  → 폴더 구조 생성                                                │
│  → project.yml 생성                                             │
│  → OCIO config 복사                                             │
│  → Kitsu 프로젝트 등록                                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    매일 반복: 입고 파이프라인                      │
│                                                                 │
│  ① ingest_plate.py AAB --folder 260410                          │
│     └─ from_client/ → plates/{shot}/{version}/ 복사              │
│                                                                 │
│  ② setup_shot.py AAB --all                                      │
│     └─ 샷 폴더 + 심링크 + Nuke 스크립트 생성                      │
│     └─ 새 플레이트 감지 시 nk 자동 재생성                          │
│                                                                 │
│  ③ convert_excel.py AAB --folder 260410                         │
│     └─ 클라이언트 Excel → shots.csv + notes.csv 변환             │
│                                                                 │
│  ④ update_kitsu_shots.py AAB --all --folder 260410              │
│     └─ Kitsu 샷 등록 + description 업데이트                      │
│                                                                 │
│  ⑤ update_kitsu_preview.py AAB --folder 260410                  │
│     └─ editor MOV → Kitsu preview 업로드                         │
│                                                                 │
│  ⑥ update_kitsu_comment.py AAB --folder 260410                  │
│     └─ notes.csv → Kitsu 태스크 comment 생성                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       아티스트 작업                               │
│                                                                 │
│  Nuke로 .nk 파일 열기                                            │
│  → OCIO 자동 적용                                                │
│  → 플레이트 Read 노드 자동 설정                                   │
│  → 합성 작업                                                     │
│  → 렌더 (Validator 자동 검증)                                     │
└─────────────────────────────────────────────────────────────────┘
```

### 클라이언트 납품 데이터 흐름

```
클라이언트 납품 (from_client/260410/)
     │
     ├── Excel ──→ convert_excel.py ──→ shots.csv + notes.csv
     │                                       │          │
     │                                       ▼          ▼
     │                              update_kitsu   update_kitsu
     │                              _shots.py      _comment.py
     │                                  │              │
     │                                  ▼              ▼
     │                              Kitsu:         Kitsu:
     │                              description    comment
     │
     ├── editor MOV ──→ update_kitsu_preview.py ──→ Kitsu: preview
     │
     └── plate ──→ ingest_plate.py ──→ plates/{shot}/v001/
                                            │
                                            ▼
                                       setup_shot.py
                                            │
                                            ▼
                                       EP01/S004/0002/
                                         ├── plate → ../plates/...
                                         └── comp/nk/*.nk
```

### UHD Nuke 노드 그래프

```
    ┌──────────────┐
    │  Read_PLATE  │  EXR 시퀀스
    │  (ACES2065-1)│
    └──────┬───────┘
           │
        ┌──┴──┐
        │Dot1 │  (분기점)
        └──┬──┘
     ┌─────┴──────┐
     │            │
     ▼            ▼
┌────────┐  ┌──────────────┐
│Write_  │  │ Reformat     │  3840→1920
│PUBLISH │  │ _REVIEW      │
│        │  └──────┬───────┘
│ EXR    │         │
│Zip1 16b│         ▼
│ACES    │  ┌──────────────┐
│2065-1  │  │ Write_REVIEW │
└────────┘  │              │
            │ ProRes422    │
            │ Rec.709      │
            │ 1920x1080    │
            └──────────────┘
```

### HD Nuke 노드 그래프

```
    ┌──────────────┐
    │  Read_PLATE  │  MOV
    │  (ARRI LogC) │
    │              │
    │  first: 1    │  ← MOV 원본 프레임
    │  last: N     │
    │  frame_mode  │
    │  "start at"  │
    │  frame: 1001 │  ← 타임라인 매핑
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Write_REVIEW │
    │              │
    │ ProRes422    │
    │ Rec.709      │
    │ 1920x1080    │
    └──────────────┘
```

---

## 5. 도구 사용법

### 5.1 init_show.py — 쇼 생성

프로젝트를 처음 만들 때 한 번만 실행합니다.

```bash
# UHD 프로젝트 (Netflix 기준)
python3 tools/init_show.py AAA \
  --workflow uhd \
  --fps 23.976 \
  --resolution 3840x2160 \
  --camera "Input - ARRI - V4 LogC (EI800) - Wide Gamut4" \
  --output-colorspace "ACES - ACES2065-1"

# HD 프로젝트 (드라마)
python3 tools/init_show.py AAB \
  --workflow hd \
  --fps 23.976 \
  --resolution 1920x1080 \
  --camera "Input - ARRI - V4 LogC (EI800) - Wide Gamut4" \
  --output-colorspace "Output - Rec.709"
```

| 옵션 | 필수 | 설명 | 예시 |
|------|------|------|------|
| `show_name` | O | 쇼 코드 | `AAA` |
| `--workflow` | X | `uhd` 또는 `hd` | `hd` |
| `--fps` | O | 프레임 레이트 | `23.976` |
| `--resolution` | O | 해상도 | `3840x2160` |
| `--camera` | O | 카메라 컬러스페이스 | `"Input - ARRI - V4 LogC..."` |
| `--output-colorspace` | O | 출력 컬러스페이스 | `"ACES - ACES2065-1"` |
| `--review-colorspace` | X | 리뷰 컬러스페이스 | `"Output - Rec.709"` |
| `--review-resolution` | X | 리뷰 해상도 | `1920x1080` |

---

### 5.2 ingest_plate.py — 플레이트 입고

```bash
python3 tools/ingest_plate.py AAB --list                     # 폴더 목록
python3 tools/ingest_plate.py AAB --folder 260410 --dry-run   # 미리보기
python3 tools/ingest_plate.py AAB --folder 260410             # 실제 복사
python3 tools/ingest_plate.py AAB --folder 260410/02_plate    # 서브폴더 지정
```

| 타입 | 패턴 | 처리 |
|------|------|------|
| `org` | `*_org_v001.mov` | plates/로 복사 |
| `plate` | `*_plate_v001.exr` | plates/로 복사 |
| `editor` | `*_editor_v001.mov` | 스킵 (Kitsu 업로드 대상) |

---

### 5.3 setup_shot.py — 샷 폴더 생성

```bash
python3 tools/setup_shot.py AAB --all                        # 전체 샷 (comp)
python3 tools/setup_shot.py AAB --all --task roto             # 전체 샷 (roto)
python3 tools/setup_shot.py AAB --all --task prep             # 전체 샷 (prep)
python3 tools/setup_shot.py AAB --all --dry-run               # 미리보기
python3 tools/setup_shot.py AAB EP01_S004_0002                # 단일 샷
```

- plates/ 기준으로 샷 자동 감지
- `--task` 미지정 시 기본 comp
- 새 버전 플레이트 감지 시 nk 자동 재생성
- 한 샷에 여러 태스크 가능 (comp + roto 각각 실행)
- 생성: 폴더 + plate 심링크 + Nuke 스크립트

**태스크별 nk 경로:**
```
{shot}/comp/nk/EP01_S004_0002_comp_v001.nk   # --task comp (기본)
{shot}/roto/nk/EP01_S004_0002_roto_v001.nk   # --task roto
{shot}/prep/nk/EP01_S004_0002_prep_v001.nk   # --task prep
```

---

### 5.4 create_nk.py — Nuke 스크립트 생성

```bash
python3 tools/create_nk.py AAB --all                         # 전체 comp (스킵)
python3 tools/create_nk.py AAB --all --force                 # 전체 comp (덮어쓰기)
python3 tools/create_nk.py AAB --all --task roto             # 전체 roto
python3 tools/create_nk.py AAB EP01_S004_0002 --new-version  # 버전업
python3 tools/create_nk.py AAB EP01_S004_0002 --slate        # 슬레이트 (UHD)
```

| 워크플로우 | 슬레이트 | 템플릿 |
|-----------|---------|--------|
| HD | - | `hd_comp.nk` |
| UHD | 없음 | `uhd_comp.nk` |
| UHD | 있음 | `uhd_comp_slate.nk` |

---

### 5.5 convert_excel.py — Excel → CSV 변환

클라이언트 Excel을 내부 표준 CSV로 변환합니다.

```bash
python3 tools/convert_excel.py AAB --folder 260410            # 변환
python3 tools/convert_excel.py AAB --folder 260410 --dry-run  # 미리보기
python3 tools/convert_excel.py AAB --folder 260410 --force    # 덮어쓰기
```

**기능:**
- Excel 헤더 자동 감지 (Shot Code, VFX_Work, Description 등)
- ffprobe로 실제 프레임 레인지 감지 (plates/ 기준)
- 클라이언트 status → Kitsu status 자동 매핑 (wtg→todo, change→wip 등)
- VFX_Work에서 태스크 타입 자동 추출 (comp, matte, roto 등)
- 기존 CSV 있으면 스킵 (`--force`로 덮어쓰기)

**생성 파일:**
```
from_client/260410/
  ├── shots.csv   ← 샷 데이터
  └── notes.csv   ← 작업 지시
```

---

### 5.6 Kitsu 업데이트 (3개 독립 도구)

**순서: shots → preview → comment**

```bash
# 1. 샷 등록 + description (추가 태스크 지정 가능)
python3 tools/update_kitsu_shots.py AAB --all --folder 260410
python3 tools/update_kitsu_shots.py AAB --all --folder 260410 --task roto  # roto 태스크 추가

# 2. editor preview 업로드 (태스크 지정 가능)
python3 tools/update_kitsu_preview.py AAB --folder 260410
python3 tools/update_kitsu_preview.py AAB --folder 260410 --task roto  # roto에 업로드

# 3. VFX_Work comment (중복 자동 방지)
python3 tools/update_kitsu_comment.py AAB --folder 260410
```

**또는 wrapper로 일괄 실행:**

```bash
python3 tools/update_kitsu.py AAB --all --folder 260410
```

**각 도구의 역할:**

| 도구 | 읽는 것 | Kitsu 반영 |
|------|---------|-----------|
| `update_kitsu_shots.py --all` | plates/ | 샷 등록 + 프레임 레인지 + 태스크 생성 |
| `update_kitsu_shots.py --folder` | shots.csv | description 업데이트 |
| `update_kitsu_preview.py` | editor MOV 파일 | 태스크별 preview 업로드 (`--task` 지정) |
| `update_kitsu_comment.py` | notes.csv | 태스크별 comment 생성 (중복 방지) |

**서브폴더 지정:**

모든 `--folder` 옵션에서 `/`를 포함하면 서브폴더를 직접 지정합니다:
- `--folder 260410` → 부분 매칭
- `--folder 260410/01_editor` → 서브폴더 직접 지정

---

### 5.7 kitsu_login.py — Kitsu 로그인

```bash
python3 tools/kitsu_login.py
# → URL, 이메일, 비밀번호 입력
# → config/token_cache.json에 토큰 저장
```

---

## 6. 내부 CSV 포맷

클라이언트 Excel은 매번 다른 포맷으로 오기 때문에, `convert_excel.py`로 내부 표준 CSV로 변환합니다.

### shots.csv — 샷 데이터

```csv
shot_code,description,frame_in,frame_out,colorspace
EP01_S005_0060,"스티커 리무브 필요",1001,1063,Arri4.rec709
EP01_S005_0110,"메뉴판 스티커 제거",1001,1107,Arri4.rec709
```

| 필드 | 용도 | 소스 |
|------|------|------|
| `shot_code` | 샷 매칭 키 | Excel: Shot Code |
| `description` | Kitsu shot description | Excel: Description |
| `frame_in` | 시작 프레임 | ffprobe 자동 감지 또는 Excel |
| `frame_out` | 마지막 프레임 | ffprobe 자동 감지 또는 Excel |
| `colorspace` | 참고 | Excel: Shot_Colorspace |

### notes.csv — 작업 지시

```csv
shot_code,task,note,status,assignee
EP01_S005_0060,comp,"1) 스티커 리무브",wip,PD
EP01_S051_1350,matte,"1) 도로표지판 변형",todo,
```

| 필드 | 용도 | 소스 |
|------|------|------|
| `shot_code` | 샷 매칭 키 | Excel: Shot Code |
| `task` | 태스크 타입 (comp/matte/roto/prep/fx) | VFX_Work 자동 추출 |
| `note` | 작업 지시 내용 → Kitsu comment | Excel: VFX_Work |
| `status` | 태스크 상태 (todo/wip/retake/done) | Excel: Status 자동 매핑 |
| `assignee` | 담당자 | (수동 입력 가능) |

### 데이터 흐름 (ShotGrid 방식)

```
Shot (샷)          ← shots.csv
├── description
├── frame_in/out
│
├── Version (버전)  ← editor MOV 파일
│   ├── v001: editor_v001.mov
│   └── v002: editor_v002.mov
│
└── Note (노트)    ← notes.csv
    └── "1) 스티커 리무브" (태스크에 연결)
```

---

## 7. Nuke 워크플로우

### Nuke 시작 설정

Nuke 시작 시 `init.py`가 자동으로:
1. 파이프라인 공통 gizmo/script 경로 등록
2. 쇼 전용 gizmo/script 경로 등록
3. SKYFALL 메뉴 생성

### SKYFALL 메뉴 구조

```
SKYFALL
├── Pipeline
│   ├── Check Context        # 현재 컨텍스트 확인
│   └── Sync from Kitsu      # Kitsu에서 프레임 레인지/fps 동기화
├── Asset
│   └── Load Plate           # 플레이트 로더 (자동 감지)
├── Publish
│   ├── Check Assets         # 퍼블리시 검증 (수동)
│   └── Smart Publish        # (예정)
├── Gizmos
│   ├── Common/              # 공통 기즈모
│   └── {프로젝트명}/         # 쇼 전용 기즈모
└── Scripts
    ├── Common/              # 공통 스크립트
    └── {프로젝트명}/         # 쇼 전용 스크립트
```

### 퍼블리시 검증 (Validator)

렌더 실행 전 자동으로 검사합니다:

| 검사 항목 | 내용 |
|----------|------|
| 컨텍스트 | 스크립트가 올바른 샷 폴더에 저장됐는지 |
| 해상도 | project.yml 설정과 일치하는지 |
| 네이밍 | `{shot_code}_{task}_v{###}.exr` 형식 |
| 프레임 레인지 | 전체 프레임이 렌더되는지 |
| 파일 포맷 | EXR, 16-bit, 지정 압축 (Netflix: ZIP1) |
| 컬러스페이스 | project.yml 출력 컬러스페이스와 일치 |

---

## 8. 프로젝트 설정 (project.yml)

`init_show.py`가 생성하며, 모든 도구가 참조합니다.

```yaml
project_name: AAB
fps: 23.976
resolution: [1920, 1080]
working_colorspace: ACEScg
ocio_config: aces_ww
ocio_config_path: /Volumes/skyfall/shows/AAB/config/ocio/config.ocio
camera_colorspace: "Input - ARRI - V4 LogC (EI800) - Wide Gamut4"
output_colorspace: "Output - Rec.709"
output_compressor: zip1
output_bit_depth: 16
review_colorspace: "Output - Rec.709"
review_resolution: [1920, 1080]
workflow: hd  # uhd 또는 hd
```

**주요 카메라 컬러스페이스:**

| 카메라 | 컬러스페이스 |
|--------|------------|
| ARRI Alexa 35 (V4) | `Input - ARRI - V4 LogC (EI800) - Wide Gamut4` |
| ARRI Alexa (V3) | `Input - ARRI - V3 LogC (EI800) - Wide Gamut` |
| Sony Venice | `Input - Sony - S-Log3 - S-Gamut3.Cine` |
| RED | `Input - RED - REDLog3G10 - REDWideGamutRGB` |
| Canon | `Input - Canon - Canon-Log2 - Cinema Gamut Daylight` |
| Blackmagic | `Input - BMD - BMDFilm WideGamut Gen5` |

---

## 9. 컬러 매니지먼트

- **OCIO 버전:** v1 (ww_aces_config)
- **Working Space:** scene_linear (ACEScg)
- **Viewer LUT:** Rec.709 (ACES)

**UHD:**
```
카메라 (ARRI LogC) → Read → scene_linear → Write_PUBLISH (ACES2065-1/EXR)
                                          → Write_REVIEW (Rec.709/ProRes)
```

**HD:**
```
카메라 (ARRI LogC) → Read → scene_linear → Write_REVIEW (Rec.709/ProRes)
```

---

## 10. Kitsu 연동

### 서버 정보

| 항목 | 값 |
|------|-----|
| URL | KITSU_API_URL 환경변수 참조 |
| 인코딩 | 동기 모드 |

> 서버 접속 정보는 사내 Wiki를 참조하세요.

### Kitsu 데이터 구조

```
Project (AAB)
└── Episode (EP01)
    └── Sequence (S004)
        └── Shot (0002)
            ├── Description (shots.csv에서)
            ├── Frame In / Frame Out
            └── Task: COMPOSITING
                ├── Preview: editor MOV (Version)
                └── Comment: 작업 지시 (notes.csv에서)
```

### Preview 업로드 (2단계)

```
1. POST /actions/tasks/{id}/comments/{id}/add-preview
   → preview 엔티티 생성 (파일 없이)

2. POST /pictures/preview-files/{preview_id}
   → 실제 MOV 파일 업로드 (인코딩 트리거)
```

---

## 11. 트러블슈팅

### Nuke에서 MOV가 검게 보일 때

Read 노드 프레임 설정 확인:
- `first`: 1, `last`: N (MOV 원본 프레임)
- `frame_mode`: "start at", `frame`: 1001

```bash
python3 tools/create_nk.py AAB --all --force
```

### Kitsu preview 인코딩 안 됨

```bash
# Kitsu 서버에 SSH 접속 후 (접속 정보는 사내 Wiki 참조)
sudo tail -30 /opt/zou/logs/gunicorn_error.log
cat /etc/zou/zou.env  # ENABLE_JOB_QUEUE=false 확인
```

### CSV가 Excel에서 깨져 보임

CSV는 UTF-8 BOM으로 생성되므로 Excel에서 정상 표시됩니다. 깨지면 `--force`로 재생성:

```bash
python3 tools/convert_excel.py AAB --folder 260410 --force
```

### 새 플레이트(v002)가 nk에 반영 안 됨

`setup_shot --all`이 자동 감지하지만, 수동으로 하려면:

```bash
python3 tools/create_nk.py AAB --all --force
```

### Kitsu 토큰 만료

```bash
python3 tools/kitsu_login.py
```

---

## 환경 변수

| 변수 | 용도 | 기본값 |
|------|------|--------|
| `SKYFALL_SHOWS_DIR` | 쇼 루트 경로 | `/Volumes/skyfall/shows` |
| `KITSU_API_URL` | Kitsu API URL | (사내 설정 참조) |
| `KITSU_ACCESS_TOKEN` | Kitsu 인증 토큰 | (token_cache.json) |
| `SKYFALL_SHOW` | Nuke 플러그인 등록용 | (자동 감지) |

---

## 빠른 참조

### 매일 입고 (전체)

```bash
python3 tools/ingest_plate.py AAB --folder 260410
python3 tools/setup_shot.py AAB --all
python3 tools/convert_excel.py AAB --folder 260410
python3 tools/update_kitsu_shots.py AAB --all --folder 260410
python3 tools/update_kitsu_preview.py AAB --folder 260410
python3 tools/update_kitsu_comment.py AAB --folder 260410
```

### 플레이트만 받았을 때

```bash
python3 tools/ingest_plate.py AAB --folder 260410
python3 tools/setup_shot.py AAB --all
python3 tools/update_kitsu_shots.py AAB --all
```

### Excel/editor만 나중에 받았을 때

```bash
python3 tools/convert_excel.py AAB --folder 260410
python3 tools/update_kitsu_shots.py AAB --folder 260410
python3 tools/update_kitsu_preview.py AAB --folder 260410
python3 tools/update_kitsu_comment.py AAB --folder 260410
```

### Roto/Prep 태스크 프로젝트

```bash
python3 tools/ingest_plate.py AAA --folder 20241125
python3 tools/setup_shot.py AAA --all --task roto
python3 tools/convert_excel.py AAA --folder 20241125
python3 tools/update_kitsu_shots.py AAA --all --task roto --folder 20241125
python3 tools/update_kitsu_preview.py AAA --folder 20241125 --task roto
python3 tools/update_kitsu_comment.py AAA --folder 20241125
```
