# 천사의 시 II 한글화 재설계 Task — 폐기된 전략 기록

> **2026-07-18 폐기:** 이 문서의 공용 Work RAM `$2B0F` 훅, 전역 GETFNT
> 디스패처, CD_READ 후 sidecar 재적재 전략은 더 이상 구현 기준이 아니다.
> 전투 공격·필드 복귀·탑·메모 오버레이 전환에서 반복적으로 메모리 소유권을
> 침범했으므로 후속 변형을 금지한다. 새 작업의 유일한 기준은
> `Task_Ziria_Module_Relink.md`이며, 이 문서는 실험 이력과 실패 원인 보존용이다.

## 1. 목적

현재까지 확인된 런타임 증거를 기준으로, 화면을 손상시키지 않는 다중 한글 글리프 공급 구조와
전체 번역 재삽입 경로를 단계적으로 확정한다.

이 문서는 작업 순서와 통과 기준만 정의한다. **이 단계에서는 소스 코드, BIOS, BIN/CUE,
번역 CSV를 수정하지 않는다.** 각 Task는 이전 게이트가 PASS일 때만 착수한다.

### 새 빌드 폰트 정책

- 2026-07-17 이후 새로 생성하는 모든 한글 빌드는 `font/Galmuri8x8.ttf`만 사용한다.
- 고정 SHA-256: `97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05`.
- native 8×8 잉크를 12×12 PCE 셀 중앙 `(2,2)`에 배치하고 16×16/32바이트 MSB-first 글리프로 만든다.
- 폰트 해시 불일치, 누락 글리프 또는 12×12 초과 글리프는 빌드 실패로 처리한다.
- 기존 Galmuri11 기반 진단 스크립트와 잠긴 산출물은 과거 증거 재현용일 뿐 새 패치 빌드 입력으로 사용하지 않는다.
- 기계 판독 기준: `translation/font_build_policy.json`.

## 2. 현재 기준선

### 2.1 확정된 사실

- 필드 대사 렌더러는 System Card 3.0(J)의 `EX_GETFNT` mode 1을 사용한다.
- mode-1 글리프 저장 형식은 `0x30000 + compact_index * 18`의 12×12 packed 데이터이며,
  BIOS가 이를 32바이트 출력 형태로 확장한다.
- `8F6F`의 compact index는 1722이고 BIOS offset은 `0x37914`이다.
- index 1722의 원래 `出` 글리프를 `가`로 교체한 단일 글리프 BIOS는 정상 부팅·표시에 성공했다.
- 원문의 `よう` 두 바이트 `6F 2D`를 `8F 6F`로 정확히 치환한 빌드는 정상 화면,
  정상 페이지 전환, 한글 출력에 성공했다.
- 첫 대사 표본에서는 **같은 인코딩 바이트 수를 유지한 정확 치환**이 가능하다.

근거:

- `translation/system_card_one_glyph_probe_manifest.json`
- `translation/exact_substitution_probe_manifest.json`
- `walkthrough.md` Step 32~37

### 2.2 실패로 확정된 방식

- mode-0의 `0x10000 + index * 32`를 대사 폰트로 간주하는 방식
- EX_GETFNT가 계산할 수 있는 모든 compact index를 안전한 BIOS 폰트 슬롯으로 간주하는 방식
- 18개 또는 896개 BIOS 슬롯을 일괄 교체하는 방식
- 문자열의 남는 바이트를 ASCII `0x20`으로 채우는 방식
- 고정 Work RAM 또는 Super CD RAM을 전역 상주 번역·폰트 풀로 예약하는 방식
- 부트 시 전체 한글 폰트와 번역을 한 번에 적재하는 방식

18글자와 896글자 BIOS 진단은 System Card 시작 화면부터 전체 타일 손상을 만들었다. 두 글자
진단도 같은 증상을 만들었으므로, 현재 증거로는 index 1722 이외의 BIOS 슬롯을 안전하다고
승인할 수 없다. 두 글자 실패는 index 1720 추가와 index 1722 자형 변경을 함께 포함했으므로
어느 한 슬롯만의 문제라고 단정하지 않는다.

### 2.3 아직 증명하지 않은 범위

