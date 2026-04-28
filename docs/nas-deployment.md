# NAS Deployment Notes

## 역할 분리

### NAS

- 웹 프론트엔드 호스팅
- FastAPI 백엔드 실행
- SQLite 또는 PostgreSQL 저장
- 프리뷰, 로그, 결과물 저장
- 작업 큐 브로커 또는 상태 저장

### Worker PC

- Maya 실행
- Blender 실행
- After Effects 실행
- NAS API에서 작업 요청을 받아 순차 처리

## 권장 공유 폴더

- `\\NAS\sf_pipeline\projects`
- `\\NAS\sf_pipeline\previews`
- `\\NAS\sf_pipeline\logs`
- `\\NAS\sf_pipeline\temp`

## 1차 배포 구조

```text
NAS
|- api
|- web
|- db
|- storage
`- logs
```

## 실행 흐름

1. 사용자가 웹에서 프로젝트와 샷을 선택
2. `Render` 버튼 클릭
3. API가 `PipelineRun` 생성
4. Worker가 대기열에서 작업 수신
5. Maya AnimOut 실행
6. Blender 렌더 실행
7. After Effects 가합성 실행
8. 결과물과 상태를 NAS에 반영

## 운영상 주의점

- NAS는 DCC 실행 머신으로 보지 않는다
- After Effects 자동화는 Windows Worker 전제가 필요하다
- 공용 경로 규칙을 먼저 고정해야 한다
- 상태 변경은 반드시 API를 통해 기록한다
