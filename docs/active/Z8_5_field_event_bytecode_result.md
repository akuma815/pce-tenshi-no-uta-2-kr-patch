# Z8.5 field event-bytecode 정적 참조 결과

## 판정

상태는 **STATIC_DENOMINATOR_PASS_BOUNDARY_REPAIR_REQUIRED**다.

기존 236행은 정적으로 다음과 같이 분해된다.

- opcode `02` 인라인 payload: 217행
- opcode `03` 인라인 payload: 10행
- opcode `14` 인라인 payload: 1행
- Memo 16-bit 포인터 테이블: 7행
- 대사로 잘못 검출된 가나 순차표: 1행

따라서 실제 text consumer 분모는 235개이며, 참조 소유자는 전부 열거됐다.
인라인 228개는 명령 바로 뒤의 NUL 종료 payload라 별도 포인터가 없다. Memo 7개는
`0x011F010..0x011F01D`의 little-endian 포인터로 모두 역참조된다.

## 차단된 경계

- `iso:010CAE1`, `iso:010D080`: opcode `02` payload의 앞부분이 master에서 누락됐다.
- `iso:011F011`: 실제 첫 Memo 문자열은 `0x011F01E`인데 master가 포인터 13바이트를
  문자열 앞부분으로 포함했다.
- `iso:010F080`: 가나 순차 lookup table 일부이며 text consumer가 아니다.

정확한 경계를 가진 232행만 현재 redirect 후보가 될 수 있다. 위 3개 경계를
수정하고 false positive를 제거하기 전에는 redirect/index를 만들지 않는다.

이번 단계는 분석 파일만 만들었으며 CUE/BIN/ISO는 변경하지 않았다.