- index 1722 이외의 안전한 BIOS 교체 슬롯
- 본문 외 메뉴·전투·이름·아이템·이벤트 화면의 글리프 소비 경로
- 커스텀 코드 영역과 모든 파서·제어코드의 무충돌성
- 모듈별 한글 글리프 데이터의 저장 위치와 런타임 수명
- 전체 번역문을 수용하는 문자열 재배치·redirect 경로
- 각 대화창에서 허용되는 공백, 패딩, 줄바꿈, 페이지 종료 규칙

## 3. 채택 전략

### 3.1 목표 구조

릴리스 후보에서는 원본 System Card BIOS를 유지한다. 게임의 각 렌더 모듈에서
`EX_GETFNT` 호출을 모듈 로컬 훅으로 전환하고, 커스텀 한글 코드일 때만 현재 모듈과 같은
수명으로 적재된 지역 글리프 풀에서 글리프를 공급한다. 일본어와 원본 기호는 BIOS로 그대로
폴백한다.

```text
텍스트 바이트
  ├─ 원본 일본어/기호 ──> 원본 EX_GETFNT
  └─ 커스텀 한글 코드 ─> 모듈 로컬 GETFNT 훅
                           └─ 현재 모듈의 glyph map + glyph pool
```

원칙:

1. BIOS 내부의 추정 빈 슬롯을 추가로 사용하지 않는다.
2. 영구 RAM 폰트 풀을 만들지 않는다.
3. 글리프는 사용하는 슬롯·overlay·실행 모듈과 같은 수명으로 적재한다.
4. 첫 PoC에서는 문자열 재배치와 폰트 훅을 동시에 시험하지 않는다.
5. 첫 PoC는 원문과 동일한 바이트 수의 정확 치환만 사용한다.
6. 패딩 값은 렌더러별 실측 전까지 사용하지 않는다.
7. 모든 코드·데이터 쓰기는 Expected Write와 전체 diff 감사 대상으로 둔다.

### 3.2 커스텀 코드 후보

기존 연구 훅이 사용했던 SJIS lead `EB~EF` 범위를 우선 후보로 감사한다. 이는 확정 사양이
아니며 다음 조건을 모두 만족할 때만 채택한다.

- 게임의 모든 대상 텍스트 파서가 2바이트 문자로 전달한다.
- 제어코드, 종료자, redirect, continuation과 충돌하지 않는다.
- 원본 전체 모집단에서 기존 의미로 사용되지 않는다.
- 커스텀 훅이 처리하지 않는 렌더 경로로 유출될 때 빌드가 실패한다.
- 인코더, 디코더, 패키지 빌더, 검증기가 하나의 명시 매핑을 공유한다.

후보 범위가 불합격하면 다른 lead/pair를 자동 선택하지 않고 Task 2로 돌아간다.

## 4. 실행 Task

## Task 0 — 기준선 동결

목표: 성공·실패 산출물을 혼용하지 않는 재현 기준선을 고정한다.

- [x] 원본 BIN, CUE, System Card 3.0(J)의 크기와 강한 해시를 기록한다.
- [x] `exact_substitution_probe`를 필드 대사 가시성 PASS 기준으로 지정한다.
- [x] 896/18/2글자 BIOS 진단을 FAIL·사용 금지 목록으로 지정한다.
- [x] ASCII `0x20` 패딩을 금지 정책으로 지정한다.
- [x] BizHawk 코어, firmware identity, 실행 설정을 기준선에 연결한다.

산출물:

- 기준선 매니페스트
- 성공/실패 산출물 목록
- 재현 절차

통과 조건:

- 같은 이름의 산출물이 다른 내용으로 덮이지 않는다.
- 모든 후속 Task가 기준선 해시 불일치 시 시작 전에 실패한다.

Task 0 실행 결과 (2026-07-17): **PASS**.

- 기준선 SSOT: `translation/task0_baseline_manifest.json`
- 사람용 기준선·재현 절차: `Task0_기준선.md`
- fail-closed 사전검사: `python tools/verify_task0_baseline.py`
- 원본 입력, BizHawk 실행 환경, 승인 PASS 증거, 사용 금지 FAIL 증거 총 27개 파일의 크기와 SHA-256을 잠갔다.
- 후속 Task는 시작 전에 사전검사를 실행해야 하며 해시·CUE 연결·firmware override·코어 설정·런타임 판정 중 하나라도 다르면 종료 코드 1로 중단한다.
- Task 1 산출물은 현재 기준선에 대해 소급 사전검사 PASS로 기록했다.

