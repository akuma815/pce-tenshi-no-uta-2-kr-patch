# Task 0 결과 — 기준선 동결

## 판정

Task 0은 **PASS**다. 기준선 SSOT는 `translation/task0_baseline_manifest.json`,
fail-closed 사전검사는 `tools/verify_task0_baseline.py`다.

원본 BIN/CUE/ISO, firmware, 성공·실패 진단 이미지의 내용은 변경하지 않았다. 현재 파일을
직접 SHA-256으로 다시 읽어 잠금값을 만들었다.

## 불변 원본

| 대상 | 크기 | SHA-256 |
|---|---:|---|
| 원본 BIN | 523,184,384 | `D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5` |
| 원본 CUE | 1,430 | `C491342EA8CBF2B6E829316AAAD0AF3F790EC58288DE9BF880927CDCC7C9CC6B` |
| Track02 cooked ISO | 19,103,744 | `7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9` |
| System Card 3.0(J) | 262,144 | `E11527B3B96CE112A037138988CA72FD117A6B0779C2480D9E03EAEBECE3D9CE` |

System Card SHA-1은 `79F5FF55DD10187C7FD7B8DAAB0B3FFBD1F56A2C`다. cooked
Track02 ISO와 CUE 기반 raw BIN 좌표를 구분하며, raw BIN의 데이터 트랙 시작은
7,914,480바이트, runtime absolute LBA bias는 128이다.

## 채택된 성공 기준

`exact_substitution_probe`만 제한된 성공 기준으로 채택한다.

- BIOS: `SystemCard3_one_glyph_probe.pce`
- BIOS SHA-256: `212F3C96A4010BF06A13CEFFD8DEC92C00639188287F18376006CBA67EBB8198`
- 게임: `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_exact_substitution_probe.cue`
- BIN SHA-256: `73A7513F633118BEBAB1A741BC06E8C47C5D75BB134B79F7CC7BA1EA469E8D17`
- 검증 범위: 필드 renderer의 원문 `6F 2D`를 같은 길이의 `8F 6F`로 바꾸고
  mode-1 index 1722의 단일 한글 글리프 표시
- padding: 0바이트
- 미승인 범위: 추가 BIOS slot, 다중 글리프, 전체 번역, 다른 renderer

같은 파일명이 다른 내용으로 덮이면 사전검사가 실패한다.

## 실패 및 사용 금지

| 진단 | 결과 | 정책 |
|---|---|---|
| 896글리프 System Card | 시작 화면부터 전역 타일 손상 | `DO_NOT_USE` |
| 현재 번역 18글리프 | 시작 화면부터 동일 손상 | `DO_NOT_USE` |
| 2글리프 | 시작 화면부터 동일 손상 | `DO_NOT_USE` |
| 단일 글리프 + ASCII `0x20` padding | 페이지 대사가 잔류·결합 | padding `PROHIBITED` |

실패 파일도 증거이므로 삭제하거나 성공 이미지로 덮지 않는다. 정확한 파일별 해시는 기준선
매니페스트에 들어 있다.

## BizHawk 실행 기준

| 항목 | 고정값 |
|---|---|
| EmuHawk | 2.11.2, commit `4d63f303...` |
| EmuHawk SHA-256 | `E3AD72418FD125BB6D47A3FE21D8FB7E20802F7392A17B266ED71FE98FA27FFF` |
| PCE core | `PCEHawk` |
| Cores DLL SHA-256 | `36D755B904E747E7705778787B7A2BD06502E72589C7F2F6E5CE203233EAF53B` |
| config | `translation/one_glyph_bizhawk_config.ini` |
| firmware override | 통과한 단일 글리프 BIOS |
| AutoLoadLastSaveSlot / AutosaveSaveRAM | false / false |
| SaveRAM | 프로젝트 루트와 `H:/BizHawk/SaveRAM`에 Tenshi/Datenshi 파일이 없는 clean start |

## 재현 절차

1. 기존 EmuHawk 프로세스를 종료한다.
2. 프로젝트 루트에서 `python tools/verify_task0_baseline.py`를 실행한다.
3. `TASK0 BASELINE: PASS`가 아니면 작업과 실행을 중단한다.
4. 잠긴 `translation/one_glyph_bizhawk_config.ini`를 사용한다.
5. BIN/ISO가 아니라 잠긴 `exact_substitution_probe.cue`를 cold boot한다.
6. System Card 화면, 타이틀, 첫 대사, 다음 페이지 전환을 확인한다.
7. 기대 결과는 첫 본문 `가、シオン`, 다음 페이지 정상 clear, 전역 그래픽 손상 없음이다.

## 후속 Task 사전검사

모든 후속 Task는 조사·빌드·패치 전에 다음 명령이 0으로 종료돼야 한다.

```powershell
python tools/verify_task0_baseline.py
```

불일치 시 자동 보정하거나 현재 해시로 기준선을 갱신하지 않는다. 리비전 변경이나 의도적
산출물 교체는 새 파일명과 새 기준선 version으로 별도 승인해야 한다.
