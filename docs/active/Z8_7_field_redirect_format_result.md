# Z8.7 field redirect wire format 결과

판정: **WIRE_FORMAT_PASS_LOADER_ALLOCATION_AND_ABI_OPEN**

- Z8.6에서 확정한 235개 corrected consumer를 source key 오름차순으로 직렬화했다.
- 인덱스는 32바이트 헤더와 12바이트 고정 레코드 235개로 구성된다.
- 레코드는 source key, 번역 대상, 원문 길이, 번역 길이, consumer kind, continuation flags를 포함한다.
- inline consumer는 번역 NUL 뒤 `source_key + original_length`로 복귀하고, Memo는 native pointer-string return을 사용하도록 형식에서 구분했다.
- 520개 한글을 Galmuri8x8 기반 단일 field-local 코드표로 생성했다(여유 420개).
- 문자열 blob은 14640바이트이며 8 KiB 경계 교차는 0건이다.
- 원문에 마커를 쓰지 않으며 lookup miss는 원문 경로를 그대로 사용한다.

아직 확정하지 않은 것:

- loader-owned sector/LBA 배치
- field renderer hook entry와 실제 cursor/continuation ABI
- packed18 글리프의 적재·확장 목적지와 수명
- relocation 및 branch reachability

따라서 CUE/BIN/ISO는 생성하거나 수정하지 않았다. 다음 게이트는 위 네 항목 중
loader-owned 배치와 renderer ABI를 함께 증명하는 것이다.