## Task 1 — 렌더 경로와 EX_GETFNT ABI 전수 카탈로그

목표: 어느 호출부를 훅해야 하는지와 각 호출부의 live state를 확정한다.

- [x] 필드, 메뉴, 전투, 이벤트, 부트, 이름/아이템 화면의 GETFNT 호출부를 분리한다.
- [x] 각 호출부의 ISO 위치, 런타임 PC, 적재 LBA/크기, 목적 RAM bank, MPR 상태를 기록한다. 미관측값은 `unknown`으로 고정했다.
- [x] `$F8/$F9`, `$FA/$FB`, `$FF`, A/X/Y/P, 반환값의 live-in/live-out을 확인한다.
- [x] mode 0/1 분기와 18→32바이트 변환의 실제 소유자를 확인한다.
- [x] 같은 코드 사본과 overlay 재적재 사본을 구분한다.
- [x] 미확인 렌더 경로를 명시적으로 `unknown`으로 남긴다.

산출물:

- `renderer_id` 기반 호출부 카탈로그
- 모듈별 적재·상주·소비 수명표
- 첫 구현 대상 renderer 1개 선정 결과

통과 조건:

- 첫 PoC 대상인 필드 렌더러의 ABI와 모듈 수명이 완전히 설명된다.
- 훅이 보존해야 할 레지스터·MPR·zero-page 상태가 확정된다.

실패/불명확 시:

- 훅 구현을 시작하지 않고 디버거/Lua 추적으로 필요한 값만 추가 관측한다.

Task 1 실행 결과 (2026-07-17): **필드 renderer 구현 게이트 PASS**.

- 상세 문서: `Task1_GETFNT_카탈로그.md`
- 기계 판독 원장: `translation/getfnt_renderer_catalog.json`
- raw `20 60 E0` 22건 중 실행 코드 확정 18건, 미확정 raw match 4건
- 13개 호출은 99바이트 context가 동일한 `renderer.standard_overlay` 사본
- Task 4 런타임 정정 후 첫 구현 대상: `renderer.field_main` (`0x8667E` / PC `$967E`)
- 이전 `0x45855` / PC `$8855` 대상은 `cd_read_trace` LBA에 128섹터 bias를 중복 적용한 결과였으며 도달성 PoC에서 폐기했다.
- mode 1의 18→32 변환 소유자: System Card `$F2CC`
- 정정: mode 1 성공 후 `$FA/$FB`는 +32가 아니라 **+24**이며 마지막 8바이트는 현재 포인터 기준으로 0을 채운다.
- 메뉴/전투/이름/아이템, 카드, 후반 overlay의 런타임 MPR/loader 값은 `unknown`으로 유지하며 해당 renderer에는 훅을 삽입하지 않는다.

## Task 2 — 커스텀 코드 공간 판정

목표: 한글 코드를 원본 문자·제어 흐름과 모호성 없이 구분한다.

- [x] 전체 추출 raw bytes와 알려진 제어코드에서 `EB~EF` pair 사용 여부를 감사한다.
- [x] fetch parser가 후보 pair를 한 문자로 소비하는지 정적·런타임으로 확인한다.
- [x] look-ahead, 줄바꿈, 페이지 전환, redirect, continuation 경로를 함께 검사한다.
- [x] 후보 코드 수와 전체 번역 고유 글리프 수를 별도로 계산한다.
- [x] 모듈 로컬 재매핑을 사용할 경우 한 장면의 최대 활성 글리프 수를 계산한다.

통과 조건:

- 1글자 PoC용 코드 하나가 모든 관련 파서에서 무충돌로 전달된다.
- 코드 공간 부족 시 전체 레퍼토리와 활성 작업 집합 중 어느 예산이 병목인지 구분된다.

결과(2026-07-17): **필드 게이트 PASS**.

