# Skyfall Pipeline 개발 로드맵

> 최종 업데이트: 2026-04-10

---

## 완료 현황

### Phase 1: 기반 안정화 ✅ (2026-04-09 완료)

| 항목 | 상태 | 내용 |
|------|------|------|
| 설정 시스템 | ✅ | `env.py`에 `get_project_config()` 구현, 모든 하드코딩 제거 |
| HTTPS + URL 중앙화 | ✅ | `env.py`에서 Kitsu URL 관리, HTTPS 전환 |
| 토큰 보안 | ✅ | `kitsu_login.py` token 파일 `chmod 0o600` |
| Timeout + Retry | ✅ | `kitsu.py` requests Session에 retry + 30s timeout |
| Mock 제거 | ✅ | `kitsu.py` mock_id 반환 → RuntimeError 발생 |
| 에러 처리 | ✅ | bare except 제거, logging 모듈 도입 |

### Phase 2: Nuke 파이프라인 ✅ (2026-04-09 완료)

| 항목 | 상태 | 내용 |
|------|------|------|
| validator.py | ✅ | 해상도/fps → project.yml, 코덱/색심도/프레임 검사 |
| loader.py | ✅ | EXR 시퀀스 감지, 버전 정렬, 확장자 필터, colorspace 적용 |
| Nuke 템플릿 | ✅ | hd_comp.nk, uhd_comp.nk, uhd_comp_slate.nk (토큰 치환) |
| OCIO + ACES | ✅ | ww_aces_config v1, 쇼별 config, Nuke 자동 적용 |
| 메뉴 시스템 | ✅ | init.py + menu.py, 프로젝트별 gizmo/script 등록 |

### Phase 2.5: 입고 파이프라인 + Kitsu 통합 ✅ (2026-04-10 완료)

| 항목 | 상태 | 내용 |
|------|------|------|
| init_show.py | ✅ | 쇼 생성 (workflow uhd/hd, OCIO, Kitsu 프로젝트) |
| ingest_plate.py | ✅ | from_client/ → plates/{shot}/{version}/ 복사, editor 스킵 |
| setup_shot.py | ✅ | 샷 폴더 + 심링크 + nk 생성 (Kitsu 분리), 새 플레이트 자동 감지 |
| create_nk.py | ✅ | 템플릿 기반 nk 생성, HD MOV ffprobe 프레임 감지 |
| convert_excel.py | ✅ | 클라이언트 Excel → 내부 CSV (shots.csv + notes.csv) |
| update_kitsu_shots.py | ✅ | 샷 등록 + description (shots.csv 기반) |
| update_kitsu_preview.py | ✅ | editor MOV → Kitsu preview (2단계 업로드) |
| update_kitsu_comment.py | ✅ | 작업 지시 → Kitsu comment (notes.csv 기반) |
| 내부 CSV 포맷 | ✅ | ShotGrid 방식: Shot/Version/Note 분리 |
| Excel 파서 | ✅ | 헤더 자동 감지, status 매핑, task 타입 추출 |

---

## 미완료 / 진행 예정

### Phase 3: Maya 통합 (다음 세션)

- `apps/maya/` 폴더 구조 추가
- `context.py`의 DCC 감지 → Maya 연결
- Nuke와 동일한 menu / loader / validator 패턴
- USD 기반 데이터 교환 (Camera, Geometry, Transform)

### Phase 4: USD + 렌더팜 (장기)

- **USD** 도입: 씬 기술 표준화, Non-destructive layering
- **OpenCue** 렌더팜: Cuebot + RQD + CueGUI
- **OCIO v2** 마이그레이션 (현재 v1)
- MaterialX 머티리얼 교환

---

## 현재 아키텍처

```
tools/                          services/
├── init_show.py                ├── kitsu.py (API)
├── ingest_plate.py             ├── kitsu_utils.py (공통)
├── setup_shot.py               └── excel_parser.py (Excel)
├── create_nk.py
├── convert_excel.py            apps/nuke/
├── update_kitsu.py (wrapper)   ├── init.py
├── update_kitsu_shots.py       ├── menu.py
├── update_kitsu_preview.py     ├── loader.py
├── update_kitsu_comment.py     ├── validator.py
└── kitsu_login.py              └── templates/ (hd/uhd/slate)

core/
├── env.py (설정, project.yml)
└── context.py (DCC 컨텍스트)
```

### 매일 입고 워크플로우

```
ingest_plate → setup_shot → convert_excel → kitsu_shots → kitsu_preview → kitsu_comment
```

### 데이터 모델 (ShotGrid 방식)

```
Shot (shots.csv)      → Kitsu Shot (description, frame range)
Version (editor MOV)  → Kitsu Preview (미디어 업로드)
Note (notes.csv)      → Kitsu Comment (작업 지시)
```

---

## 해외 메이저 스튜디오 패턴 비교

| 패턴 | 대형 스튜디오 | Skyfall 현황 |
|------|-------------|-------------|
| Publish → Validate → Promote | ILM, Weta, Pixar | validator.py ✅ |
| USD 기반 씬 기술 | 사실상 전 스튜디오 | Phase 4 예정 |
| 중앙 트래킹 DB | 필수 | Kitsu ✅ |
| DCC 독립 추상화 | Ayon/OpenPype | context.py ✅ |
| OCIO + ACES | 표준 | ww_aces_config v1 ✅ |
| 렌더팜 스케줄러 | OpenCue/Deadline | Phase 4 예정 |
| 버전 불변성 | 공통 원칙 | plates/ 버전 서브폴더 ✅ |
| 설정 중앙화 | 공통 | project.yml ✅ |

---

## 참고: ASWF 오픈소스 스택

| 도구 | 기원 | 역할 | Skyfall 사용 |
|------|------|------|-------------|
| OpenEXR | ILM | HDR 이미지 포맷 | ✅ UHD workflow |
| OpenColorIO | Sony Imageworks | 색상 관리 | ✅ v1 |
| OpenCue | Sony Imageworks | 렌더팜 스케줄러 | Phase 4 |
| USD | Pixar | 씬 기술 | Phase 4 |
| MaterialX | ILM/Lucasfilm | 머티리얼 교환 | Phase 4 |

---

*Skyfall Pipeline — Internal Development Reference*
