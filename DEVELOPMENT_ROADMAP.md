# Skyfall Pipeline 현황 점검 및 개발 방향

> 작성일: 2026-04-09

---

## 현재 코드 주요 문제점

### 🔴 즉시 수정 필요 (Production 위험)

| 위치 | 문제 | 수정 방향 |
|---|---|---|
| `services/kitsu.py:13` | HTTP (비암호화) 로 자격증명 전송 | HTTPS로 변경, URL을 env.py로 집중화 |
| `tools/verify_tasks.py:20` | kitsu.py와 다른 서버 URL 사용 (불일치) | 동일 URL 소스 사용 |
| `services/kitsu.py:243` | 토큰 없으면 `mock_id` 반환 → 하위 코드 오작동 | 명시적 에러로 변경 |
| `tools/kitsu_login.py:28` | 토큰 파일 권한 미설정 (world-readable) | `chmod 0o600` 추가 |
| `apps/nuke/validator.py:38` | 해상도 1920x1080 하드코딩 | project.yml 또는 Kitsu에서 읽기 |
| `tools/setup_shot.py:79` | Nuke 스크립트에 fps 24 하드코딩 | Kitsu/config에서 읽기 |
| `tools/init_show.py:36` | project.yml 생성하지만 **아무데서도 읽지 않음** | env.py에 config reader 구현 |
| 전체 | `except Exception: pass` 남발 | 구체적 예외 처리 + logging 모듈 도입 |

---

## 해외 메이저 스튜디오 패턴과의 비교

### 모든 대형 스튜디오가 공통으로 가진 것

| 패턴 | 대형 스튜디오 | Skyfall 현황 |
|---|---|---|
| **Publish → Validate → Promote** 엄격한 게이트 | ILM, Weta, Pixar 공통 | validator.py 있음 ✅ (미완성) |
| **USD** 기반 씬 기술 | 사실상 전 스튜디오 | 미구현 ❌ |
| **중앙 트래킹 DB** (ShotGrid/Kitsu) | 필수 | Kitsu 연동 ✅ |
| **DCC 독립 추상화 레이어** | Ayon/OpenPype 또는 자체 | 구조 있음 ✅ (미완성) |
| **OCIO + ACES** 색상 관리 | 표준 | 미구현 ❌ |
| **렌더팜 스케줄러** | OpenCue/Deadline | 미구현 ❌ |
| **버전 불변성** (published = immutable) | 공통 원칙 | 부분 구현 |
| **설정 중앙화** | 공통 | 분산/하드코딩 ❌ |

### Skyfall 규모에 맞는 레퍼런스
**Ayon/OpenPype** (300+ 부티크 스튜디오 사용) + **Kitsu** 조합이 Skyfall 규모와 가장 유사한 모델입니다.
Skyfall이 지금 만들고 있는 것이 바로 이 구조입니다.

---

## Skyfall 개발 로드맵

### Phase 1: 기반 안정화 (지금 당장)

#### 1. 설정 시스템 구축
- `env.py`에 `project.yml` reader 추가
- 모든 하드코딩(URL, fps, 해상도) → `project.yml` 또는 환경변수로 이동

#### 2. 보안 / 신뢰성
- HTTPS 전환 + URL 단일 소스화 (`env.py`에서 관리)
- `logging` 모듈 도입 (`print` → `log`)
- 토큰 파일 권한 설정 (`chmod 0o600`)
- `requests` timeout + retry 추가

#### 3. 에러 처리
- bare `except` 제거, 구체적 예외 타입으로 교체
- `kitsu.py` mock 반환 → 명시적 예외 발생
- 부분 실패 시 롤백 패턴 적용

---

### Phase 2: Nuke 파이프라인 완성 (단기)

#### 1. `validator.py` 완성
- 해상도 / fps → Kitsu 또는 `project.yml`에서 동적 로드
- 코덱 / 색심도 검사 추가
- 렌더 출력 경로 존재 여부 확인
- `use_limit` 미설정 시에도 프레임 범위 검사

#### 2. `loader.py` 개선
- EXR 시퀀스 감지 (`.%04d.exr`)
- 버전 번호 기반 정렬 (알파벳 순서 아닌 버전 파싱)
- 허용 확장자 필터 (`.mov`, `.exr`, `.tif`)
- colorspace 메타데이터 적용

#### 3. Nuke 스크립트 템플릿
- 인라인 문자열 → `.nk` 템플릿 파일로 분리
- colorspace, fps, format 자동 삽입
- Jinja2 또는 단순 문자열 치환 방식

---

### Phase 3: Maya 통합 (중기)

- `apps/maya/` 폴더 구조 추가
- `context.py`의 DCC 감지 로직 이미 있음 → Maya 연결
- Nuke와 동일한 `menu / loader / validator` 패턴 적용
- **USD 기반 데이터 교환** (Nuke ↔ Maya)
  - 대형 스튜디오 표준, VFX Reference Platform 권장
  - Camera, Geometry, Transform 데이터 교환

---

### Phase 4: USD + 렌더팜 (장기)

#### 1. USD 도입
- 씬 기술 표준화 (Houdini, Maya, Nuke 모두 USD 지원)
- 에셋 publish를 USD layer로 저장
- Hydra 기반 뷰포트 렌더 (DCC 독립)
- Non-destructive layering으로 협업 강화

#### 2. 렌더팜
- **OpenCue** (Sony 오픈소스, 무료, ASWF 관리) 도입
  - Cuebot (스케줄러) + RQD (렌더 노드 에이전트) + CueGUI
- 또는 **AWS Deadline** (클라우드 버스트 필요 시)

#### 3. OCIO + ACES
- OpenColorIO v2.x 기반 컬러 파이프라인 표준화
- ACES 색상 공간 도입
- `validator.py`에 colorspace 검사 추가
- 전 DCC 동일 OCIO config 사용

---

## 가장 중요한 한 가지

지금 Skyfall 파이프라인에서 **즉시 해결해야 할 핵심**:

> **`project.yml`을 만들어놓고 아무도 읽지 않는다**

FPS, 해상도, 서버 URL 등이 여러 파일에 각각 하드코딩돼 있습니다.
`env.py`에 `project.yml` reader 하나만 제대로 만들어도 코드 품질이 크게 올라갑니다.

```python
# 목표 구조 (env.py)
def get_project_config(project_name: str) -> dict:
    config_path = get_shows_root() / project_name / "config" / "project.yml"
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f)
```

이 함수 하나로 `validator.py`, `setup_shot.py`, `kitsu.py` 전체의 하드코딩을 제거할 수 있습니다.

---

## 참고: 업계 주요 오픈소스 스택 (ASWF 관리)

| 도구 | 기원 | 역할 |
|---|---|---|
| OpenEXR | ILM | HDR 이미지 포맷 (VFX 표준) |
| OpenVDB | DreamWorks/ILM | 볼류메트릭 데이터 |
| OpenColorIO | Sony Imageworks | 색상 관리 |
| OpenImageIO | Larry Gritz/Sony | 이미지 I/O |
| USD (OpenUSD) | Pixar | 씬 기술 및 컴포지션 |
| MaterialX | ILM/Lucasfilm | 머티리얼/룩뎁 교환 |
| OpenCue | Sony Imageworks | 렌더팜 스케줄러 |
| OpenTimelineIO | Pixar | 에디토리얼 타임라인 |
| OpenAssetIO | DNEG/Foundry | 에셋 매니저 API 추상화 |

---

*Skyfall Pipeline — Internal Development Reference*
