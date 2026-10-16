# Z8.9 설계 — field family 확장 등록 (Z3 트랜잭션 실사용)

상태: **DESIGN_DRAFT — 구현·디스크 빌드 없음**
작성일: 2026-07-27
입력 판정: Z8.8 `ABI_PASS_UNCHANGED_WIRE_ALLOCATION_FAIL`
상위 문서: `Task_Ziria_Module_Relink.md`, `Z3_모듈_섹션_확장_규약.md`, `Z8_8_loader_allocation_abi_result.md`

## 1. 해결해야 할 수치

Z8.8에서 확정된 부족량이 이 설계의 입력이다.

| 항목 | 값 |
|---|---:|
| Z8.7 자산 총량 (index+text+glyph) | 26,852 B |
| LBA 482 장면 원문 회수 총량 | 14,816 B |
| 회수 run 최대 연속 길이 | 344 B |
| 총량 부족 | 12,036 B |
| 연속성 | 세 blob 모두 배치 불가 |

결론: **회수 공간만으로는 총량·연속성 양쪽에서 실패**하므로, (1) 새 공간의 등록과
(2) 연속 blob을 전제하지 않는 wire 버전업이 함께 필요하다.

## 2. 이번 설계에서 새로 실측한 사실 (2026-07-27, 원본 무수정 판독)

`extracted_bin/Track02_data.iso` 판독 결과이며 디스크는 변경하지 않았다.

### 2.1 장면 디렉터리는 96섹터 슬롯 격자다

- scene 테이블(ISO `0x83531`, 55 entries): LBA 290부터 stride 96.
  다수 엔트리의 sector count가 96 미만이다
  (예: entry 4 = LBA 578/78, entry 24 = LBA 2498/71, entry 25 = 2594/71).
- primary 테이블(ISO `0x424A5`, 55 entries): LBA 162/354부터 별도 격자.
  두 테이블의 extent는 서로 **겹치고 끼어든다**
  (예: primary entry 2 = LBA 354/75는 scene entry 0(290/96)과 1(386/96) 사이에 걸침).
- 따라서 "슬롯 꼬리 = 빈 공간"은 성립하지 않는다. 반드시 두 테이블 합집합
  기준으로 판정해야 한다.

### 2.2 두 테이블 합집합 기준 미참조 디스크 구간 (후보)

두 55-entry 테이블 + 알려진 엔진/부트 모듈 extent의 합집합을 뺀 Track02(총 9,328섹터)
미참조 구간:

| LBA 구간 | 섹터 | 바이트 |
|---|---:|---:|
| 1822–1826, 2100–2114, 2189–2210, 2286–2306, 2569–2594 | 84 | 172,032 |
| 4498–4514, 4596–4610, 4691–4706, 4787–4802, 4892–4898, 4974–4994, 5070–5090, 5174–5186 | 118 | 241,664 |
| 5474–6018 (scene 테이블 마지막 extent 뒤) | 544 | 1,114,112 |
| 6050–9328 (primary 테이블 마지막 extent 뒤) | 3,278 | 6,713,344 |
| **합계** | **4,024** | **8,241,152** |

주의: 이 수치는 **두 테이블 기준의 후보일 뿐**이다. ADPCM/음성/세이브 등 테이블을
경유하지 않는 CD_READ가 이 구간을 읽을 수 있으므로, Z8.9a의 참조 감사를 통과하기
전에는 어느 섹터도 승인하지 않는다 (Z3: "loader 등록 없는 신규 LBA 사용 금지"와
"fill run을 빈 공간으로 추정 금지" 준수).

### 2.3 장면 패키지에는 꼬리 fill이 없다

LBA 482/290/2882 세 패키지 모두 마지막 섹터까지 밀집 데이터다
(482의 말미 fill run은 132바이트뿐, 2882는 515바이트).
따라서 **RAM `$68-$7F` 안의 여유를 정적 fill 관찰로 승인할 수 없고**, 장면 RAM의
cold 구간은 런타임 read-coverage로만 증명할 수 있다.

## 3. 설계 결론 — 2단 할당 + wire v2

RAM이 진짜 제약이다(`$68-$87` 32 bank 전부 소유자 확정, persistent free bank 0개).
따라서 확장은 다음 2단으로 설계하고, A-1이 부족할 때만 A-2를 승인한다.

> **2026-07-27 갱신:** Plan A-1은 canary 2차 게이트에서 **구조적으로 폐기**됐다.
> LBA 482 extent의 78/96섹터가 primary(grid) 테이블 엔트리(450/78, 546/84)와
> 디스크를 공유하므로, 482 컨텍스트 cold 바이트도 다른 맵 로드에서 그래픽으로
> 사용된다. 482 전용 창(`0x17000..0x20000`)의 용량은 필요량에 미달한다.
> 활성 경로는 **Plan A-2**이며, 원본 482 extent를 0바이트 변경으로 유지한다.

### Plan A-1 — 장면 패키지 내부 cold 구간의 in-package 할당 (폐기됨)