- `renderer.field_main`의 관련 주/보조/변수 fetch 경로에서 `EF41`을 Task 3 단일 PoC 코드로 승인했다.
- 정확한 2바이트 치환 런타임 관찰에서 뒤 문장과 다음 페이지 정렬이 유지됐다. 이는 파서 소비 증명이며 글리프 출력 증명은 아니다.
- 의미 경계 후보 940, raw-substring-absent 후보 844, 현재 고유 한글 904, 장면 최대 활성 한글 571이다. 전역 고정 매핑보다 장면 로컬 재매핑을 우선한다.
- 기존 `translation/char_map.json`, 일괄 `EB~EF` 매핑 및 비필드 렌더러는 승인하지 않는다.
- 상세 근거: `Task2_커스텀코드공간.md`, `translation/task2_custom_code_audit.json`, `translation/task2_custom_code_runtime.json`.

## Task 3 — 필드 모듈 로컬 GETFNT 훅 설계

목표: BIOS를 수정하지 않고 커스텀 글리프 한 개를 반환하는 최소 훅을 설계한다.

- [x] 첫 대사에서 실제 실행되는 호출부 하나만 대상으로 고정한다.
- [x] 기존 field module 내부의 검증된 코드 패딩과 데이터 패딩을 재감사한다.
- [x] 커스텀 코드이면 로컬 글리프를 공급하고, 그 외에는 원본 BIOS로 점프한다.
- [x] MPR을 바꾸면 TMA로 실제 값을 저장하고 모든 반환 경로에서 복구한다. 이번 설계는 MPR을 바꾸지 않는다.
- [x] stack page, BIOS 변수, 공용 Work RAM을 훅 저장소로 사용하지 않는다.
- [x] 원본 명령 효과, 분기 거리, 복귀 주소, 글리프 버퍼 증가 규칙을 명세한다.

우선 데이터 형식 후보:

1. 32바이트 expanded glyph — PoC가 단순하지만 저장량이 큼
2. 18바이트 mode-1 packed glyph — 저장량이 작지만 안전한 확장 루틴이 필요

첫 PoC에서는 32바이트 1글리프를 우선 검토한다. 이후 용량 감사 결과에 따라 18바이트
packed 형식으로 바꿀지 결정한다.

통과 조건:

- 훅·글리프·trampoline의 모든 바이트가 검증된 모듈 범위 안에 있다.
- 원본 일본어 경로의 입력과 출력이 바이트/상태 기준으로 동일하다.
- 커스텀 경로의 출력 32바이트가 기대 글리프와 일치한다.

결과(2026-07-17): **설계 게이트 PASS, Task 4 PoC 빌드 준비 완료**.

- 정정된 실제 호출부 `$967E`의 `JSR $E060`을 `JSR $C737`으로 바꾸는 직접 훅을 채택했다.
- `$C737..$C783`의 훅+`가` expanded 글리프는 77바이트이며, 457바이트 `FF` 창 안에 들어간다. 원본 JSR/JMP 참조는 0건이고 비실행 raw-word 겹침 6건은 감사 기록에 유지했다.
- 비커스텀 경로는 `JMP $E060`으로 원본 BIOS에 tail-call하며 반환 프레임 수가 원본과 같다.
- 커스텀 경로는 32바이트를 원래 목적지에 쓰고 A=`00`, X=`00`, Y=`FF`, `$FA/$FB`=`+24`, `$FF` 보존으로 반환한다.
- 코드와 데이터가 이미 MPR6=`84`에 있어 TMA/TAM, stack 임시 저장, BIOS 변수 및 공용 Work RAM을 전혀 사용하지 않는다.
- 원본 게임 이미지와 BIOS는 Task 3에서 수정하지 않았다. 상세 근거: `Task3_필드_GETFNT_훅설계.md`, `translation/task3_field_getfnt_hook_design.json`.

## Task 4 — 원본 BIOS 기반 1글자 훅 PoC

목표: 커스텀 코드→게임 모듈 글리프→VRAM 표시의 전체 연결을 검증한다.

- [x] 원본 BIOS를 사용한다.
- [x] 첫 대사의 원문 2바이트를 커스텀 코드 2바이트로 정확 치환한다.
- [x] 모듈 로컬 글리프 풀에는 `가` 한 글자만 둔다.
- [x] 문자열 길이, 페이지 제어, 화자명, 종료자는 변경하지 않는다.
- [x] System Card 시작 화면부터 다음 대사 페이지까지 새 실행으로 확인한다.

