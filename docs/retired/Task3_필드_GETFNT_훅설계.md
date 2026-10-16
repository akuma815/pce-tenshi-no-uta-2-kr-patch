# Task 3 — 필드 모듈 로컬 GETFNT 훅 설계

결론: **설계 게이트 PASS**. 원본 게임 이미지와 BIOS는 수정하지 않았으며 Task 4의 1글자 PoC 빌드를 만들 수 있는 Expected Write 두 건을 확정했다.

적용 범위는 `renderer.field_main`의 첫 대사 경로뿐이다. Task 2에서 승인된 커스텀 코드 `EF41` 하나만 처리한다.

## 선택한 구조

필드 호출부 `$967E`의 원본 `JSR $E060`을 `JSR $C737`으로 바꾼다.

```text
$967E  JSR $C737
          |
          +-- F9:F8 == EF:41 --> 로컬 32바이트 글리프 복사 --> RTS
          |
          +-- 그 외 ----------> JMP $E060 ----------------> BIOS RTS
```

`$C737`은 필드 모듈의 물리 뱅크 `0x84`, MPR6 창에 있다. 첫 대사 및 다음 페이지에서 관찰된 MPR2..6은 `80 81 82 83 84`이므로 별도의 뱅크 전환 없이 실행 코드와 글리프를 함께 읽을 수 있다.

## 호출부와 수명

- 필드 모듈: Track02 LBA 258 / ISO `0x81000`, 20섹터, 40,960바이트
- 물리 뱅크: `0x80..0x84`
- 호출부: ISO `0x8667E`, 런타임 `$967E`
- 원본 바이트: `20 60 E0` (`JSR $E060`)
- 변경 예정 바이트: `20 37 C7` (`JSR $C737`)
- 반환 주소: `$9681`

Task 4 도달성 실패로 이전 LBA130 판정을 폐기했고, frame 1237의 CD_READ LBA258을 Track02 상대값으로 바로 적용해 이 호출을 정정했다. 첫 페이지와 두 번째 페이지까지 MPR6=`84`가 유지된다.

## 코드·데이터 창

- 창: `$C737..$C8FF`, ISO `0x89737..0x898FF`
- 원본: 457바이트 전체 `FF`
- 사용: 77바이트
- 잔여: 380바이트
- 사용 구간과 값이 겹치는 비정렬 raw word: 6건(매니페스트에 전부 기록)
- 사용 구간의 원본 `JSR`/`JMP` 참조: 0
- 뱅크 경계 횡단: 없음

이 창은 ISO `0x89736`의 `RTS` 바로 다음에서 시작하고 `0x89900`의 포인터 테이블 전에 끝난다. 사용 구간을 직접 가리키는 원본 `JSR`/`JMP`는 0건이며 뱅크 경계를 넘지 않는다.

## 훅 동작

### 원본 문자 경로

1. `$F9`가 `EF`인지 비교한다.
2. `$F8`이 `41`인지 비교한다.
3. 하나라도 다르면 `JMP $E060`으로 원본 BIOS에 tail-call한다.

패치된 `JSR $C737`이 반환 주소를 한 번만 쌓고, fallback의 `JMP`는 추가 반환 주소를 만들지 않는다. 따라서 BIOS의 `RTS`가 원래와 동일하게 `$9681`로 돌아간다.

System Card ABI에서 A와 P는 live-in이 아니다. 비교 전에 `$F8/$F9`, `$FA/$FB`, `$FF`, X, Y 및 반환 프레임은 바뀌지 않으므로 BIOS가 받는 유효 입력은 원본과 동일하다. fallback 출력과 BIOS scratch/MPR 부작용도 원본 BIOS가 그대로 소유한다.

### 커스텀 문자 경로

`F9:F8=EF:41`이면 `$BB4D`의 32바이트 expanded 글리프를 원래 `$FA/$FB` 시작점에 복사한다.

