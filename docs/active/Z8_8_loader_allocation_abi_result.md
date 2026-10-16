# Z8.8 loader allocation 및 field reader ABI 결과

판정: **ABI_PASS_UNCHANGED_WIRE_ALLOCATION_FAIL**

## 확인된 ABI

- field stream 공용 진입점은 `$4036 -> JMP $4284`이다.
- reader 선택 우선순위는 `$55`, `$53`, `$2E69`, 기본 `$4B/$4C` 순서다.
- 네 경로 모두 다음 바이트를 `A`와 `$2D80`에 반환한다.
- `X`, `Y`는 보존된다.
- 기본 reader는 MPR2-4를 저장·복원하고 overlay reader는 MPR6을 저장·복원한다.
- `$54/$55` 임시 문자열은 NUL에서 포인터를 지운 뒤, NUL을 반환하지 않고 기본
  `$4B/$4C` stream의 다음 바이트를 즉시 반환한다.
- `$52/$53` 경로는 NUL을 그대로 반환한다.
- 원본 `field.main_engine` 안의 직접 `JSR $4036` 호출은 80개다.

이 결과로 cursor 및 continuation ABI는 정적으로 닫혔다.

## loader-owned 저장 공간 판정

동시에 살아 있는 bank 소유권은 다음과 같다.

- 현재 field scene: `$68-$7F`, 24 banks
- `field.main_engine`: `$80-$84`, 5 banks
- `field.resource`: `$85-$87`, 3 banks

따라서 확인된 `$68-$87` 32 banks 안에는 새 persistent bank가 없다. Z3 extension
registry도 승인된 allocation이 0개이며 `auto_sidecar`, `fill_run`, `implicit_gap`,
`shared_scene_bank`, `work_ram`을 금지한다.

LBA 482 장면의 235개 원문 문자열 범위를 전부 회수하는 가장 낙관적인 계산도 다음과
같다.

- 원문 회수 총량: 14,816 bytes
- 서로 겹치지 않는 연속 run: 229개
- 가장 큰 run: 344 bytes
- Z8.7 index: 2,852 bytes
- Z8.7 text: 14,640 bytes
- Z8.7 packed glyphs: 9,360 bytes
- Z8.7 총 자산: 26,852 bytes
- 총량 부족: 12,036 bytes

Z8.7은 index, text, glyph를 각각 연속 blob으로 정의한다. 가장 큰 회수 run이
344 bytes이므로 세 blob 가운데 하나도 배치할 수 없다. 총량도 부족하므로 단순한
fragment allocator만 추가해서 해결할 수도 없다.

## 게이트 결론

- reader ABI: **PASS**
- Z8.7 wire를 변경하지 않는 loader-owned allocation: **FAIL**
- CUE/BIN/ISO 생성: **BLOCKED**

이 판정은 기존 실패 패치를 되살리지 않는다. 원본 Track 02 ISO는 변경하지 않았다.

## 다음 단계

Z8.9에서는 저장 표현 자체를 버전업해야 한다.

1. `$4036` reader ABI는 그대로 보존한다.
2. `$68-$7F`가 battle/tower load 때 교체된다는 조건을 유지한다.
3. Z8.7의 연속 `target_offset` 의미를 그대로 사용하지 않는다.
4. glyph 총량을 줄이거나 장면별 glyph/text package로 나누는 방안을 비교한다.
5. 각 장면 loader가 소유한 범위와 접근 가능한 조각을 증명한 뒤에만 디스크 빌드를
   허용한다.

산출물:

- `translation/ziria_z8_8_loader_allocation_abi_manifest.json`
- `module_relink/z8_8_loader_allocation_abi/source_reclaim_ranges.tsv`
- `tools/build_ziria_z8_8_loader_allocation_abi.py`
- `tools/verify_ziria_z8_8_loader_allocation_abi.py`