v2 최종 상태(2026-07-17): **정적 PASS / 런타임 PASS**. `EF41` 위치에서 Galmuri8x8
`가`가 출력됐고, 다음 페이지의 원본 `出`은 일본어로 유지됐으며 그래픽과 페이지 전환도
정상이었다. 자세한 산출물과 검증 결과는 `Task4_1글자_훅_PoC.md`,
`translation/task4_field_hook_poc_v2_manifest.json`,
`translation/task4_field_hook_poc_v2_runtime.json`에 기록한다.

PASS 기준:

- System Card, 타이틀, 인게임 그래픽이 정상이다.
- 커스텀 코드 위치만 `가`로 표시된다.
- 원문의 다른 `出`은 일본어 `出`로 남는다.
- 다음 페이지가 정상적으로 지워지고 진행된다.

이 PASS가 증명하는 범위:

- 원본 BIOS를 유지한 필드 대사 한 경로의 커스텀 글리프 공급

증명하지 않는 범위:

- 다글자 용량, 다른 renderer, 문자열 재배치, 전체 번역

## Task 5 — 필드 8~16글자 다글자 PoC

목표: BIOS 슬롯을 건드리지 않고 연속 한글과 local glyph map을 검증한다.

- [x] 현재 번역본에서 받침·복합모음이 포함된 짧은 표본을 선택한다.
- [x] 원문과 같은 인코딩 바이트 예산 안에서 사람이 승인한 표본을 사용한다.
- [x] 글리프 pool과 map을 같은 필드 모듈 수명으로 둔다.
- [x] ASCII `0x20` 패딩은 사용하지 않는다.
- [x] 남는 원문 tail은 보존하거나, 실제 공백/종료 정책이 확인된 경우에만 변경한다.

현재 상태(2026-07-17): **정적 PASS / 다글자 표시 PASS / 장면 전환 안정성 확인 대기**.
원문 16바이트 전체를
`준비는다됐나페이`의 완전한 2바이트 코드 8개로 치환했으며 패딩과 tail은 없다.
`EF58~EF5F` local map과 Galmuri8x8 글리프 page는 MPR6=`84`의 `$C800~$C8FF`에 둔다.
세부 기록은 `Task5_필드_다글자_PoC.md`, `translation/task5_field_multiglyph_map.json`,
`translation/task5_field_multiglyph_poc_manifest.json`이 소유한다.

런타임에서 `준비는다됐나페이` 8글자의 순서·자형, 일본어 폴백, 페이지 전환과 필드 그래픽은
PASS했다. 필드 재진입과 최소 20회 장면 전환 중 오염·`EXEC BRK` 부재는 아직 확인하지 않았으므로
Task 5 전체 PASS로는 승격하지 않는다.

PASS 기준:

- 8~16개 글리프가 서로 뒤바뀌지 않고 표시된다.
- 페이지 전환, 재진입, 같은 화면의 일본어 폴백이 정상이다.
- 최소 20회 장면 전환 뒤에도 오염이나 `EXEC BRK`가 없다.

Task 5 개정 결과(2026-07-17): **관찰 게이트 PASS**. 실행 훅은 MPR2=`80`의
`$5230`으로 이동하고, MPR6=`84`의 `$C800~$C8FF`는 비실행 글리프 데이터 전용으로
분리했다. 같은 실행에서 한글 8글자와 메모 진입이 정상임을 확인했다. 승인 범위는 첫 필드
8글자·BIOS fallback·메모 진입이며, 전체 장면/renderer/장시간 안정성은 후속 QA 범위다.
근거는 `translation/task5_5230_codebank_multiglyph_poc_manifest.json` 및
`translation/task5_5230_codebank_multiglyph_poc_runtime.json`이다.

## Task 6 — 모듈별 글리프 예산 산정

목표: 전체 레퍼토리와 활성 작업 집합을 분리하여 실제 병목을 계산한다.

