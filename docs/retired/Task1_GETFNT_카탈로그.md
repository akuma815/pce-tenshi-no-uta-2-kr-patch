# Task 1 결과 — 렌더 경로와 EX_GETFNT ABI 카탈로그

## 1. 판정

- 상태: **PASS (필드 renderer 구현 게이트)**
- 원본 ISO의 `JSR $E060` raw pattern: 22건
- 실행 코드로 정적 확정한 호출: 18건
- 동일 주변 코드 사본: 13건 (`renderer.standard_overlay`)
- 코드로 확정하지 못한 raw match: 4건 — 훅 대상에서 제외하고 `unknown` 유지
- 첫 구현 대상: `renderer.field_main`
- 게임 ISO, BIN, BIOS 및 BizHawk 소스는 수정하지 않았다.

기준선:

| 대상 | 해시 |
|---|---|
| `extracted_bin/Track02_data.iso` | SHA-256 `7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9` |
| System Card 3.0(J) | SHA-1 `79F5FF55DD10187C7FD7B8DAAB0B3FFBD1F56A2C` |
| System Card 3.0(J) | SHA-256 `E11527B3B96CE112A037138988CA72FD117A6B0779C2480D9E03EAEBECE3D9CE` |

기계 판독용 상세 원장은 `translation/getfnt_renderer_catalog.json`이다.

## 2. renderer 분류

| renderer_id | 소비 화면 | 호출 위치 | mode | 상태 |
|---|---|---|---|---|
| `renderer.boot_opening` | 부트/오프닝 | ISO `0x003891`, PC `$6891` | `$2A82`에서 동적 | 실행 코드 확정 |
| `renderer.standard_overlay` | 부트 사본 및 이벤트 신 사본 | 13개 위치, 공통 PC `$6886` 추정 | `$2A82`에서 동적 | 99바이트 코드가 모두 동일 |
| `renderer.disproved_lba130_candidate` | 첫 필드 대사가 아님 | ISO `0x045855`, PC `$8855` 추정 | 1 고정 | Task 4 무조건 훅 도달성 FAIL로 폐기 |
| `renderer.field_main` | 필드/마을 일반 대사 | ISO `0x08667E`, PC `$967E` | 1 고정 | **정정된 첫 구현 대상** |
| `renderer.card_primary` | 카드 미니게임 | ISO `0xBD1CA6` | 1 고정 | 실행 코드 확정, 런타임 매핑 unknown |
| `renderer.card_secondary` | 카드 미니게임의 두 번째 글리프 경로 | ISO `0xBD8A97` | 1 고정 | 실행 코드 확정, 런타임 매핑 unknown |

`renderer.standard_overlay`의 ISO 호출 위치는 다음과 같다.

```text
0x032886
0xC06886  0xC76886
0xD6E886  0xDCE886  0xE2E886  0xE8E886  0xEEE886
0xF5E886  0xFBE886  0x101E886 0x107E886 0x10DE886
```

모두 호출 전후 48바이트, 즉 99바이트 context SHA-1 prefix가
`B9BF5653CEC0038A`로 동일하다. 따라서 서로 다른 구현 13개가 아니라 같은 renderer
바이너리가 여러 디스크 위치에 복제된 경우다. 다만 각 디스크 사본의 적재 시점과 수명은
독립적이므로 패치 시 한 사본의 성공을 다른 사본에 일반화하면 안 된다.

다음 네 raw match는 주변 바이트만으로 실행 가능한 함수 경계를 확정하지 못했다.

```text
0xCA59C6  0xDA615A  0xED3080  0x10A1CAA
```

이들은 `renderer.unknown_raw_match_01..04`로 보존한다. 런타임 PC 적중 또는 코드
cross-reference가 생기기 전에는 GETFNT 훅 대상으로 취급하지 않는다.

## 3. EX_GETFNT ABI

### 3.1 공통 입력

| 상태 | 의미 |
|---|---|
| `$F8/$F9` | SJIS trail/lead 바이트. 필드 엔진도 이 순서로 전달한다. |
| `$FA/$FB` | 32바이트 출력 버퍼 시작 주소 |
| `$FF bit 0` | 0=32바이트 원본 글리프, 1=18바이트 packed 12×12 글리프 |
| A/X/Y/P | 입력값을 요구하지 않는 scratch |

`$E060`은 System Card bank 0의 `JMP $F124`이며, `$F124`가 SJIS 검증·compact
index 계산·font bank 매핑을 소유한다. mode 1의 압축 해제는 **System Card `$F2CC`**가
소유한다. 게임 renderer는 18→32 변환을 하지 않는다.

### 3.2 성공 시 출력 및 clobber

| 상태 | mode 0 | mode 1 |
|---|---|---|
| 출력 버퍼 | 원본 32바이트 복사 | 18바이트를 24 bitmap 바이트로 확장하고 뒤 8바이트를 0으로 채움 |
| A | `$00` | `$00` |
| X | `$00` | `$00` |
| Y | `$20` | `$FF` |
| `$FA/$FB` | 시작 주소 유지 | 시작 주소 + **24** |
| `$F8/$F9` | 원본 SJIS가 아니라 내부 index/address 계산값으로 clobber | 동일 |
| `$FF` | 유지 | 유지 |
| P | clobber | clobber |
| S | JSR/RTS 전후 동일 | JSR/RTS 전후 동일 |
| MPR | 임시 font bank 매핑 후 원래 값 복구 | 동일 |

