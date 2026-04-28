# SF Visual Pipeline

웹 중심 파이프라인의 첫 스캐폴드입니다.

이 프로젝트는 다음 흐름을 목표로 합니다.

- Google Sheets에서 컷전보/샷 메타데이터를 읽어옴
- 웹 API에서 샷, 태스크, 버전, 상태를 일관되게 관리함
- Maya, Blender, After Effects는 API를 통해 같은 데이터를 사용함
- 렌더/합성 상태를 웹에서 추적하고 자동화 작업으로 연결함

## 현재 포함된 내용

- `backend/`: FastAPI 기반 백엔드
- `frontend/mockup/`: 프로젝트 선택 / 샷 리스트 / Render 실행 흐름 웹 목업
- `docs/architecture.md`: 초기 아키텍처 문서
- `docs/nas-deployment.md`: NAS/Worker 배포 메모
- `docs/roadmap.md`: 단계별 개발 로드맵
- SQLite 기반 개발용 DB 설정
- Google Sheets 동기화 서비스 골격
- Shot / Task / Version / Status Event 모델

## 빠른 시작

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

브라우저:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

목업 확인:

`frontend/mockup/index.html`을 브라우저에서 열면 현재 화면 구조를 바로 볼 수 있습니다.

## 환경 변수

`backend/.env.example`를 참고해서 `.env`를 만들면 됩니다.

## 우선순위 다음 단계

1. Google Sheets 실제 인증 연결
2. ShotMaster 시트 컬럼 매핑 확정
3. `PipelineRun`, `PipelineStepRun` 추가
4. Maya / Blender / AE 클라이언트 추가
5. NAS 배포 구조 확정