- [x] 현재 번역 CSV에서 전체 고유 한글 수를 집계한다.
- [x] physical grid, scene/system loader, menu/battle module별 고유 글리프를 집계한다.
- [x] 32바이트와 18바이트 저장 형식 양쪽의 필요량을 계산한다.
- [x] 문자열 package, glyph map, glyph pool, manifest, hook을 함께 합산한다.
- [x] 중복 core glyph의 복제 비용과 영구 상주 위험을 비교한다.
- [x] 현재 96-sector slot/overlay 제한과 각 모듈 padding에 대조한다.

산출물:

- 모듈별 `string_bytes`, `glyph_count`, `glyph_bytes`, `hook_bytes`, `slack_bytes`
- overflow 모듈 목록과 정확한 부족량

통과 조건:

- 모든 모듈이 `fit` 또는 명시된 overflow branch 중 하나로 분류된다.
- 전체 896자 같은 전역 수치를 각 장면의 활성 예산으로 오용하지 않는다.

Task 6 실행 결과(2026-07-17): **용량 게이트 PASS / 릴리스 빌드 입력 차단 17건**.

- 최신 `master_text.csv` 18,817행에서 고유 한글 1,053자, 제어코드 순서 불일치 0건을 확인했다.
- 전역 940-code 후보는 113자 부족하지만 단일 loader 최대 활성 집합은 609자이므로 지역 재매핑은 성립한다.
- 85개 loader를 32바이트 기준 직접 FIT 28개, source-hole 재료화 분기 14개, scene-load sidecar 분기 43개로 전부 분류했다.
- 18바이트 기준은 직접 FIT 추정 39개, source-hole 분기 4개, sidecar/module split 42개다. 확장기 PoC 전에는 구현 PASS가 아니다.
- physical grid 55개와 메뉴·전투 renderer 수요 55개를 별도 집계했다. 전역 semantic 합계를 동시 상주량으로 사용하지 않는다.
- `needs_review` 17행은 용량에는 포함했으나 릴리스 빌드 입력에서 차단한다.
- 상세 문서: `Task6_모듈별_글리프_예산.md`
- 기계 판독 원장: `translation/task6_module_glyph_budget.json`
- 검토 워크북: `outputs/019f55dd-966e-7f81-aed7-0f92ef88e1c9/Task6_module_glyph_budget.xlsx`
- 검증: `python -X utf8 tools/verify_task6_module_budgets.py` PASS.

## Task 7 — overflow 글리프 공급 분기

Task 6 결과에 따라 아래 순서로 선택한다.

진행 상태(2026-07-18): **공통 Work RAM `$2B0F` packed-18 훅이 한글·메모·전투·탑 회귀 PASS**.

- [x] Task 5의 packed-18 데이터 ABI는 유지하되, 전투 회귀에 실패한 `$5230` 실행 소유권은 폐기한다.
- [x] 12×12 18바이트 레코드를 기존 16×16 32바이트 출력 ABI로 전개하는 최소 PoC를 생성한다.
- [x] Galmuri8x8 8글리프의 `18B → 32B` 왕복과 Expected Write·전체 BIN diff를 검증한다.
- [x] BizHawk HuC6280 전체 디스어셈블러로 128바이트/71명령 및 모든 분기·JSR 경계를 검산한다.
- [x] 실제 화면에서 8글리프, 일본어 BIOS fallback, 필드 메뉴와 메모 진입을 확인한다.
- [x] 런타임 PASS 뒤 최신 85개 loader를 Branch A/B/C로 분류한다.
- [x] 필드→메모→전투→공격→필드 복귀 3,122프레임에서 Work RAM 읽기·쓰기를 장기 추적한다.
- [x] `$2AFF..$2C8E` 400바이트 후보의 direct page·stack·BIOS 변수·기존 실험 구간 충돌을 감사한다.
- [x] 첫 필드 로드 뒤 후보를 초기화하고 `JMP $F124`만 실행하는 중립 PoC를 통과시킨다.
- [x] 탑 `LBA 2882`까지 장기 추적해 기존 `$2AFF..$2B0E` 겹침을 발견하고 `$2AFF` 승인을 폐기한다.
- [x] 두 추적의 공통 미접근 구간 `$2B0F..$2C8E`에서 중립 PoC로 탑을 통과시킨다.
- [x] packed-18 훅을 `$2B0F..$2B8D`로 재조립해 한글·fallback·메모·전투·탑 회귀를 통과시킨다.
- [ ] 17개 Branch C loader 중 대표 단위에서 sidecar RAM 수명 PoC를 통과시킨다.

