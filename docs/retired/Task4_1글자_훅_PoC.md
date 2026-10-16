# Task 4 — 원본 BIOS 기반 1글자 훅 PoC

## 현재 상태

**정적 빌드 PASS / 런타임 FAIL**

위 상태는 잘못 선정된 v1 호출부에 대한 판정이다. Task 4 도달성 진단으로 LBA 좌표 오류를
확정한 뒤 실제 필드 호출부를 사용한 **v2 정적·런타임 검증은 PASS** 상태다.

Task 3에서 설계한 `renderer.field_main` 전용 GETFNT 훅을 실제 디스크 이미지에 적용했다.
BIOS는 수정하지 않으며, H:\BizHawk의 원본 `PCECD_3.0-(J).pce`를 명시적으로 선택한다.

## 적용 내용

| 구분 | Track02 ISO 오프셋 | 변경 |
|---|---:|---|
| 필드 GETFNT 호출 | `0x45855` | `JSR $E060` → `JSR $BB20` |
| 로컬 훅과 글리프 | `0x48B20` | 원본 `FF` 패딩 77바이트에 훅 45바이트와 `가` 글리프 32바이트 설치 |
| 첫 대사 | `0x10B9F2` | 원문 `6F2D` → 커스텀 코드 `EF41` |

### v2 정정 적용

| 구분 | Track02 ISO 오프셋 | 변경 |
|---|---:|---|
| 실제 필드 GETFNT 호출 | `0x8667E` | `JSR $E060` → `JSR $C737` |
| 실제 모듈 로컬 훅·글리프 | `0x89737` | `RTS` 뒤 457바이트 `FF` 창의 첫 77바이트 사용 |
| 첫 대사 | `0x10B9F2` | 원문 `6F2D` → 커스텀 코드 `EF41` |

v1의 `0x45855`는 `cd_read_trace` LBA에 128섹터 bias를 중복 적용해 선택한 잘못된
호출부였다. 무조건 `가` 반환 훅을 넣어도 일본어가 그대로였으므로 폐기했다.

- 새 글리프는 `font/Galmuri8x8.ttf`에서 생성했다.
- 글리프 풀에는 `가` 한 글자만 있다.
- 첫 대사의 나머지 본문, 화자명, 페이지 제어, 종료자는 원본 그대로다.
- 커스텀 코드가 아니면 훅은 원본 BIOS `EX_GETFNT`로 tail-jump한다.
- 훅은 MPR을 바꾸지 않고 공유 Work RAM이나 스택 scratch를 사용하지 않는다.

## 산출물

- 실행 CUE: `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_task4_field_hook_poc.cue`
- 실행 BIN: `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_task4_field_hook_poc.bin`
- BizHawk 설정: `translation/task4_field_hook_poc_bizhawk_config.ini`
- 빌드 기록: `translation/task4_field_hook_poc_manifest.json`
- 빌더: `tools/build_task4_field_hook_poc.py`
- 검증기: `tools/verify_task4_field_hook_poc.py`

출력 BIN SHA-256:

`09539211F77291760E84151703647969BA180AFF4A94CE75C69CB7F140776957`

v2 실행 CUE와 SHA-256:

- `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_task4_field_hook_poc_v2.cue`
- `4DA30EA2002BC1CAA7E1207FFFA0C2A2B45893D600433494E2A2DF2EA664189B`
- 매니페스트: `translation/task4_field_hook_poc_v2_manifest.json`
- 빌더/검증기: `tools/build_task4_field_hook_poc_v2.py`, `tools/verify_task4_field_hook_poc_v2.py`

## 정적 검증 결과

- 출력 BIN 크기: 원본과 동일한 523,184,384바이트
- 선언된 Expected Write: 3개
- 실제 변경 바이트: 80바이트
- 선언 범위 밖 변경: 0바이트
- 원본 BIN/CUE 및 원본 BIOS: 변경 없음
- 원본 BIOS SHA-256: `E11527B3B96CE112A037138988CA72FD117A6B0779C2480D9E03EAEBECE3D9CE`
- Galmuri8x8 SHA-256: `97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05`

## 런타임 확인 절차

Lua 없이 EmuHawk를 새로 실행하고 다음을 순서대로 확인한다.

1. System Card 시작 화면과 타이틀이 정상인지 확인한다.
2. 첫 필드 화면의 배경·스프라이트·대사창이 정상인지 확인한다.
3. 첫 대사에서 치환된 첫 글자만 `가`로 보이는지 확인한다.
4. 뒤에 나오는 원본 `出`이 일본어 `出`로 유지되는지 확인한다.
5. 다음 대사 페이지가 정상적으로 지워지고 진행되는지 확인한다.

2026-07-17 v1 첫 세 페이지 확인 결과, 부팅·그래픽·원본 `出`·페이지 진행은 정상이었지만
잘못된 호출부 때문에 `EF41` 위치가 `가`로 출력되지 않았다. 이 v1 FAIL은
`translation/task4_field_hook_poc_runtime.json`에 보존했다.

## v2 런타임 결과

2026-07-17 정정된 v2를 Lua 없이 새로 실행해 다음을 확인했다.

- `EF41`로 치환한 첫 위치만 Galmuri8x8 `가`로 출력됐다.
- 다음 페이지의 원본 문장 `支度は出来たのかフェイト`에 포함된 `出`은 일본어 `出`로 남았다.
- 필드 배경, 스프라이트, 대사창이 정상이며 첫 페이지가 지워진 뒤 다음 페이지로 진행됐다.
- 실행 BIN SHA-256은 `4DA30EA2002BC1CAA7E1207FFFA0C2A2B45893D600433494E2A2DF2EA664189B`다.

따라서 Task 4 v2는 **PASS**다. 판정과 스크린샷 경로는
`translation/task4_field_hook_poc_v2_runtime.json`에 잠갔다. 승인 범위는 필드 첫 대사 경로의
단일 커스텀 글리프 공급까지이며, 다글자·다른 renderer·문자열 재배치는 아직 승인하지 않는다.
