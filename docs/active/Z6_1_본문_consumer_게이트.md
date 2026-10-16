# Z6.1 본문 consumer 게이트

## 목적

Z6에서 확인하지 못했던 다음 두 실제 대사 본문 소비 경로가 공용 `$8754` 글리프를
정상적으로 처리하는지 검증한다.

1. 첫 필드에서 여는 Memo 기록의 실제 본문
2. 탑 진입 초상화 이벤트의 실제 대사 본문

Z6에서 검증한 화자명은 이번 단계에서 수정하지 않는다.

## 기준선

- 기준 빌드: Z6 family integration v1
- 기준 상태: `RUNTIME_PASS`
- 기준 BIN SHA-256:
  `D598B992BA0118641639BD811772CF17BF309C1B4D090C50E21E295DE28DF18E`
- 공용 글리프: `$8754` → `$9172`의 Galmuri8x8 `가`

## Expected Write

| consumer | Track02 주소 | 제어코드 뒤 원본 | Z6.1 |
|---|---:|---:|---:|
| 첫 필드 Memo 본문 | `0x011FA1F` | `95 95` | `87 54` (`가`) |
| 탑 진입 후 첫 대사 본문 | `0x05BA0F5` | `47 68` | `87 54` (`가`) |

- Memo는 `#1` 뒤의 압축 본문 토큰 두 바이트를 같은 길이의 raw 코드로 교체한다.
- 탑 대사는 `iso:05BA0EA` 레코드의 `#1` 뒤 첫 압축 토큰 두 바이트를 같은
  길이의 raw 코드로 교체한다.
- 화자명, `#1/#5`, 줄바꿈, 페이지, 종료자 및 후속 본문은 보존한다.

## 정적 검증

- Z6 대비 변경: 4바이트, 2개 연속 구간
- identity 대비 Z4+Z5+Z6+Z6.1 전체 변경: 46바이트
- Track02 섹터 수 및 전체 BIN 크기: 보존
- 변경 0:
  - 실행 코드
  - 글리프 레코드
  - 화자명
  - 전투 모듈
  - BIOS, MPR, Work RAM
  - loader table, audio, CUE track layout
- v2 출력 BIN SHA-256:
  `5F76640EC67713BFBF42F42D9B3C4E468DB537D5A3923FD27C87F6BF861C7C46`

## v1 런타임 결과와 수정

- PASS: 첫 필드 Memo 본문 `가`, Memo 복귀, 전투, 필드 복귀, 탑 진입,
  캐릭터·초상화 그래픽
- FAIL: 탑 진입 후 첫 대사 본문 `가`
- 원인: v1의 `0x05BA1B7`은 탑 진입 후 첫 대사가 아니라 뒤쪽 초상화 이벤트
  레코드 `0x05BA1AD`의 본문이었다.
- 런타임 화면에서 화자명만 `가`로 시작하고 본문은 원문으로 출력된 사실과
  `master_text.csv`의 `iso:05BA0EA` 레코드를 대조해 실제 본문 시작점을
  `0x05BA0F5`로 정정했다.
- v2는 Z6 기준선에서 다시 생성했으며 v1의 잘못된 변경은 상속하지 않는다.

## 런타임 게이트

1. 첫 필드 대사 본문 `가`
2. 첫 필드 Memo 본문 첫 글자 `가`
3. Memo 정상 복귀
4. 첫 전투 공격과 필드 복귀
5. 전투 후 탑 진입
6. 탑 진입 대사 본문 첫 글자 `가`
7. 초상화와 필드 캐릭터 그래픽 정상
8. 블랙 스크린, 잘못된 필드 전환, 프리징, `EXEC BRK` 반복 없음

## v2 런타임 판정

- 탑 진입 후 첫 대사 화자명 `가`: PASS
- 같은 레코드의 실제 본문 첫 글자 `가`: PASS
- 후속 본문 출력과 진행: PASS
- Memo 본문·복귀, 전투·필드 복귀, 전투 후 탑 진입: PASS
- 그래픽 손상, 블랙 스크린, 프리징: 없음

판정일: 2026-07-24

현재 상태: **Z6.1 v2 RUNTIME PASS**

## 산출물

- v1 빌더: `tools/build_ziria_z6_1_body_consumers.py`
- v1 매니페스트: `translation/ziria_z6_1_body_consumers_v1_manifest.json`
- v2 빌더: `tools/build_ziria_z6_1_body_consumers_v2.py`
- v2 매니페스트: `translation/ziria_z6_1_body_consumers_v2_manifest.json`
- 실행 CUE:
  `module_relink/z6_1_body_consumers_v2_shared_slot/output/Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z6_1_body_consumers_v2_shared_slot.cue`