실패 경로는 A=`$01`로 반환하며 출력 버퍼는 유효하다고 간주할 수 없다. `$EC/$ED/$EE`,
`$FC`, `$22B8..$22BB`, `$22BD`는 BIOS 내부 scratch다. 기존 `구조분석.md` §12.3의
“글리프 주소를 `$F8/$F9`로 반환하고 `$FA/$FB`를 32 증가” 설명은 실제 System Card
3.0(J) 코드와 맞지 않으며 이 문서의 판정으로 대체한다.

### 3.3 훅의 보존 계약

필드용 module-local GETFNT 훅은 다음을 지켜야 한다.

1. `$F8/$F9`, `$FA/$FB`, `$FF`를 입력 ABI로 받는다.
2. 커스텀 글리프 성공 시 정확히 32바이트를 원래 `$FA/$FB`가 가리킨 버퍼에 쓴다.
3. `$FF`, S, 호출 당시 MPR2~MPR7을 보존한다.
4. mode 1 호환 경로에서는 A=`$00`, X=`$00`, Y=`$FF`, `$FA/$FB`=시작+24를 재현한다.
5. P와 `$F8/$F9`는 native ABI상 clobber지만, 훅 내부 분기에서 원본 일본어 fallback으로
   넘어갈 때는 입력 SJIS와 destination을 손상시키기 전에 복구한다.
6. 게임 zero-page 중 BIOS ABI/scratch로 명시되지 않은 주소는 변경하지 않는다.
7. MPR을 바꾸면 TMA로 실제 live 값을 저장하고 모든 반환 경로에서 TAM으로 복구한다.

## 4. 필드 renderer 수명과 live state

| 단계 | 확정값 |
|---|---|
| 디스크 저장 | Track02 상대 LBA 258, ISO `0x81000`, 20섹터=`0xA000` 바이트 |
| CD trace 좌표 | LBA 258은 이미 Track02 상대값이며 frame 1237에서 관측 |
| 적재 호출 | `CD_READ`, count 20, destination bank `00`, mode `01` |
| 실제 물리 RAM | `$80..$84` |
| 소비 시 매핑 | MPR2..MPR6=`80,81,82,83,84` |
| CPU 주소 | ISO `0x8667E - 0x81000 + $4000 = $967E` |
| destination glyph buffer | `$2EA7..$2EC6` 또는 `$2EC7..$2EE6` (호출 래퍼의 분기별 버퍼) |
| mode | `LDA #$01 / STA $FF / JSR $E060` |
| 하류 소비 | `$973D` 이후 필드 글리프→VDC 전송 경로 |
| 검증된 생존 구간 | 적재 후 첫 인게임 대사와 PC `$53AF` 관측 시점까지 |
| 종료 조건 | `$80..$84`가 다음 CD_READ에 덮이거나 MPR2..6이 다른 모듈로 재매핑될 때 |

필드 글리프 취득 래퍼는 `$966A` 부근에 있으며 SJIS `$8754/$8755`만 내장 글리프로
우회한다. 나머지는 mode 1로 `$967E`에서 BIOS를 호출한다. 이전 `$8855` 판정은
`cd_read_trace`의 LBA 258에 128섹터를 다시 빼서 생긴 오프셋 오류였다. ISO `0x45855`를
무조건 `가` 훅으로 바꿔도 첫 세 페이지가 일본어 그대로였던 결과로 해당 경로를 폐기했다.

따라서 `renderer.field_main`은 ABI, 저장 범위, 적재 크기, 물리 bank, 소비 MPR, 출력
버퍼 및 하류 VRAM 경로가 모두 닫힌 유일한 첫 구현 대상이다.

## 5. 모듈 수명표

| renderer_id | storage/load | RAM/MPR | 소비 수명 | 미확인 |
|---|---|---|---|---|
| `boot_opening` | LBA 2, 16섹터, load `$4000` | IPL 상대 bank `00..03`→물리 `$80..$83` | 부트 진입부터 다음 시스템 로드 전 | 호출 순간 MPR runtime dump |
| `standard_overlay` | 각 호출은 module start+`0x2886`; start LBA는 JSON 참조 | unknown | 각 overlay 적재 후 교체 전 | load count, destination bank, 실제 MPR |
| `field_main` | LBA 130, 20섹터 | `$80..$84`, MPR2..6 | 첫 필드 엔진 적재부터 덮어쓰기/재매핑 전 | 없음(첫 구현에 필요한 범위) |
| `menu_battle_common` | LBA 260 시작 정적 식별 | unknown | 해당 제2 엔진 적재 중 | load count, bank, 메뉴/전투/이름/아이템별 실행 coverage |
| `card_primary` | ISO 위치만 확정 | unknown | unknown | loader, PC, MPR |
| `card_secondary` | ISO 위치만 확정 | unknown | unknown | loader, PC, MPR |

## 6. 다음 단계 게이트

Task 2로 넘어갈 수 있는 범위는 `renderer.field_main`뿐이다. 다른 renderer에는 아직 훅을
삽입하지 않는다. 메뉴·전투·이름·아이템, 카드, 후반 event overlay는 실제 화면에서
GETFNT 진입 PC, MPR2..7, `$F8..$FF`, A/X/Y/P와 직전 CD_READ를 수집한 뒤 각자 별도의
수명 계약을 닫아야 한다.