증명된 cold 구간(§5)과 원문 회수 run(14,816 B)을 **패키지 내부에서 그대로** 번역
자산 저장소로 쓴다.

- 디스크 쓰기는 원본 96섹터 extent 안의 cold/회수 바이트에 한정된 **in-place
  고정 크기 덮어쓰기**다 (Sample 패치가 실증한 원칙과 동일).
- 기존 `mode 06` 96섹터 read가 자산을 자동 적재하므로 **로더 코드·테이블 변경이
  0바이트**이고, 수명은 장면 교체와 정확히 일치한다 (Z3 `owning_family_only` 자동
  충족).
- Z3 등록 트랜잭션은 "신규 LBA" 대신 "기존 extent 내 오프셋 범위"로 등록한다.
  sector allocation = 대상 extent 내 byte range, loader patch = 없음(기존 entry 2가
  소유), load condition = entry 2 로드, 수명 = 다음 mode-06 read.

### Plan A-2 — 미참조 섹터의 번역 모듈 + 로더 2차 read (A-1 부족 시)

cold+회수 합계가 자산 총량에 미달할 때만:

- §2.2 감사 통과 구간에서 장면당 전용 번역 extent를 할당한다.
- `field.main_engine` 로더의 `$66FC: JSR $E009` 복귀점(`$66FF`) 직후에 훅을 넣어,
  로드된 entry가 번역 extent를 가진 장면일 때만 2차 `$E009` read를 수행한다.
  - 목적지는 **A-1과 같은 방법으로 증명된 장면 RAM cold 구간**이다. 목적지 증명
    없이 2차 read를 승인하지 않는다.
  - `$F8-$FF` zero-page 인자와 A/X/Y, MPR은 원본 로더가 이미 소유한 상태에서만
    사용하고 복귀 전 원상 복구를 정적 검증한다.
- 훅 코드 공간은 새로 감사한다. Task3의 `$C737` FF 창은 Z4 v1에서 Memo 손상을
  일으켰으므로 **재사용 금지**. 후보는 (1) 로더 루틴 인접 미사용 코드 감사,
  (2) Z3 relink로 `field.main_engine` 모듈 자체를 재링크해 만든 명시적
  `extension_code` section 순서로 검토한다.

### Wire v2 — fragment 기반 저장 표현 (Z8.7에서 버전업)

Z8.8 지시("연속 `target_offset` 의미를 그대로 사용하지 않는다")에 따라:

1. **region table**을 추가한다: 승인된 저장 구간(cold 구간, 회수 run, A-2 extent)의
   `(base_source_key, length)` 목록. 최대 run 344 B 같은 조각도 등록 가능하다.
2. index 레코드의 target은 `region_id + region 내 offset`으로 바꾼다.
   레코드당 번역 text는 단일 region 안에 있어야 한다(레코드 내부 분할 금지 —
   reader 연속성 단순화). 평균 번역 62 B, 최장 레코드는 배치기가 큰 region에
   우선 배정한다.
3. glyph는 18 B 단위로 자유 분할 가능하므로 glyph map에 region 좌표를 넣는다.
4. index 자체(2,852 B)는 연속이 필요하므로 **가장 큰 단일 region**에 배치하며,
   이것이 index 최소 region 크기 요구가 된다. 부족 시 index를 2-level로 분할한다
   (source key 상위 바이트로 버킷).
5. `$4036` reader ABI, `A/$2D80` 반환, MPR 저장·복원, NUL continuation 규약은
   Z8.8 확정 그대로 보존한다. 원문 stream 재개 규칙(`source_key +
   original_length`)도 유지한다.
6. 용량 보조: 번역 text의 사전(bigram/음절) 압축을 선택 사양으로 두되,
   **압축은 A-1/A-2 합계가 부족할 때만** 도입한다(전개 코드 = 추가 코드 공간
   비용이므로 공짜가 아니다).

## 4. Z3 등록 트랜잭션 매핑

| Z3 요구 항목 | 이 설계의 값 |
|---|---|
| 소유 module/family | `scene.field_start`(entry 2) / field family |
| 물리 LBA·capacity | A-1: LBA 482 extent 내 byte ranges / A-2: 감사 통과 신규 extent |
| runtime physical bank | cold 구간이 속한 `$68-$7F` bank (증명 결과로 확정) |
| loader table patch | A-1: 없음 / A-2: 로더 훅 + 장면→번역 extent 매핑표 |
| load condition | entry 2 mode-06 read 완료 시 |
| 수명 종료 | 다음 장면 mode-06 read (battle/tower 전환) |

금지 항목은 Z3 그대로: Work RAM 실행, auto sidecar, `$68-$7F` cross-family
persistent, fill run 추정, 미등록 LBA.

## 5. 게이트 분해 (각각 fail-closed, 순서 고정)

### Z8.9a — 디스크 참조 전수 감사

