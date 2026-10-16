# Z8.3 field source-key read-only probe

## 정적/오프라인 판정

- lookup: **236개**, 24-bit scene-relative key 중복 0
- 기존 Z6 trace의 field scene stream read: **828회**
- 계산 key와 trace overlay offset 불일치: **0건**
- 계산 key와 Track02 ISO offset 불일치: **0건**
- 정확한 레코드 시작 hit: **8개**
- 레코드 내부까지 포함한 관측: **9개**
- Lua write-capable API 검출: **0건**

상태는 `OFFLINE_REPLAY_PASS_RUNTIME_CAPTURE_PENDING`이다. 기존 trace로 source-key
수식은 검증됐지만, 새 Lua가 현재 BizHawk 실행에서 정상 동작하는지는 별도
runtime 증거가 필요하다.

## 실행 절차

1. Lua 없이 게임을 실행해 첫 필드가 보일 때까지 진행한다.
2. BizHawk Lua Console에서 `tools/trace_ziria_z8_field_source_keys.lua`를 연다.
3. 첫 대화, Memo 진입·복귀, 첫 전투·필드 복귀, 탑 진입까지 진행한다.
4. `translation/ziria_z8_field_source_key_runtime_status.txt`와
   `translation/ziria_z8_field_source_key_runtime_trace.tsv`를 보존한다.

이 probe는 host 로그만 쓰며 게임 메모리, 입력, savestate, CUE/BIN/ISO를
수정하지 않는다.

## 런타임 후속 결과

2026-07-26 실제 BizHawk 경로 실행 결과는
`Z8_4_field_source_key_runtime_result.md`에 기록했다.

- trace 852행
- field scene stream 783회
- `START_HIT` 9회 / 고유 레코드 8개
- source-key 수식 불일치 0건
- lookup ID/ISO 위치 불일치 0건
- scene identity 불일치 0건

따라서 관측된 소비자에 대한 source-key 런타임 게이트는 PASS다. 다만
236개 전체 참조 분모는 아직 열려 있으므로 redirect/index는 생성하지 않았다.