현재 PoC: `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_task7_packed18_expander_poc.cue`

- 글리프 저장량: 256바이트 → 144바이트(43.75% 절감)
- 정적 검증: `python -X utf8 tools/verify_task7_packed18_expander_poc.py` PASS
- 기계어 검산: `dotnet run --project tools/huc6280_disasm_verifier/huc6280_disasm_verifier.csproj -- translation/task7_packed18_expander_poc_manifest.json` PASS
- 런타임 결과: 두 번째 한글 대사, 다음 일본어 fallback 대사, 메모 진입 모두 PASS.
- 18바이트 기준 loader 분류: 모듈 내부 42개, source-hole/Task 8 의존 26개, sidecar 17개.
- 17개 sidecar shard는 22/150섹터만 사용하고 최대 장면 임시량은 4,140바이트다.
- 정적 분류 원장: `translation/task7_overflow_supply_plan.json`
- 남은 블로커는 디스크 용량이 아니라 장면 로드부터 마지막 글리프 소비까지 유지되는 loader-safe RAM이다.
- `$2AFF..$2C8E`는 부팅 전에 비어 있는 RAM이 아니다. 이전 전역 추적에서 400바이트 중 379바이트가
  프레임 121/135/502에 기록됐다. 또한 탑 경로는 선두 `$2AFF..$2B0E` 안의 주소를 사용하므로
  `$2AFF` 훅 승인은 폐기됐다. 두 경로의 공통 후보는 `$2B0F..$2C8E` 384바이트뿐이다.
- 이 공통 구간도 첫 필드 로드 완료 뒤 초기화하는 코드 후보일 뿐이며, 4,140바이트 sidecar 저장소로
  일반화하지 않는다.
- 장기 추적 판정: `translation/task7_work_ram_lifetime_verdict.json`.
- 충돌 감사: `translation/task7_work_ram_candidate_audit.json`.

### Branch A — 모듈 내부 수록

현재 모듈 tail/hole에 문자열·map·glyph를 함께 둔다. 가장 단순하며 수명이 명확하므로 우선한다.

### Branch B — core glyph 복제

공통 고빈도 글리프를 필요한 모듈에 복제한다. 디스크 중복을 허용하되 영구 RAM 포인터를 만들지 않는다.

### Branch C — scene-load-time sidecar

모듈 내부에 들어가지 않을 때만 검토한다. LBA 9178 sidecar의 글리프 subset을 장면 로드 시점에
읽고, 마지막 소비까지 보존되는 RAM 구간을 런타임 수명 추적으로 증명해야 한다.

금지:

- 문자 출력 중 CD 읽기
- 근거 없는 3KiB/4KiB Work RAM 고정 예약
- scene 종료 뒤에도 남는 전역 포인터
- 빈 sector/zero run만으로 공간을 승인하는 것

## Task 8 — 문자열 재배치 경로 결합

목표: 글리프 공급 PoC가 통과한 뒤에만 긴 번역 문자열을 연결한다.

- [ ] 기존 fetch hook 참조 모델과 physical grid/overlay topology를 기준선으로 재검증한다.
- [ ] redirect와 continuation이 실제 stream 우선순위를 보존하는지 확인한다.
- [ ] 원문 내부 참조, 공유 tail, 중복 문자열을 해결한다.
- [ ] 패딩 대신 NUL·페이지·줄 종료의 renderer별 정책을 적용한다.
- [ ] 첫 대표 단위는 대사 한 블록만 재배치한다.

PASS 기준:

- 긴 한글 대사 한 블록이 잘림 없이 표시된다.
- 다음 대사, 분기, 이벤트, 페이지 진행이 원본과 동일하다.
- fetch hook과 GETFNT hook이 MPR/zero-page/stack 상태를 서로 오염시키지 않는다.

## Task 9 — renderer별 확대

다음 순서로 각각 독립 PoC와 회귀를 통과시킨다.

1. 필드 일반 대사
2. 필드 이벤트/scene loader 대사
3. 메뉴·아이템·장비·이름
4. 전투 메시지
5. 카드/미니게임
6. 부트·후반 특수 이벤트