- [ ] 두 55-entry 테이블 + 엔진/부트/오프닝 extent의 정적 합집합 재계산
- [ ] 기존 장기 trace 전부(Z1/Z6/Z8 v4, Task7)의 CD_READ LBA 로그를 합집합에 대조
- [ ] 테이블 비경유 read(ADPCM/음성 등)의 LBA 산출 코드를 정적 확인
- [ ] §2.2 후보 중 "어떤 정적 참조·런타임 read에도 걸리지 않는" 섹터만 승인 목록화

PASS: 승인 목록의 각 섹터에 대해 참조 0건이 정적+런타임 양쪽에서 증명된다.
FAIL 시: 해당 섹터 제외. 목록이 비어도 A-1은 진행 가능(디스크는 A-2에만 필요).

### Z8.9b — 장면 RAM cold 구간 증명 (핵심 게이트)

- [ ] BizHawk에서 `$68-$7F` 192 KiB 전 구간 read-coverage 추적 probe 작성
      (기존 Task7 Work RAM 추적 인프라 재사용, host 파일 기록만)
- [ ] 회귀 경로(첫 대사 → Memo → 전투 → 복귀 → 탑) + 해당 장면의 확장 QA 경로
      (모든 NPC 대화, 모든 진입 가능 이벤트)에서 read된 offset을 수집
- [ ] 미접근 구간 후보를 도출하고, 원문 회수 run과 병합해 region 후보표 작성
- [ ] **canary 검증**: 후보 구간을 trap 패턴으로 채운 진단 빌드로 같은 QA 경로를
      재주행하고, 화면·진행·오디오 차이 0건 + 후보 구간 read 0건을 재확인
- [ ] 후보별 `(bank, offset, length)`와 증거 trace를 registry 초안에 기록

PASS: canary까지 통과한 region 합계가 wire v2 배치 요구(index 연속 요구 포함)를
충족한다.
부족 시: (1) text 압축 도입 재평가 → (2) A-2 승인 절차로 이관.
한계 명시: read-coverage는 주행한 경로에 대한 증명이다. 미주행 이벤트가 후보
구간을 읽을 가능성은 잔여 위험으로 남으므로, canary 진단 빌드를 QA 기간 내내
유지해 위반을 즉시 검출한다.

### Z8.9c — wire v2 확정과 오프라인 배치

- [ ] region table 형식과 index target 재정의를 `field_dialogue_format.json` v2로 기록
- [ ] Z8.9b region 실측값으로 235 레코드 + 520 glyph 전량 배치 시뮬레이션
- [ ] 8 KiB bank 경계 교차 0건, region 초과 0건, source key 왕복 검증
- [ ] 독립 검증기 + 결정성 재생성

PASS: 전량 배치 성공 보고서와 결정적 산출물. 디스크는 여전히 무수정.

### Z8.9d — reader redirect 훅 설계·정적 검증

- [ ] `$4036/$4284` 경계에서 source key 계산 → region lookup → 번역 stream 전환
      훅의 코드 배치·크기·분기 도달성 확정 (코드 공간 감사 포함)
- [ ] MPR/X/Y/`$2D80` 계약과 NUL continuation의 정적 검증
- [ ] huc6280_disasm_verifier로 전체 명령 검산

### Z8.9e — 첫 디스크 빌드와 런타임 게이트

- [ ] A-1 범위(+ 필요시 A-2)만 변경한 빌드, Expected Write 대 전체 BIN diff 일치
- [ ] 회귀 순서: 첫 대사(한글) → Memo 진입·복귀 → 첫 전투 공격 → 필드 복귀 →
      탑 진입 → 초상화 대사
- [ ] 화면 손상, `EXEC BRK`, 검은 화면, 오디오 이상 0건
- [ ] 장면 재진입 20회 반복 오염 검사 (Task5에서 미완이었던 항목 승계)

## 6. 리스크 요약

| 리스크 | 대응 |
|---|---|
| cold 구간이 미주행 이벤트에서 사용됨 | 확장 QA 경로 + canary 진단 빌드 상시 유지, fail-closed |
| cold 합계가 요구량 미달 | text 압축 → A-2 순차 승인, 어느 쪽도 게이트 전 디스크 빌드 금지 |
| A-2 훅 코드 공간 부재 | Z3 relink로 engine `extension_code` section 생성 (모듈 재링크 본연의 경로) |
| 테이블 비경유 CD_READ가 후보 섹터 사용 | Z8.9a에서 정적+런타임 이중 감사 |
| battle/tower로의 일반화 오류 | 이 설계는 entry 2(field 시작 장면) 한정. 다른 장면·family는 각자 Z8.9b부터 반복 |

## 7. 다음 실행 항목

1. Z8.9a 감사 스크립트: `tools/build_ziria_z8_9_disc_reference_audit.py` (+verify)
2. Z8.9b probe: `tools/ziria_z8_9_scene_ram_coverage.lua` (+오프라인 재생 검증기)
3. 두 결과를 `translation/ziria_z8_9_allocation_registry.json` 초안으로 병합

이 문서는 설계 초안이며 CUE/BIN/ISO, 로더, 원본 텍스트를 변경하지 않았다.
