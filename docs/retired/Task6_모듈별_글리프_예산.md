# Task 6 — 모듈별 글리프 예산

## 판정

**용량 게이트 PASS / 릴리스 빌드 입력 차단 17건**이다.

최신 `translation/full_extraction/master_text.csv` 18,817행을 기준으로 모든 physical grid,
primary/overlay loader context, 메뉴·전투 renderer 수요를 다시 계산했다. 빈 번역과 제어코드
순서 불일치는 0건이다. 다만 `status=needs_review` 17행은 번역문이 채워져 있어 예산에는
포함했지만, 승인 전에는 릴리스 빌드 입력으로 사용할 수 없다.

기준 `master_text.csv` SHA-256:

`36AAE2700FB2639A29BBCC3770EFC203BF494997A722DD0C85B8F6026E560AC0`

## 핵심 결과

| 항목 | 결과 |
|---|---:|
| 전체 행 | 18,817 |
| 고유 한글 | 1,053 |
| 한글 출현 수 | 370,018 |
| 전역 940-code 대비 부족 | 113 |
| 단일 loader 최대 활성 한글 | 609 |
| 32바이트 전역 상주 크기 | 38,100바이트 / 5뱅크 |
| 18바이트 전역 상주 크기 | 23,358바이트 / 3뱅크 |
| physical grid | 55 |
| loader context | 85 |
| 메뉴·전투 renderer 수요 단위 | 55 |

전역 고정 매핑은 113자가 부족하지만, loader별 최대 활성 집합 609자는 940-code 한도 안에
들어간다. 따라서 Task 5에서 검증한 **모듈 수명 지역 매핑**을 유지한다. 전체 1,053자를
영구 RAM에 두는 설계는 3~5개 8KiB 뱅크의 수명과 소유권을 새로 증명해야 하므로 채택하지
않는다.

## 32바이트 expanded 경로

Task 5에서 실제 표시와 메모 진입이 확인된 경로다.

| 분류 | loader 수 | 의미 |
|---|---:|---|
| 직접 FIT | 28 | 96-sector window의 남는 whole bank에 package 수용 |
| source-hole 분기 | 14 | 원문 redirect 뒤 source span 회수·재료화가 필요 |
| scene-load sidecar 분기 | 43 | whole bank와 현재 source-hole 합계로도 부족 |

각 package는 64바이트 runtime manifest, 128바이트 hook reserve, 정확 중복 제거 문자열,
글리프당 4바이트 map, 글리프당 32바이트 expanded data 및 32바이트 정렬을 포함한다.
문자열은 NUL 1바이트를 포함하고 8KiB 뱅크 경계를 넘지 않게 계산했다.

`source-hole`은 이전 redirect 조사에서 얻은 구조적 회수 후보치다. 최신 번역을 실제로
배치한 결과가 아니므로 직접 FIT로 승격하지 않고 `TASK8_SOURCE_HOLE_RECLAIM_AND_MATERIALIZE`
분기로 남겼다. 43개 sidecar 분기도 문자 출력 중 CD 읽기를 허용한다는 뜻이 아니다.
Task 7에서 장면 로드 시 읽기와 마지막 소비까지의 RAM 수명을 별도로 증명해야 한다.

## 18바이트 packed 경로

| 분류 | loader 수 | 의미 |
|---|---:|---|
| 직접 FIT 추정 | 39 | 용량상 수용되지만 18→32 확장기 PoC 필요 |
| source-hole 분기 | 4 | packed data와 source-hole 재료화를 함께 요구 |
| sidecar/module split 분기 | 42 | packed 상태에서도 현재 용량 초과 |

18바이트 수치는 mode-1 packed glyph의 저장량만 반영한 **추정치**다. Task 5는 32바이트
expanded 복사 경로만 검증했으므로, 18바이트 FIT를 구현 PASS로 해석하지 않는다.

## 메뉴·전투·시스템 수요

런타임 모듈 경계가 아직 확정되지 않은 전체 semantic 집계는 다음과 같다.

| 범주 | 행 | 고유 문자열 | 문자열 바이트 | 고유 한글 | 32바이트 package |
|---|---:|---:|---:|---:|---:|
| `menu_data` | 3,789 | 305 | 2,918 | 325 | 14,848 |
| `system` | 82 | 78 | 1,008 | 151 | 6,656 |
| `command` | 56 | 32 | 572 | 71 | 3,328 |
| `battle` | 28 | 21 | 270 | 8 | 768 |
| `card` | 52 | 40 | 799 | 130 | 5,696 |

이 값은 전역 합계일 뿐 한 번에 상주하는 module budget이 아니다. 55개 loader별 자식 수요도
별도로 산출했으며, Task 9에서 실제 renderer hook·loader·수명이 확인될 때 부모 loader의
공간을 배정한다.

## core glyph 복제 결정

상위 64/128/256 고빈도 글리프를 각 loader에 복제하는 최악 상한은 32바이트 형식 기준
각각 187,020 / 370,476 / 729,756바이트다. 이는 primary와 overlay context를 모두 별도
소비자로 센 상한이며 최종 디스크 증가량을 뜻하지 않는다. 디스크 중복은 허용하되 다음을
고정한다.

- 같은 physical grid에서 공유 가능한 복제는 Task 7 배치 단계에서 합친다.
- 포인터와 glyph pool 수명은 항상 해당 loader/module에 종속한다.
- core glyph를 이유로 전역 영구 RAM 포인터를 만들지 않는다.

## 번역 자산 감사

- 빈 번역: 0
- 제어코드 토큰 순서 불일치: 0
- `needs_review`: 17
- 원문과 동일한 역문: 507
- 일본어 문자가 남은 행: 4,644

일본어 잔존 수에는 `{%f}` 직후의 얼굴/화자 선택용 1바이트 kana와 승인 원문 자산이 포함돼
있으므로 곧바로 미번역으로 판정하지 않았다. `needs_review` 17행은 XLSX의 `Review Blockers`
시트에 원문·역문·오프셋과 함께 정리했다.

## Task 0 사전검사 상태

원본 BIN, CUE, Track02 ISO, 원본 System Card의 SHA-256은 Task 0 잠금값과 모두 일치했다.
다만 기존 `tools/verify_task0_baseline.py`는 보관 증거인
`Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_exact_substitution_probe.cue`가 현재 루트에 없어
완주하지 못했다. 따라서 이번 용량 분석은 검증된 Track02 기준선에 대해 재현 가능하지만,
릴리스 빌드 전에 해당 증거 복원 또는 Task 0 매니페스트의 보관 정책 개정이 필요하다.

## 산출물과 재현

- 기계 판독 원장: `translation/task6_module_glyph_budget.json`
- 계산기: `tools/analyze_task6_module_budgets.py`
- 검증기: `tools/verify_task6_module_budgets.py`
- 검토 워크북: `outputs/019f55dd-966e-7f81-aed7-0f92ef88e1c9/Task6_module_glyph_budget.xlsx`

```powershell
python -X utf8 tools/analyze_task6_module_budgets.py
python -X utf8 tools/verify_task6_module_budgets.py
```

두 번째 명령은 보호 입력 해시, Galmuri8x8 해시, 글리프·map·package 산식, 모든 module의
`FIT` 또는 명시적 overflow branch를 검증한다.
