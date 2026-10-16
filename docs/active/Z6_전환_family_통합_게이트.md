# Z6 전환 family 통합 게이트

## 결론

field, menu/Memo, battle, tower/dungeon, portrait/event는 별도 renderer가 아니다.
연속 경로에서 관찰된 1,602회의 GETFNT가 모두 상주 `field.main_engine`의
`$967E`(MPR4=`$82`)를 통과했다. Z6의 family 분리는 renderer 코드가 아니라
mode-06 장면 패키지의 텍스트 스트림 소유권으로 정의한다.

## 실제 스트림 경계

| family | CD 패키지 | 실제 Track02 소스 | 원본 | Z6 |
|---|---:|---:|---:|---:|
| field Memo 화자명 | LBA 482 | `0x011FA17` | `BC B5` (`シオ`) | `87 54` (`가`) |
| tower dialogue 화자명 | LBA 2882 | `0x05BA0EC` | `CC AA` (`フェ`) | `87 54` (`가`) |
| portrait/event 화자명 | LBA 2882 | `0x05BA1AF` | `BC B5` (`シオ`) | `87 54` (`가`) |
| tower Memo copy 화자명 | LBA 2882 | `0x05BDA17` | `BC B5` (`シオ`) | `87 54` (`가`) |

네 표본은 모두 **대사 본문 첫 글자가 아니라 캐릭터 화자명의 첫 두 글자**다.
주소는 `$4293/$42DE/$42AB/$42BA`의 실제 byte read, 현재 MPR, 마지막 mode-06
CD_READ LBA를 결합해 계산했다. 각 변경은 두 개의 1바이트 압축 토큰을 같은 길이의
2바이트 raw 코드로 치환하므로 이후 스트림 주소와 제어코드는 이동하지 않는다.

## 글리프와 renderer

- Z4 field 슬롯 `$8754/$9172`의 Galmuri8x8 `가`를 공통 core glyph로 재사용한다.
- Z5 battle 슬롯 `$8755/$9192`와 공격 메시지는 그대로 보존한다.
- 새 dispatcher, hook, 글리프 레코드, Work RAM 코드는 추가하지 않는다.

## 정적 검증

- Z5 대비 증분: 8바이트, 4개 연속 구간
- Z4+Z5+Z6 전체 Track02 변경: 42바이트
- Track02와 전체 BIN 크기: 원본과 동일
- 변경 0: 실행 코드, glyph record, battle module, BIOS, MPR, Work RAM, loader table,
  audio, CUE track layout
- Z6 BIN SHA-256:
  `D598B992BA0118641639BD811772CF17BF309C1B4D090C50E21E295DE28DF18E`

## 런타임 게이트

1. 첫 대사 `가`와 캐릭터 그래픽
2. 필드 Memo 화자명의 `가`, 진입과 복귀
3. 첫 전투 공격 `가`, 공격 처리와 필드 복귀
4. 전투 후 탑 진입
5. 탑 일반 대사 화자명의 `가`
6. 초상화 이벤트 화자명의 `가`와 초상화 그래픽
7. 탑 Memo 화자명의 `가`, 진입과 복귀

검은 화면, 화면 손상, 잘못된 필드 전환, `EXEC BRK`가 없어야 PASS다.

판정(2026-07-19): **Z6 RUNTIME PASS**. 위 화자명 표본은 모두 정상 출력됐고
전환 경로도 정상이다. 첫 필드 대사 본문의 `가`는 기존 Z4 표본과 이번 실행에서
PASS가 재확인됐다. 반면 Memo 본문 첫 글자와 탑 진입 직후 대사 본문 첫 글자는
화면에서 확인하지 않았으므로 `NOT_CHECKED`다. 두 본문 표본은 Z7/Z8의
글리프·텍스트 패키지 게이트에서 별도로 검증한다.
