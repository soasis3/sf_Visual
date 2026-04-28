# Architecture

## 목표

기존 DCC 스크립트 중심 파이프라인을 웹 중심 파이프라인으로 재구성한다.

핵심 원칙:

- 단일 진실 원천은 API와 DB
- Google Sheets는 운영 입력/외부 협업 원장
- Maya / Blender / After Effects는 얇은 클라이언트
- 파일명 파싱보다 `shot_code`, `task_type`, `version_number` 같은 명시적 식별자를 우선

## 시스템 구성

### 1. Web App

- 샷 목록, 상태 보드, 버전 이력, 담당자 화면
- 컷전보 조회 및 수정
- 렌더 상태 / AE 상태 확인

### 2. Pipeline API

- Shot / Task / Version / StatusEvent CRUD
- Google Sheets 동기화
- 외부 DCC 클라이언트 인증 및 요청 처리

### 3. Workers

- 렌더팜 상태 폴링
- AE 자동화 트리거
- 시트 동기화 예약 작업

### 4. DCC Connectors

- Maya: 애니메이션 export, 카메라/캐시 publish
- Blender: 캐시 import, 렌더 세팅 반영, 렌더 상태 업데이트
- After Effects: 템플릿 열기, 소스 연결, 렌더큐 등록

## 데이터 모델

### Shot

- `project_code`
- `sequence_code`
- `shot_code`
- `scene_number`
- `cut_number`
- `title`
- `frame_start`, `frame_end`
- `fps`
- `status`
- `render_status`
- `ae_status`
- `assignee`
- `due_date`

### Task

- `shot_id`
- `task_type`
- `status`
- `assignee`
- `notes`

권장 `task_type`:

- `layout`
- `animation`
- `lighting`
- `render`
- `comp`
- `after_effects`
- `delivery`

### Version

- `shot_id`
- `task_id`
- `version_number`
- `dcc_app`
- `file_path`
- `preview_path`
- `status`
- `comment`

### StatusEvent

- `shot_id`
- `task_id`
- `event_type`
- `from_status`
- `to_status`
- `actor`
- `message`

## 상태 설계

샷 전체 상태와 세부 태스크 상태를 분리한다.

예시:

- Shot `status`: `ready`, `wip`, `review`, `approved`, `hold`, `delivered`
- Render `render_status`: `waiting`, `queued`, `rendering`, `complete`, `error`
- AE `ae_status`: `not_started`, `prep`, `comping`, `review`, `final`

## Google Sheets 연동 전략

### 권장 시트

- `ShotMaster`
- `TaskStatus`
- `Delivery`
- `Config`

### 동기화 방식

1. 시트 데이터를 읽어 정규화
2. `shot_code` 기준으로 upsert
3. 상태 변경은 이벤트 로그와 함께 저장
4. 선택적으로 시트에 역반영

## AE 연동 방향

1. API에서 샷 메타데이터 조회
2. JSX 또는 스크립팅 브리지로 템플릿 AEP 열기
3. 렌더 이미지/EXR/프리컴프 입력 경로 매핑
4. AE 태스크 및 버전 상태를 API에 업데이트

## 추천 다음 구현

1. 인증
2. 실제 Sheet 컬럼 맵
3. 상태 전이 규칙
4. DCC용 API client SDK
