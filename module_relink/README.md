# module_relink

천외마경식 모듈 재링크 전략의 빌드 작업 폴더다. 원본 CUE/BIN은 이 폴더 밖에
있으며 모든 도구가 읽기 전용 입력으로 취급한다.

## Z2 identity build

```powershell
python tools\build_ziria_z2_identity.py
python tools\verify_ziria_z2_identity.py
```

생성 구조:

- `track02/segments/`: Track 02 전체를 빈틈과 중첩 없이 분할한 조립 단위
- `track02/logical_modules/`: primary/overlay 로더 표 55개씩의 논리 모듈 뷰
- `track02/semantic_modules/`: Z1에서 의미가 확인된 엔진·리소스·장면 패키지
- `track02/Track02_data.identity.iso`: 세그먼트만 이어 붙인 Track 02
- `output/`: 원본과 바이트 단위로 동일한 CUE/BIN identity rebuild
- `linker_layout.json`: Z3에서 사용할 bank·runtime 배치 계약

`output/`의 CUE/BIN은 배포 패치가 아니다. 모듈 분해와 재조립 파이프라인이 원본을
정확히 보존한다는 것을 증명하는 기준 산출물이다.

## Z3 section contract

- `specs/`: 모듈별 `original/extension_code/text/glyph/relocation` 계약
- `linked_identity/`: original section만 링크한 identity module
- `extension_registry.json`: sector allocation과 loader registration의 원자적 승인표

```powershell
python tools\build_ziria_z3_sections.py
python tools\verify_ziria_z3_sections.py
```

Z3 registry가 비어 있는 동안 모든 non-zero extension 요청은 실패하는 것이 정상이다.