- 출력 버퍼: 원래 `$3328..$3347`
- 복사량: 32바이트
- 성공 반환: A=`00`, X=`00`, Y=`FF`
- `$FA/$FB`: mode-1 ABI와 같이 +24
- `$FF`: 보존
- MPR: 변경 없음
- stack page: 훅 임시 저장에 사용하지 않음
- BIOS 변수/공용 Work RAM: 훅 상태 저장에 사용하지 않음

32바이트 데이터는 새 빌드 기준 폰트 `font/Galmuri8x8.ttf`에서 직접 생성한다. 폰트 SHA-256은 `97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05`이다. 이 bitmap 폰트는 PIL에서 16px strike로 열리지만 실제 잉크는 8×8이므로, 12×12 PCE 셀 중앙 `(2,2)`에 배치하고 16×16 출력의 나머지를 0으로 채운다.

```text
expanded 32:
000000003C80048004C004800880308000800080000000000000000000000000
```

각 행은 MSB-first 2바이트이며 12×12 셀 밖은 0이다. 이는 mode-1 성공 경로가 소비자에게 제공하는 32바이트 버퍼 형태와 일치한다.

## MPR 정책

훅에는 `TMA`와 `TAM`이 전혀 없다. 코드와 글리프가 이미 MPR6=`84`에 함께 있으므로 MPR 저장·변경·복구 자체를 제거했다. 따라서 인터럽트 금지, stack 임시 저장 또는 Work RAM 임시 변수가 필요 없다.

이 설계는 MPR6=`84`이라는 필드 모듈 수명 계약에 의존한다. 다른 렌더러나 필드 모듈 교체 이후로 확장할 수 없다.

## Task 4 Expected Write

Task 4 빌더는 다음 두 건 외의 변경을 거부해야 한다.

1. `field-getfnt-call`
   - ISO `0x8667E`
   - 기대값 `2060E0`
   - 변경값 `2020BB`
2. `field-getfnt-hook-and-glyph`
   - ISO `0x89737`
   - 기대값: 77바이트 `FF`
   - 변경값: `translation/task3_field_getfnt_hook.bin`

Task 4에서 별도로 첫 대사 `6F2D -> EF41` 치환이 필요하지만, 그것은 Task 2에서 검증한 진단 텍스트 쓰기이며 Task 3 훅 설계 자체의 Expected Write에는 포함하지 않았다.

## 통과 범위

증명됨:

- 훅·글리프·분기 대상이 모두 검증된 필드 모듈 범위와 동일 뱅크 안에 있다.
- 원본 경로의 stack shape와 BIOS 소유 동작이 유지된다.
- 커스텀 경로가 32바이트 글리프와 필드 소비자에 필요한 성공 ABI를 제공한다.
- MPR, stack page, BIOS scratch, 공용 Work RAM을 임시 저장소로 사용하지 않는다.
- 모든 변경 위치와 원본 기대 바이트가 기계 판독 가능하게 고정됐다.

아직 증명되지 않음:

- 실제 패치된 게임에서 `EF41`이 `가`로 표시되는지
- 다음 페이지 및 원본 일본어 fallback의 런타임 동일성
- 여러 글리프와 장면 로컬 재매핑
- 메뉴·전투·카드 등 비필드 렌더러

위 항목 중 첫 두 개는 Task 4의 런타임 PoC에서 판정한다.

## 산출물과 검증

- 설계 생성기: `tools/design_task3_field_getfnt_hook.py`
- 기계 판독 설계: `translation/task3_field_getfnt_hook_design.json`
- 훅+글리프 바이트: `translation/task3_field_getfnt_hook.bin`
- fail-closed 검증기: `tools/verify_task3_field_getfnt_hook.py`

검증 명령:

```text
python tools/verify_task0_baseline.py
python tools/verify_task2_custom_code.py
python tools/verify_task3_field_getfnt_hook.py
```
