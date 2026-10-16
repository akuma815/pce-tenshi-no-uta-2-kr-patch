# Z8.4 field source-key runtime result

## 판정

- 상태: **RUNTIME_SOURCE_KEY_PASS_DENOMINATOR_OPEN**
- 런타임 trace: **852행**
- field scene stream: **783회**
- START_HIT: **9회 / 고유 8개**
- source-key 수식 불일치: **0건**
- lookup ID/ISO 위치 불일치: **0건**
- scene identity 불일치: **0건**
- mode-06 전환: LBA 482@frame 1420, LBA 290@frame 2845, LBA 2882@frame 4188

오프라인 재생에서 확인한 정확한 시작 ID 8개가 새 BizHawk 런타임에서도
모두 관측됐다. source key 계산과 236행 lookup 왕복은 PASS다.

## 남은 차단 조건

이번 경로는 source-key 산식과 관측된 소비자를 검증했지만 236개 전체의
참조 분모를 닫지는 못했다. 미관측 228개에 대한 정적 event-bytecode
decoder 또는 동등한 전체 coverage가 확보되기 전에는 redirect/index를
생성하지 않는다.

이번 분석은 CUE/BIN/ISO를 수정하지 않았다.
