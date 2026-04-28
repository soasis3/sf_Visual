# Apps Script Thumbnail Extractor

셀 안에 붙여넣은 Google Sheets 썸네일은 Sheets REST API에서 값처럼 잘 읽히지 않습니다.

이 프로젝트에는 원본 시트를 수정하지 않고 썸네일을 읽기 위한 Apps Script 초안이 포함되어 있습니다.

파일:

- [thumbnail_export.gs](/C:/Users/hwang/Desktop/codex/sfVisual/tools/apps_script/thumbnail_export.gs)

## 왜 필요한가

- 현재 샷리스트의 `B열 Thumbnail`은 `=IMAGE(...)` 수식이 아니라 셀 안 이미지입니다.
- Sheets REST API에서는 이 값이 빈 셀처럼 보이는 경우가 많습니다.
- Apps Script의 `CellImage`는 `getContentUrl()`로 Google-hosted URL을 읽을 수 있습니다.

공식 참고:

- [CellImage | Apps Script](https://developers.google.com/apps-script/reference/spreadsheet/cell-image)
- [Sheets API CellData](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/cells)

## 사용 방식

1. Google Apps Script에서 새 standalone project 생성
2. `thumbnail_export.gs` 내용 붙여넣기
3. 한 번 실행해서 권한 승인
4. 필요하면 Web App으로 배포

## 엔드포인트 예시

- 전체 씬 목록:
  `.../exec`
- 특정 씬 샷 + 썸네일:
  `.../exec?scene=0010`

## 기대 결과

- `sceneList`는 기존처럼 읽음
- 특정 씬의 `Direction Note`에서 `Shot`, `Thumbnail`, `Duration` 추출
- 셀 안 이미지면 `preview_image_url`에 `getContentUrl()` 결과 저장 시도

## 주의점

- `getUrl()`은 공식 문서상 많은 신규 이미지에서 비어 있을 수 있습니다.
- `getContentUrl()`도 Google-hosted 임시 URL일 수 있으니 캐싱 전략이 필요할 수 있습니다.
- 이 스크립트는 읽기 전용으로 작성되어 원본 시트 값을 수정하지 않습니다.
