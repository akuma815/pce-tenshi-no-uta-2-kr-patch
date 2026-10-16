# 전체 텍스트 추출 결과

- 원본 ISO SHA-256: `7566073a2aa1f48e7b39ed2b34277d9935fade8a3fad7dcc72c21276e2632af9`
- 번역용 물리 레코드: 18,817건
- 500건 단위 CSV: 38개 (마지막 파일 제외 모두 500건)
- 원시 검수 후보: 308,373건
- 외부 번역 자산 목록: 6,284건

## 파일

- `batches_500/`: 실제 번역 작업용 CSV. ISO 오프셋 순서이며 500건 단위입니다.
- `master_text.csv`: 위 배치들을 합친 단일 원본입니다.
- `category_summary.csv`: 대사·메뉴 데이터·커맨드 등 범주/상태별 통계입니다.
- `forensic_candidates.csv`: 그래픽 오탐 가능성이나 로더 근거가 아직 없는 후보입니다.
- `external_asset_inventory.csv`: 기존 XLSX/CSV 자산과 ISO 일치 여부입니다.
- `coverage_report.json`: 재현성 및 완료 게이트입니다.

## 상태

- `verified`: 기존 런타임/대사 추출 경로로 확인된 문자열
- `verified_asset_cluster`: 기존 번역 자산과 일치하고 ISO에서 밀집 테이블을 이루는 문자열
- `verified_asset_match`: 4자 이상 외부 자산과 정확히 일치하는 ISO 문자열
- `needs_review`: 짧은 단독 일치라 사람이 용도를 확인해야 하는 문자열

`forensic_candidates.csv`와 `external_unconfirmed` 항목의 범위 판정이 끝나기 전에는
“누락 0건”으로 확정하지 않습니다.
