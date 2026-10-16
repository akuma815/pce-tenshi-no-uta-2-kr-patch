# Z8.6 field 경계 보정 및 source-key index 결과

## 판정

**BOUNDARY_REPAIR_PASS_SOURCE_INDEX_CLOSED**

- `iso:010CAE1` → `iso:010CABD`: 누락된 이동 통과 안내 prefix 복원
- `iso:010D080` → `iso:010D036`: 누락된 오토 배틀 안내 2페이지 복원
- `iso:011F011` → `iso:011F01E`: Memo 포인터 13바이트 제거
- `iso:010F080`: 가나 lookup table이므로 field 대사 인덱스에서 제외

`master_text.csv`는 기존 매니페스트의 불변 기준이므로 수정하지 않았다.
보정 내용은 overlay CSV에 기록했고, 이후 Z8 설계가 사용할 정본은
235행의 `ziria_z8_field_source_key_index.tsv`다. 보정된 ID와 source key는
각각 235개로 모두 유일하며 모든 raw record가 원본 ISO와 일치한다.

이번 단계에서는 CUE/BIN/ISO를 수정하지 않았다.
