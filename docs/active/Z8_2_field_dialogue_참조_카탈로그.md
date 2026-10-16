# Z8.2 field dialogue 참조 카탈로그

## 판정

상태는 `LOADER_REFERENCE_PASS_TEXT_REFERENCE_DENOMINATOR_OPEN`다. `field.main_engine`이 소유하는 overlay directory
entry 2가 LBA 482의 96 sectors를 mode 06으로 physical bank `$68-$7F`에
적재하는 로더 참조는 정확히 한 개이며 원본 바이트 `0001E260`과 일치한다.

이 scene extent 안에는 dialogue 레코드 **236개**가 있다. 기존
장기 추적에서 실제 stream 소비가 확인된 것은 **9개**, 레코드
전체 바이트가 확인된 것은 **8개**다. 나머지
**227개**는 추출 경계와 원본 바이트는
확정됐지만 runtime 소비가 확인되지 않았다.

## 확정한 source key

논리 주소만 저장하지 않는다. 소비 시점의 MPR을 읽어 다음 scene-relative
offset을 계산한다.

`physical_bank = MPR[logical >> 13]`

`source_offset = (physical_bank - $68) * $2000 + (logical & $1FFF)`

236개 레코드의 source offset은 모두 24-bit little-endian으로 왕복되며
`$68-$7F` 범위 안이다. 이 키는 같은 scene package가 resident인 동안 MPR
page가 바뀌어도 동일하다.

## 아직 redirect/index를 만들지 않은 이유

- runtime에서 확인된 텍스트 레코드는 236개 중 9개뿐이다.
- 관측된 logical start 값을 scene 바이트에서 검색하면 우연 일치가 섞인다.
  따라서 literal byte scan 결과를 포인터 카탈로그로 승격하지 않았다.
- event bytecode의 모든 text-start 소비를 열거하는 정적 decoder 또는
  동등한 완전 runtime coverage가 아직 없다.
- 번역 컨테이너 저장 좌표, 적재 RAM, 수명, field stream reader hook ABI가
  아직 loader-owned 경계로 확정되지 않았다.

그러므로 `01/02` 프로토콜이나 임의 16-bit 포인터 보정은 사용하지 않는다.
다음 단계는 `$4293/$42DE/$42AB/$42BA` stream reader 경계에서 위 source key를
계산하는 read-only probe를 만들고, 관측된 9개 시작점의 키가 카탈로그와
일치하는지 검증하는 것이다.