한 renderer의 PASS를 다른 renderer로 일반화하지 않는다. 각 경로는 별도 hook identity,
글리프 package, 레이아웃 기준을 가진다.

## Task 10 — 빌드 게이트 통합

- [ ] 원본 리비전 강한 해시 검사
- [ ] 매핑 누락 0건
- [ ] 제어코드·종료자 보존
- [ ] 모듈별 용량 초과 0건
- [ ] hook signature·branch·overlap 검증
- [ ] MPR/ABI 정적 검증
- [ ] Expected Write 사전 계획과 전체 diff 감사
- [ ] BIN 크기·CUE track 보존
- [ ] xdelta 적용 결과와 목표 BIN 동일성
- [ ] 실패 진단 BIOS/CUE가 릴리스 입력에 포함되지 않는지 검사

하나라도 실패하면 BIN/xdelta 릴리스 산출물을 만들지 않는다.

## Task 11 — 번역 확대와 QA

폰트·문자열 E2E 게이트가 통과한 renderer부터 500개 CSV 배치 단위로 진행한다.

- [ ] 빌드에 포함할 행은 번역·제어·레이아웃 검토 상태를 분리한다.
- [ ] 자동 잘림은 금지하고 초과 항목을 검토 큐로 보낸다.
- [ ] 고유명사·힌트·선택지는 의미 손실 없는 번역만 승인한다.
- [ ] 메뉴 폭, 대화창 2/3줄, 페이지 수, 전투 타이밍을 경로별로 검사한다.
- [ ] 장면 전환, 저장/로드, 전투 진입/이탈, 메뉴 반복 진입을 회귀한다.

최종 종료 조건:

- 목표 텍스트 모집단의 미처리 항목 0건
- 매핑되지 않은 글리프 0건
- 알려진 화면 깨짐·진행 정지·`EXEC BRK` 0건
- 원본과 비교해 의도하지 않은 그래픽 차이 0건
- 배포 패치 재적용 결과가 검증 BIN과 동일

## 5. 우선순위와 중단 조건

### 즉시 수행 순서

1. Task 0 기준선 동결
2. Task 1 필드 렌더러 ABI/수명 확정
3. Task 2 커스텀 코드 1개 승인
4. Task 3 필드 로컬 GETFNT 훅 설계
5. Task 4 원본 BIOS 1글자 훅 PoC
6. Task 5 필드 다글자 PoC

Task 4가 PASS하기 전에는 전체 글리프 생성, 전체 번역 재삽입, 다른 renderer 훅을 진행하지 않는다.

### 중단 조건

- 원본 BIOS에서도 커스텀 코드가 파서 단계에서 모호하게 소비됨
- 필드 모듈 안에 검증 가능한 hook/data 공간이 없음
- ABI·MPR 상태를 모든 반환 경로에서 보존할 수 없음
- 모듈/scene 수명과 글리프 pool 수명을 연결할 수 없음
- 다글자 PoC에서 화면 손상이나 진행 불가가 재현됨

중단 시에는 증상을 가리는 새 BIOS 슬롯이나 임의 RAM 주소를 시도하지 않고, 처음 끊긴
저장→적재→상주→소비 경계로 돌아간다.

## 6. 최종 설계 판정

현재 권고안은 다음과 같다.

| 항목 | 판정 |
|---|---|
| 단일 BIOS 글리프 교체 | 진단용 PASS, 릴리스 구조로 확장 금지 |
| 다중 BIOS 슬롯 교체 | FAIL |
| 동일 바이트 정확 치환 | PASS, 제한적 PoC 용도 |
| ASCII `0x20` 패딩 | FAIL |
| 전역 상주 RAM 폰트 | FAIL |
| 모듈 로컬 GETFNT 훅 + 지역 글리프 subset | **우선 구현 후보** |
| 전체 번역 재배치 | 폰트 훅 E2E PASS 이후 진행 |

이 전략의 첫 번째 성공 기준은 “더 많은 글자를 BIOS에 넣는 것”이 아니다. **원본 BIOS를
사용한 상태에서 커스텀 코드 한 글자를 게임 모듈의 글리프 데이터로 정상 출력하는 것**이다.
이 게이트를 통과해야만 다글자와 전체 번역으로 확대한다.
