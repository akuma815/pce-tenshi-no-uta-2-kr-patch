# 천사의 시 II ~타천사의 선택~ 한글화 프로젝트

PC Engine Super CD-ROM² / Hudson Soft·NEC, 1993

## 🡒 시작점: [`docs/HANDOFF.md`](docs/HANDOFF.md)

**작업 재개 시 인수인계 문서부터 읽는다.** 현재 단계, 다음 할 일, 확정된 기술 사실,
실패 이력, BizHawk 실행 절차가 전부 거기 있다. 작업 후에도 그 문서를 갱신한다.

상세 근거는 `docs/active/`의 각 Z 문서가 소유한다.
전략 원본은 [`docs/active/Task_Ziria_Module_Relink.md`](docs/active/Task_Ziria_Module_Relink.md).

## 현재 단계

**Z8.9d — A-2 canary 런타임 게이트 대기.**
글리프 풀을 LBA 5480..5494로 배치한 canary 빌드(`*_ziria_z8_9d_a2_canary.bin`)를
BizHawk(`BizHawk-master/output/EmuHawk.exe`)로 실행해 회귀 경로 전체가 원본과
동일한지 확인해야 한다. 특히 오디오 이상 여부. 절차는 HANDOFF §5.

## 디렉터리 구조

| 경로 | 내용 |
| --- | --- |
| `Tenshi_no_Uta_II-*_JAP.bin/.cue` | **원본 디스크 이미지. 절대 수정 금지.** |
| `Tenshi_no_Uta_II-*_a2_canary.bin/.cue` | Z8.9d A-2 canary 진단 빌드 (런타임 게이트 대기) |
| `docs/active/` | Ziria 모듈 재링크 전략 — 현재 유일한 구현 기준 (Z1~Z8) |
| `docs/reference/` | 디스크 구조 분석, 참조 한글패치 역분석, 실패 이력 |
| `docs/retired/` | **폐기된 Task0~7 분기.** 실패 원인 보존용, 구현 기준 아님 |
| `tools/` | 활성 도구 — Ziria 분기 + 공용(추출·폰트·패치·검증) |
| `archive/tools_task0_7/` | 폐기된 Task0~7 분기 스크립트 96개 |
| `translation/` | 번역 자산, 분석 JSON/TSV, 빌드 매니페스트, CDL 캡처 |
| `Translate_Original/` | 번역 원본 XLSX/CSV (대사·UI·크레딧) |
| `module_relink/` | 모듈 identity 추출물, linker layout, 섹션 spec |
| `probes/` | 진단용 수정 System Card 이미지 (`SystemCard3_*.pce`) |
| `font/` | Galmuri8x8 / Galmuri11-Condensed |
| `bios/` | 원본 Super CD-ROM² System Card Ver. 3.00 (J) |
| `Sample/` | 다른 PCE-CD 게임의 성공한 한글패치 (원본/패치본) — **재생성 불가 참조자료** |
| `extracted_bin/` | `tools/extract_bin.py` 산출물. `Track02_data.iso`만 도구가 참조 |
| `BizHawk-master/` | 런타임 검증용 에뮬레이터 |
| `outputs/` | 워크북 렌더 산출물 |

## 재생성 가능한 산출물

디스크 공간이 필요하면 아래는 삭제해도 된다.

| 대상 | 재생성 방법 |
| --- | --- |
| `module_relink/output/` | `python tools/build_ziria_z2_identity.py` (원본과 바이트 동일한 identity rebuild) |
| `extracted_bin/*.wav` | `python tools/extract_bin.py` — 어떤 도구도 참조하지 않음 |
| `extracted_bin/Track02_data.iso` | 같은 스크립트. 원본 BIN 오프셋 7,914,480부터의 슬라이스와 SHA-256 일치 |

## 경로 규약

- `tools/*.py`는 `ROOT = Path(__file__).resolve().parents[1]`로 프로젝트 루트를 잡는다.
- `archive/tools_task0_7/*.py`는 한 단계 깊으므로 `parents[2]`를 쓴다.
- 문서 안의 경로 표기는 모두 **프로젝트 루트 기준**이다 (`docs/` 기준이 아님).
