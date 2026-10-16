# 천사의 시 II 한글화 — 모듈 재링크 전략

상태: **ACTIVE**  
전환일: 2026-07-18  
참조 사례: 《천외마경 ZIRIA》 PC Engine CD 영문판 빌드 구조  
기준 폰트: `font/Galmuri8x8.ttf`

## 1. 전략 전환 판정

기존 전략은 다음 공통 구조를 유지한 채 위치와 호출 조건만 바꾸었다.

- 공용 Work RAM `$2B0F`에 실행 훅 설치
- 필드 GETFNT 호출부에서 공용 훅을 지속 참조
- LBA 9178 계열 sidecar를 CD_READ 뒤에 별도 적재
- bank `$6D` 또는 `$84`를 글리프 공급원으로 사용

이 구조는 한글 표시 자체에는 성공했지만 전투 공격, 필드 복귀, 탑 진입, 메모,
초상화 오버레이가 같은 RAM과 로더 상태를 재사용하면서 반복적으로 실패했다.
sidecar 제거, 단발 설치, 훅 축소, MPR6 변경 제거로도 재현됐으므로 단일 주소나
분기 오류가 아니라 **오버레이 수명 밖에 코드와 상태를 존속시킨 설계 오류**로
판정한다.

따라서 기존 Task 0~7의 구현 분기는 폐기한다. 분석 산출물과 런타임 trace는
모듈 경계와 회귀 경로를 찾는 증거로만 재사용한다.

## 2. 새 설계 원칙

1. 실행 코드, 글리프, 문자 테이블은 이를 사용하는 모듈이 소유한다.
2. 공용 Work RAM에는 영구 실행 코드나 영구 글리프 풀을 두지 않는다.
3. 공용 CD_READ를 가로채 모든 오버레이 뒤에 sidecar를 적재하지 않는다.
4. 모듈이 내려가면 그 모듈의 훅과 캐시도 함께 폐기된다.
5. 필드, 전투, 메뉴, 이벤트, 던전은 별도 renderer/ABI로 취급한다.
6. 원본 BIOS의 일본어 GETFNT는 fallback으로 보존한다.
7. 수정 System Card는 진단용 선택지일 뿐 배포 패치의 필수 조건으로 만들지 않는다.
8. 추가 디스크 공간은 loader graph에 등록된 모듈 또는 명시적 번역 모듈로만 사용한다.
9. 각 단계는 이전 단계의 전체 전환 회귀를 통과해야 다음 단계로 이동한다.
10. 정적 검증만으로 PASS하지 않으며, 실제 BizHawk 실행 결과를 필수 증거로 남긴다.

## 3. 목표 구조

```text
원본 CD 모듈 디렉터리/로더
        |
        +-- field family  -> field code + field text + field glyph subset
        +-- battle family -> battle code + battle text + battle glyph subset
        +-- menu family   -> menu code + menu text + menu glyph subset
        +-- event family  -> portrait/event code + event glyph subset
        +-- dungeon family-> tower/dungeon code + dungeon glyph subset
        |
        `-- optional translation modules
              로더가 명시적으로 읽고, 대상 family가 소유한 RAM에 배치
```

공통 글리프는 필요한 family에 복제한다. 디스크 중복보다 런타임 소유권과 전환
안전성을 우선한다. 전체 한글 폰트를 한 번에 RAM에 상주시킬 필요는 없다.

## 4. 작업 단계

### Z0 — 기준선 정리

- [x] 원본 `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin/.cue` 보존
- [x] 루트의 기존 파생 패치 BIN/CUE 삭제
- [x] 기존 `Task.md`를 폐기된 이력으로 표시
- [x] 새 전략 문서를 활성 기준으로 지정

후속 runtime PASS 조건(아직 미실행):

- 루트에 원본 CUE/BIN 한 쌍만 존재한다.
- 분석용 JSON/TSV, 번역 CSV, 글리프 패키지, 도구는 보존된다.

### Z1 — CD 모듈 디렉터리와 loader graph 확정

목표: 게임의 모듈을 추측 LBA가 아니라 실제 로더 항목으로 식별한다.

- [ ] 부트/kernel이 사용하는 모듈 디렉터리 또는 LBA 테이블 위치 확인
- [ ] `LBA`, sector count, load bank, entry point, 호출자, 복귀 모듈 기록
- [ ] 최소 family: field, battle, menu/Memo, portrait/event, tower/dungeon
- [ ] 전투 전후와 탑 진입 경로를 하나의 전환 그래프로 작성
- [ ] 동일 LBA가 상황별로 다른 목적에 쓰이는지 검사
- [ ] 코드·텍스트·그래픽·작업 버퍼가 차지하는 bank interval 기록

산출물:

- `translation/ziria_module_catalog.json`
- `translation/ziria_loader_graph.json`
- `Z1_모듈_로더_카탈로그.md`

PASS:

- 기준 경로의 모든 대형 CD_READ가 명명된 모듈/자원에 연결된다.
- 각 family의 로드 시작과 종료 조건, 소유 bank, 복귀 대상이 명확하다.

### Z2 — 무변경 모듈 추출·재조립

목표: 번역 코드를 넣기 전에 모듈 빌드 파이프라인이 원본과 동일함을 증명한다.

- [ ] 원본에서 Z1 모듈들을 개별 binary로 추출
- [ ] 모듈별 load address와 bank layout을 linker configuration으로 표현
- [ ] 아무 패치도 없는 상태로 모듈을 재조립
- [ ] 재삽입한 전체 BIN이 원본과 바이트 단위로 동일한지 확인
- [ ] CUE의 track 시작, pregap, audio track 참조를 변경하지 않음

산출물:

- `module_relink/` 빌드 골격
- `translation/ziria_identity_rebuild.json`

PASS:

- identity rebuild의 SHA-256이 원본 BIN과 동일하다.
- 원본 기준 경로가 BIOS→필드→전투→필드→탑까지 정상 진행된다.

### Z3 — 모듈 재링크 및 확장 공간 규약

목표: 천외마경식으로 모듈별 코드와 추가 block을 링크할 수 있게 한다.

- [ ] WLA-HuC6280 또는 동등한 HuC6280 linker로 모듈별 section 정의
- [ ] 원본 section, 확장 code, text, glyph, relocation 영역 분리
- [ ] 추가 block이 필요하면 loader table과 sector allocation을 함께 변경
- [ ] 고정 빈 bank를 추측하지 않고 family loader가 소유권을 부여
- [ ] 모듈별 최대 크기와 CD 배치 충돌을 자동 검사

금지:

- 임의 Work RAM 실행
- 원본 CD_READ 뒤의 무조건 sidecar 호출
- 다른 family가 사용하는 bank에 데이터 상주시킴
- 원본 fill sector만 보고 빈 공간으로 판정

PASS:

- 더미 확장 section 한 개가 지정 family에서만 로드되고 다음 family 전환 시 폐기된다.
- 원본 그래픽과 실행 흐름에 차이가 없다.

### Z4 — field family 1글자 모듈 로컬 PoC

- [x] field 모듈의 기존 `$8754/$8755` 로컬 GETFNT wrapper 재사용
- [x] `가` 한 글자의 Galmuri8x8 기반 32바이트 expanded glyph 포함
- [x] 일본어는 변경되지 않은 원본 BIOS GETFNT로 fallback
- [x] 원본 실행 코드와 GETFNT callsite는 변경하지 않음
- [x] 공용 Work RAM, 전역 dispatcher, sidecar 없이 첫 대사 한 글자 출력

PASS:

- 한글 한 글자 정상 출력
- Memo 진입/복귀 정상
- 첫 전투 공격과 필드 복귀 정상
- 탑 진입 정상

판정(2026-07-19): **Z4 PASS**. v1의 MPR6 `$C737` 실행은 Memo를 손상했고,
v2의 반복 `00` 구간 사용은 원본 `$8754/$8755` 글리프 레코드를 덮어 필드 캐릭터
그래픽을 손상했다. v3는 원본 `$966A..$9697` 로컬 디스패처와 `$9172` 글리프 슬롯을
그대로 활용하여 실행 코드·callsite·MPR 변경 0바이트, 전체 디스크 실제 변경 20바이트로
모든 Z4 런타임 게이트를 통과했다. 세부 기록은 `Z4_필드_1글자_로컬슬롯_PoC.md`와
`translation/ziria_z4_field_oneglyph_v3_manifest.json`이 소유한다.

### Z5 — battle family 전용 section PoC

- [x] 전투 renderer와 문자 fetch 경로 식별
- [x] 상주 엔진 안에서 field `$8754/$9172`와 분리된 battle `$8755/$9192` 슬롯 할당
- [x] 공격 메시지 `%sの攻撃！` 중 한 글자를 `$8755`로 교체
- [x] field와 battle의 text code 및 glyph record를 서로 다른 슬롯으로 유지

초기 가정과 달리 첫 전투 LBA 290은 문자 renderer를 소유하지 않는다. 런타임 trace에서
364회의 GETFNT가 모두 상주 `field.main_engine`의 `$967E`(MPR4=`$82`)를 통과했고,
정확한 `$4036` 스트림 추적에서도 전투 원문은 MPR6=`$84`, 물리
`$108ADA-$109F67`에서 읽혔다. LBA 290 bank `$68-$7F`의 문자 read는 0회였다.
따라서 family 독립성은 별도 renderer 복제가 아니라 공용 renderer 내부의 별도 text/glyph
section으로 구현한다.

PASS:

- 공격 애니메이션, 결과 처리, 필드 복귀가 원본과 동일하다.
- 전투 후 탑 진입도 정상이다.

판정(2026-07-19): **Z5 RUNTIME PASS**. Z4 포함 전체 Track02 실제 변경은 34바이트이며,
Z5 증분은 battle `$8755` 글리프 13바이트와 공격 문자 lead 1바이트, 총 14바이트다.
실행 코드, BIOS, MPR, Work RAM, loader table, LBA 290, audio는 변경하지 않았다.

### Z6 — 전환 family 통합 게이트

- [x] field + battle + tower/dungeon 모듈을 한 빌드에서 결합
- [x] menu/Memo family 추가
- [x] portrait/event family 추가
- [x] 모듈 전환마다 MPR, stack, zero page, loader state를 비교

정밀 추적에서 1,602회의 GETFNT가 전부 상주 `field.main_engine`의 `$967E`,
MPR4=`$82`를 사용했다. 별도 Memo·tower·portrait renderer 가정은 폐기하고,
family 경계는 mode-06 장면 패키지의 실제 스트림 소스로 정의한다.

Z6 v1은 Z4의 공용 `가` 코드 `$8754`를 재사용한다. 압축 토큰 두 바이트를 같은
길이의 raw 코드 `87 54`로 교체하며, 필드 Memo와 탑 Memo 복제본, 탑 일반 대사,
초상화 이벤트의 **화자명** 네 구간만 수정한다. 대사 본문 첫 글자는 수정하지 않았다.
Z6 증분은 8바이트이고 Z4+Z5+Z6 전체
Track02 변경은 42바이트다. 코드, 글리프 레코드, BIOS, MPR, Work RAM, loader,
audio, CUE 구조는 변경하지 않는다. 정적 검증과 런타임 회귀가 모두 PASS했다.

판정(2026-07-19): **Z6 RUNTIME PASS**. 네 family의 화자명 `가`와 전환 경로가
정상임을 확인했다. 첫 필드 대사 본문의 `가`는 PASS로 재확인했다. Memo 본문
첫 글자와 탑 진입 직후 대사 본문 첫 글자는 확인하지 않았으므로 `NOT_CHECKED`이며,
Z7/Z8에서 별도 표본으로 검증한다.

필수 회귀 순서:

1. 첫 대사
2. Memo 진입·복귀
3. 첫 전투 공격
4. 필드 복귀
5. 전투 후 탑 진입
6. 초상화 대사

PASS:

- 위 경로에서 화면 손상, 검은 화면, 잘못된 필드 전환, `EXEC BRK`가 없다.

### Z6.1 — Memo·탑 실제 본문 consumer 게이트

- [x] 첫 필드 Memo의 `#1` 뒤 실제 본문 위치 확정
- [x] 탑 진입 초상화 대사의 `#1` 뒤 실제 본문 위치 확정
- [x] 두 위치를 기존 `$8754/$9172`의 `가`로 고정 길이 교체
- [x] Z6 대비 4바이트 외 변경이 없음을 정적 검증
- [x] Memo 본문 `가`와 정상 복귀 런타임 확인
- [x] v1의 탑 본문 표본이 뒤쪽 초상화 이벤트였음을 런타임으로 판별
- [x] 실제 탑 진입 후 첫 대사 `iso:05BA0EA`의 본문 시작점을 `0x05BA0F5`로 정정
- [x] v1 오표본을 상속하지 않는 v2 정적 빌드 및 diff 검증
- [x] v2 탑 진입 후 첫 대사 본문 `가`와 전환 안정성 런타임 확인

빌드:

- `tools/build_ziria_z6_1_body_consumers.py`
- `translation/ziria_z6_1_body_consumers_v1_manifest.json`
- `tools/build_ziria_z6_1_body_consumers_v2.py`
- `translation/ziria_z6_1_body_consumers_v2_manifest.json`
- v2 BIN SHA-256:
  `5F76640EC67713BFBF42F42D9B3C4E468DB537D5A3923FD27C87F6BF861C7C46`

현재 상태: **Z6.1 v2 RUNTIME PASS**

### Z7 — 모듈별 폰트·글리프 패키지

- [x] `master_text.csv`의 문자를 family별로 분류
- [x] 공통 core glyph와 family 전용 glyph를 분리
- [x] Galmuri8x8에서 PCE용 글리프를 재현 가능하게 생성
- [x] 모듈별 glyph map, width/advance, fallback table 생성
- [x] 글리프 중복과 모듈 크기를 보고서로 출력

정책:

- 공통 글리프 복제를 허용한다.
- 전체 폰트 상주보다 family 독립성을 우선한다.
- 장면 중 CD 스트리밍은 금지하고 장면 로드 시 완결된 패키지를 적재한다.

결과:

- 생성기: `tools/build_ziria_z7_glyph_packages.py`
- 독립 검증기: `tools/verify_ziria_z7_glyph_packages.py`
- manifest: `translation/ziria_z7_glyph_packages_manifest.json`
- 보고서: `Z7_모듈별_글리프_패키지.md`
- Galmuri8x8에서 전체 고유 한글 1,053자를 모두 렌더했으며 누락 글리프는 0건이다.
- storage module과 renderer family의 교차점 99개에 로컬 코드 맵, 32-byte
  expanded pool, 18-byte packed pool, width/advance 및 fallback 표를 생성했다.
- 최대 패키지는 563자/packed 추정 13,576바이트이며 940-code 용량을 넘는
  패키지는 0개다.
- 네 core family의 엄격 교집합은 `부`, `지` 2자다. 이 글자들도 전역 RAM을
  참조하지 않고 필요한 패키지에 복제한다.
- 동일 입력 2회 생성 시 manifest SHA-256
  `2318290A79E0B68F9F4199AED89E88F090A721EC5C6CBCCFD54D358B6297367C`로
  일치했다.
- 검증 결과: `Z7 GLYPH PACKAGES: PASS (99 packages, 32283 instances, max 563 glyphs)`.
- 번역 `needs_review` 17행은 집계에는 포함했으나 릴리스 입력 차단 상태로
  유지한다. 제어코드 불일치는 0건이다.
- 이 단계는 CUE/BIN을 수정하지 않았다. 실제 loader extension 결합은 Z8에서
  수행한다.

### Z8 — 모듈별 텍스트 컨테이너와 리다이렉트

- [x] 원문 엔트리를 family별 컨테이너로 재분류
- [ ] 포인터/continuation/terminator를 renderer별로 정의
- [x] 번역 문자열은 해당 family 모듈 또는 명시적 번역 모듈에 배치
- [ ] 고정 길이 원문 공간에는 검증된 redirect만 기록
- [x] 이름, 메뉴, 전투 command, 아이템, 시스템 메시지를 별도 테이블로 유지

Z8 v1 구조 결과(2026-07-26):

- 18,817개 물리 레코드를 103개 `storage module + renderer family`
  분석 컨테이너로 분리했다. 이 컨테이너는 아직 runtime pointer/index 형식이 아니다.
- 모든 원본 raw가 Track02 ISO와 일치하고 `00`으로 종료됨을 확인했다.
  원문과 번역의 `0B/0C/0D/0E/#x/%x/7E` 토큰 순서 불일치는 0건이다.
- 25개 category/subcategory 의미 테이블을 별도 생성해 이름·메뉴·전투
  command·아이템·시스템 계열이 서로 병합되지 않게 했다.
- 번역 CSV의 `·` 12행/24회는 원문을 변경하지 않고 게임 기본 중점
  `A5`로 인코딩하는 명시적 별칭으로 감사 기록했다.
- 8 KiB 경계 침범, 미매핑 문자, 보호 원문 불일치는 모두 0건이다.
  독립 검증기와 재빌드 결정성 검증도 PASS했다.
- renderer별 전체 참조 카탈로그와 loader-owned redirect/index가 아직
  증명되지 않았으므로 상태는 `STRUCTURE_PASS_RELOCATION_BLOCKED`다.
  과거 상주 훅의 `01/02` redirect/continuation 규약은 재사용하지 않는다.

Z8 v2 field dialogue 참조 결과(2026-07-26):

- `field.main_engine`이 소유하는 overlay directory 55개를 전수 대조했다.
  logical entry 2의 Track02 `0x83539` 한 곳만 LBA 482×96 sectors를 가리키며,
  원본 `0001E260`을 `482 + 96`으로 왕복했다.
- 해당 scene extent `0x0F1000..0x121000` 안의 dialogue 레코드 236개를
  source-reference 카탈로그로 고정했다. 모든 raw와 `00` 종료가 원본 ISO와
  일치한다.
- logical address 자체가 아니라 소비 시점 MPR에서 계산한 scene-relative
  24-bit key를 채택했다:
  `(MPR[logical>>13]-$68)*$2000 + (logical&$1FFF)`.
  236개 키 모두 `$68-$7F` 범위에서 왕복했다.
- 기존 장기 trace에서 runtime 소비가 확인된 레코드는 9개이며, 그중 8개만
  전체 raw 바이트가 관측됐다. 나머지 227개는 runtime 미관측이다.
- 관측 logical 값을 scene raw에서 검색한 결과는 우연 일치를 포함하므로
  포인터 증거로 승인하지 않았다. 정적 event-bytecode decoder 또는 동등한
  전체 runtime coverage가 필요하다.
- 따라서 loader reference는 PASS지만 text reference 분모는 OPEN이다.
  redirect/index와 CUE/BIN/ISO는 만들지 않았고 상태는
  `LOADER_REFERENCE_PASS_TEXT_REFERENCE_DENOMINATOR_OPEN`이다.

Z8 v3 source-key probe 준비 결과(2026-07-26):

- 236개 source key lookup과 `$4293/$42DE/$42AB/$42BA` stream reader,
  `$E009` mode-06 CD read를 관측하는 BizHawk Lua probe를 작성했다.
- probe는 host TSV/status 파일만 기록한다. memory/controller/register/state/
  disc write API는 사용하지 않으며 정적 감사 결과 0건이다.
- 기존 Z6 장기 trace를 새 key 수식으로 재생한 field stream read는 828회다.
  계산 key와 trace overlay offset 및 Track02 ISO offset 불일치는 모두 0건이다.
- 정확한 레코드 시작 hit는 8개, 내부 hit까지 포함하면 9개로 Z8 v2
  카탈로그와 일치한다.
- lookup·오프라인 재생·Lua 안전성 독립 검증과 재생성 결정성을 통과했다.
  매니페스트 SHA-256은
  `42A0A0C84E6EE5C8CDEFF3BDFF5F1448D4A953C56C8FF23BA519B8AC18E64EB6`다.
- 새 BizHawk 세션의 runtime capture는 아직 없으므로 상태는
  `OFFLINE_REPLAY_PASS_RUNTIME_CAPTURE_PENDING`이다. redirect/index는 계속
  차단한다.

Z8 v4 source-key runtime 결과(2026-07-26):

- 사용자가 첫 대사 → Memo 진입·복귀 → 첫 전투·필드 복귀 → 탑 진입
  경로를 완료한 캡처에서 trace 852행을 확보했다.
- field scene stream은 783회였고 `START_HIT`는 9회, 고유 ID는 8개다.
  고유 ID 집합은 Z8 v3 오프라인 재생의 정확 시작 ID 8개와 완전히 같다.
- 모든 `START_HIT`에서 MPR 기반 24-bit source-key 수식, 236행 lookup의
  catalogue ID와 ISO 위치, 관측된 mode-06 scene identity가 일치했다.
  불일치는 각 0건이다.
- mode-06 로드는 LBA 482에서 290, 2882로 전환됐으며 probe가 연결된
  상태에서 경로 완료 시 emulator failure는 보고되지 않았다.
- 독립 검증기와 Python 구문 검사를 통과했다. 런타임 매니페스트 SHA-256은
  `F7ABA6B1DAD050175BC14D7BE92D3081D5F72F1C5F5028A58256A5B89421FDC9`다.
- 판정은 `RUNTIME_SOURCE_KEY_PASS_DENOMINATOR_OPEN`이다. source-key 산식과
  관측 소비자는 확정했지만 236개 중 미관측 228개의 정적 참조 분모가
  남았으므로 redirect/index와 CUE/BIN/ISO 변경은 계속 차단한다.

PASS:

- 첫 500개 단위가 다음 대사와 제어코드를 침범하지 않고 출력된다.
- 원문과 번역의 종료·페이지·화자 상태가 일치한다.

### Z9 — renderer별 확대

다음 순서로 각각 독립 PASS 후 통합한다.

1. 필드 일반 대사
2. 필드 이벤트·초상화
3. 메뉴·Memo·장비·상점
4. 전투 command·메시지
5. 탑·던전·특수 이벤트
6. 저장·불러오기·이름
7. 엔딩·크레딧·미니게임

한 renderer의 훅을 다른 renderer에 일반화하지 않는다.

### Z10 — 전체 빌드와 배포 게이트

- [ ] 원본 해시 및 revision 검사
- [ ] 모듈별 크기·relocation·branch 검증
- [ ] loader table과 CD sector overlap 검사
- [ ] MPR/stack/zero-page 보존 검사
- [ ] 전체 BIN diff를 선언된 module/loader 영역과 대조
- [ ] CUE track 구조 보존
- [ ] xdelta 재적용 결과가 목표 BIN과 동일
- [ ] 장시간 회귀 및 SaveRAM 재시작 검사

최종 조건:

- BIOS/CUE 오류 0건
- 미매핑 글리프 0건
- 대사 누락 및 제어코드 손상 0건
- 메모·전투·탑·초상화 회귀 0건
- 수정 BIOS 없이 배포 패치 실행 가능

## 5. 기존 산출물 재사용 정책

재사용:

- `master_text.csv`와 번역 CSV
- Galmuri8x8 폰트 정책 및 글리프 생성기
- CD_READ trace와 loader 후보 자료
- 원문 추출 결과, 제어코드 분석, 포인터 분석
- 실패 장면 SaveRAM과 회귀 순서

참고만 하고 구현에는 사용하지 않음:

- `$2B0F` Work RAM 훅
- `$5230` 공용 디스패처
- bank `$6D/$84` 영구 글리프 풀
- LBA 9178 자동 sidecar 재적재 wrapper
- 수정 System Card 일괄 글리프 교체

삭제된 루트 패치 BIN/CUE는 재생성하지 않는다. 새 산출물은 Z2 identity rebuild가
PASS한 뒤부터 `ziria_zNN_...` 명명 규칙으로 생성한다.

## 6. 다음 실행 항목

다음 작업은 **Z1 — CD 모듈 디렉터리와 loader graph 확정**이다. 이 단계에서는
원본 BIN을 수정하지 않고 기존 trace, 로더 코드, LBA 테이블을 분석한다.

참조:

- https://github.com/suppertails66/tenmatools
- https://github.com/suppertails66/tenmatools/blob/master/tenma/build.sh
- https://github.com/dshadoff/SYSCARD_Translatefont

## 7. Z1 실행 결과 (2026-07-18)

- [x] 원본 Track02의 두 55-entry LBA 테이블을 원본 해시 고정 상태로 재파싱
- [x] LBA, sector count, load bank, mode 및 알려진 실행 진입점 기록
- [x] field, battle, menu/Memo, portrait/event, tower/dungeon family 분류
- [x] 시작 필드 → 전투 → 필드 복귀 / 탑 진입 전이 그래프 작성
- [x] 장면 패키지의 공통 덮어쓰기 구간 `$68-$7F` 확정
- [x] Memo와 초상화는 별도 CD_READ가 없는 상주 하위 렌더러로 분류

산출물:

- `translation/ziria_module_catalog.json`
- `translation/ziria_loader_graph.json`
- `Z1_모듈_로더_카탈로그.md`
- `tools/build_ziria_z1_loader_graph.py`
- `tools/verify_ziria_z1_loader_graph.py`

판정: **Z1 관측 경로 PASS**. Memo/초상화의 정확한 runtime entry PC는 family 분리
직전에 추가로 추적하되, Z2 무수정 identity rebuild의 시작을 막지는 않는다.

## 8. Z2 실행 결과 (2026-07-18)

- [x] CUE의 34개 트랙 경계와 sector size를 계산하고 전체 BIN 크기와 대조
- [x] Track 02 전체를 152개 비중첩·무공백 세그먼트로 추출
- [x] primary/overlay 논리 모듈 110개와 의미 모듈 10개를 별도 binary로 추출
- [x] 세그먼트만으로 Track 02 identity rebuild
- [x] raw audio 구간과 재조립 Track 02를 결합해 전체 BIN identity rebuild
- [x] 원본 CUE를 바이트 단위로 보존
- [x] 모듈별 bank/runtime 계약을 `module_relink/linker_layout.json`으로 기록

판정: **Z2 PASS**. Track 02, 전체 BIN, CUE SHA-256이 각각 원본과 완전히 동일하다.
다음 단계는 Z3 모듈 section 분리와 확장 공간 규약 수립이다.

## 9. Z3 실행 결과 (2026-07-18)

- [x] 천외마경의 모듈별 WLA patch, 중간 컨테이너, 2-pass link 원칙 확인
- [x] 12개 모듈/하위 렌더러에 original, extension code, text, glyph, relocation 정의
- [x] 10개 실제 모듈 identity section link 및 입력 해시 일치 확인
- [x] sector allocation과 owning-loader registration의 원자적 registry 계약 구현
- [x] Work RAM, implicit gap, fill run, auto sidecar, shared scene bank 금지
- [x] `$68-$7F` cross-family persistent section 금지
- [x] 위험 배치 7종 fail-closed 거부 테스트

판정: **Z3 구조 PASS**. 승인된 non-zero extension은 의도적으로 0개이며, Z4의
field 한 글자 PoC에서 최초 등록한다.

## Z8.5 정적 event-bytecode 참조 분모 (2026-07-26)

- [x] 236행의 참조 소유자를 opcode 또는 Memo 포인터로 전수 분류
- [x] 인라인 opcode `02` 217개, `03` 10개, `14` 1개 확인
- [x] Memo little-endian 포인터 7개와 대상 `C01E..C059` 역참조 확인
- [x] 실제 text consumer 235개로 정적 분모 확정
- [x] 잘못 검출된 가나 lookup table 1행 제외
- [x] master 경계 오류 3행 fail-closed 차단
- [x] `iso:010CAE1`, `iso:010D080`의 누락 prefix를 포함하도록 원문/번역 경계 보정
- [x] `iso:011F011`을 실제 Memo 문자열 시작 `0x011F01E`로 보정
- [x] false positive `iso:010F080`을 field 대사 인덱스에서 제거
- [x] 보정된 235행 source-key/index 생성

판정: **STATIC_DENOMINATOR_PASS_BOUNDARY_REPAIR_REQUIRED**.
참조 분모는 닫혔지만 안전한 경계는 232행뿐이므로 redirect/index와
CUE/BIN/ISO 생성은 계속 차단한다.

산출물:

- `module_relink/z8_field_event_refs/field_event_reference_catalog.csv`
- `translation/ziria_z8_field_event_bytecode_manifest.json`
- `Z8_5_field_event_bytecode_result.md`
- `tools/analyze_ziria_z8_field_event_bytecode.py`
- `tools/verify_ziria_z8_field_event_bytecode.py`

## Z8.6 field 경계 보정 및 source-key index (2026-07-26)

- [x] `iso:010CAE1`을 실제 opcode-02 payload 시작 `iso:010CABD`로 보정
- [x] `iso:010D080`을 실제 opcode-02 payload 시작 `iso:010D036`으로 보정
- [x] 두 누락 레코드의 전체 일본어 원문과 기존 번역 자산을 교차 확인
- [x] `iso:011F011`을 Memo 포인터가 가리키는 `iso:011F01E`로 보정
- [x] `iso:010F080` false positive를 정규 인덱스에서 제외
- [x] 235개 corrected ID와 24-bit little-endian source key 유일성 확인
- [x] 모든 235개 NUL 레코드와 원본 ISO 바이트 일치 확인
- [x] 독립 검증 및 결정성 재생성 검증 통과

판정: **BOUNDARY_REPAIR_PASS_SOURCE_INDEX_CLOSED**.
`master_text.csv`는 이전 매니페스트의 불변 기준으로 유지하고,
`ziria_z8_field_boundary_repairs.csv`를 보정 overlay로 사용한다. 이후 Z8의
정본 입력은 235행 `ziria_z8_field_source_key_index.tsv`다.

아직 redirect/index의 런타임 바이트 형식은 설계하지 않았고 CUE/BIN/ISO도
변경하지 않았다. 다음 게이트는 renderer family 하나를 고른 뒤 이 235개
소비자 전체에 대해 loader-owned redirect/index 형식을 증명하는 것이다.

산출물:

- `translation/ziria_z8_field_boundary_repairs.csv`
- `translation/ziria_z8_field_source_key_index.tsv`
- `translation/ziria_z8_field_boundary_repair_manifest.json`
- `Z8_6_field_boundary_repair_result.md`
- `tools/build_ziria_z8_field_boundary_repairs.py`
- `tools/verify_ziria_z8_field_boundary_repairs.py`

## Z8.7 field redirect wire format (2026-07-26)

- [x] corrected consumer 235개를 source key 오름차순으로 직렬화
- [x] 32-byte header + 12-byte fixed record 형식 확정
- [x] 원문 길이와 번역 길이를 별도로 기록해 continuation을 명시
- [x] inline opcode 02/03/14와 Memo pointer consumer를 kind/flags로 분리
- [x] lookup miss는 변경 없는 원문 stream으로 fallback
- [x] 520개 한글의 단일 field-local Galmuri8x8 코드표 생성
- [x] 번역 문자열 14,640바이트의 8 KiB 경계 교차 0건 확인
- [x] 원본 텍스트에 redirect marker를 기록하지 않음
- [x] 독립 검증과 결정성 재생성 검증 통과

고정 레코드:

1. source key: unsigned 24-bit little-endian
2. text blob 상대 target: unsigned 24-bit little-endian
3. original length: unsigned 16-bit little-endian, 원문 NUL 포함
4. translated length: unsigned 16-bit little-endian, 번역 NUL 포함
5. consumer kind: 1 byte
6. continuation flags: 1 byte

inline consumer는 번역 NUL에서 `source_key + original_length`로 원문 event
stream을 재개한다. Memo pointer consumer는 native pointer-string return을
사용한다. 이 차이를 과거처럼 원문 내 임의 `01/02` 마커가 아니라 인덱스
레코드의 kind/flags로 표현한다.

판정: **WIRE_FORMAT_PASS_LOADER_ALLOCATION_AND_ABI_OPEN**.
235개 source/reference 분모와 디스크 wire 형식은 닫혔다. 그러나
loader-owned sector/LBA 배치, field renderer hook entry와 live cursor ABI,
packed18 적재·확장 목적지, relocation/branch reachability는 아직 열려 있다.
따라서 disc build는 계속 차단하며 CUE/BIN/ISO를 수정하지 않았다.

산출물:

- `module_relink/z8_field_redirect_format/field_dialogue_index.bin`
- `module_relink/z8_field_redirect_format/field_dialogue_text.bin`
- `module_relink/z8_field_redirect_format/field_dialogue_glyphs_packed18.bin`
- `module_relink/z8_field_redirect_format/field_dialogue_glyph_map.csv`
- `module_relink/z8_field_redirect_format/field_dialogue_records.tsv`
- `module_relink/z8_field_redirect_format/field_dialogue_format.json`
- `translation/ziria_z8_field_redirect_format_manifest.json`
- `Z8_7_field_redirect_format_result.md`
- `tools/build_ziria_z8_field_redirect_format.py`
- `tools/verify_ziria_z8_field_redirect_format.py`

다음 게이트는 이 형식을 바꾸지 않고 loader-owned allocation과 field
renderer cursor/continuation ABI를 함께 증명하는 것이다.

## Z8.8 loader-owned allocation 및 reader ABI (2026-07-26)

- [x] `$4036 -> $4284` 공용 stream reader 진입점 확인
- [x] `$55`, `$53`, `$2E69`, 기본 `$4B/$4C` 선택 우선순위 확인
- [x] `A/$2D80` 반환, `X/Y` 보존, MPR 저장·복원 계약 확인
- [x] `$54/$55` NUL에서 기본 stream으로 자동 continuation 확인
- [x] field scene `$68-$7F`, engine `$80-$84`, resource `$85-$87` 소유권 확인
- [x] persistent free bank 0개 및 extension registry 승인 allocation 0개 확인
- [x] 235개 원문 범위의 회수 총량과 연속 run 재계산
- [x] 입력 고정 검증기 통과

판정: **ABI_PASS_UNCHANGED_WIRE_ALLOCATION_FAIL**.

ABI는 닫혔지만 Z8.7 wire를 그대로 배치할 공간은 없다. 원문 회수 범위는 총
14,816 bytes이고 최대 연속 run은 344 bytes다. Z8.7의 index/text/glyph 합계는
26,852 bytes이며 가장 작은 연속 blob인 index도 2,852 bytes다. 따라서 총량과
연속성 양쪽에서 실패한다. CUE/BIN/ISO 생성은 계속 차단한다.

산출물:

- `translation/ziria_z8_8_loader_allocation_abi_manifest.json`
- `module_relink/z8_8_loader_allocation_abi/source_reclaim_ranges.tsv`
- `Z8_8_loader_allocation_abi_result.md`
- `tools/build_ziria_z8_8_loader_allocation_abi.py`
- `tools/verify_ziria_z8_8_loader_allocation_abi.py`

다음 게이트 Z8.9는 `$4036` ABI를 유지하면서 장면별 text/glyph package 또는 더 작은
runtime asset 표현을 비교해 저장 형식을 버전업하는 단계다.

## Z8.9 확장 할당 설계 및 Z8.9a 디스크 감사 (2026-07-27)

- [x] 2단 할당 설계 확정: Plan A-1(장면 패키지 내부 cold 구간 in-package 할당,
      로더 변경 0바이트) 우선, Plan A-2(승인 섹터 번역 모듈 + 로더 2차 read)는
      A-1 부족 시만. wire v2는 region table + fragment 배치로 버전업하되
      `$4036` reader ABI는 보존한다. 설계: `Z8_9_field_확장할당_설계.md`
- [x] Track02가 MODE1/2048 cooked 트랙임을 확정하고 슬라이스 해시를 고정
- [x] 두 55-entry 테이블이 96섹터 슬롯 격자에서 서로 끼어드는 구조임을 실측
- [x] 장면 패키지(482/290/2882)에 꼬리 fill이 없음을 실측 — RAM 여유는
      런타임 coverage로만 증명 가능
- [x] Z8.9a 디스크 참조 전수 감사: **AUDIT_PASS**. 승인 구간은
      **LBA 9178..9328 (150섹터, 307,200 B, 순수 00, 전 참조원 미참조)** 단 하나.
      비-fill 미참조 4,024섹터는 외부 참조 추정으로 전부 거부. 독립 검증 PASS.
- [x] Z8.9b scene RAM coverage probe(`$68-$7F` read+write, 장면 identity 게이트)와
      오프라인 검증기 작성, 합성 캡처 end-to-end 검증 완료
- [x] Lua whole-bus probe는 **플레이 불가 속도 + 재적재 CPU 복사 오염 결함으로 폐기**.
      PCEHawk 내장 CDL 세그먼트 캡처(네이티브 속도) + 
      `tools/analyze_ziria_z8_9_cdl_coverage.py`로 대체, 합성 .cdl 검증 완료
- [x] Z8.9b 실제 캡처 (2026-07-27): 깨끗한 세그먼트 2개(접근 10.1%/8.1%)로
      **CANDIDATES_FEASIBLE_PENDING_CANARY**. cold 165,451 B, 후보 region 132개
      /161,514 B, 최대 연속 23,151 B. 오염 세그먼트는 분석기가 자동 제외.
      무감속 로드 알리미 `tools/notify_ziria_z8_9_scene_loads.lua` 추가.
- [x] Z8.9c wire v2 배치 시뮬레이션: **PLACEMENT_PASS**. index 2,852 B(bank 69),
      glyph offset table 1,560 B, glyph 조각 2개, text blob 191개(중복 제거),
      총 28,369 B가 전부 **순수 cold 바이트**에 배치(reclaim 불사용).
      `tools/build_ziria_z8_9_wire_v2_placement.py`,
      `module_relink/z8_9_wire_v2/`.
- [x] canary 진단 빌드 생성: 배치 구간 195개를 `00 E7` 트랩 패턴으로 채운
      `..._ziria_z8_9_canary.bin/.cue` (유효 변경 27,975 B, 전체 diff 감사 PASS).
      `translation/ziria_z8_9_canary_build_manifest.json`. 릴리스 입력 금지.
- [x] canary 런타임 게이트 1차: **FAIL (2026-07-27)** — 첫 필드 진입 즉시 배경
      타일 전면 깨짐. 원인: CDL 세그먼트가 장면 로드 직후 **초기화 read**
      (그래픽→VRAM 업로드, 한 번만 읽힘)를 포함하지 못해 해당 바이트를
      cold로 오판. 대화창·스프라이트는 정상(다른 소스). 1차 canary BIN/CUE는
      무효 판정, 재생성 대상.
- [x] v3 보완: 초기화 구간 전용 probe
      `tools/trace_ziria_z8_9_field_init_coverage.lua` 작성 — 평상시 exec 훅
      2개($E009/$66FF)로 무감속, LBA 482 로드 복귀 직후 900프레임만
      whole-bus 콜백을 등록·해제해 init 접근을 기록. analyzer는 이 캡처를
      **필수 입력**으로 받아 cold에서 차감(fail-closed, 창 2회 이상 요구).
- [x] 사용자 init 캡처 완료(창 2회, 175,914 이벤트, window 240프레임).
      init read 18,528 B가 cold에서 제외됨 → cold 146,923 B, 여전히 FEASIBLE.
- [x] 재배치 PASS: index가 init-read로 판명된 bank 69(0x2000)에서
      bank 6D(0xA000)로 이동. 28,369 B 전량 순수 cold(post-init) 배치.
- [x] canary 2차 빌드 PASS: 유효 변경 28,127 B, BIN SHA-256
      `B8174FD1...5E44A1F4`.
- [x] canary 런타임 게이트 2차: **FAIL (2026-07-27)** — 초반 경로는 정상이나
      진행을 이어가자 이벤트 컷신 대화창 및 다른 맵 배경이 깨짐.
- [x] 근본 원인 확정: **LBA 482 extent의 78/96섹터는 primary(grid) 테이블
      엔트리 450/78, 546/84와 디스크를 공유**한다. 482 컨텍스트에서 cold인
      바이트도 다른 맵이 grid 엔트리로 로드하면 그래픽으로 사용된다.
      482 전용 구간은 LBA 528..546(scene offset `0x17000..0x20000`,
      36,864 B)뿐이고 그 안의 cold+reclaim 총량은 26,809 B로 필요량
      28,369 B에 미달(단편화 감안 시 더 부족).
- [x] 판정: **Plan A-1(장면 패키지 in-place 배치) 구조적 폐기**.
      Plan A-2로 전환 — 자산은 Z8.9a 승인 풀 LBA 9178..9328(순수 00,
      전 참조원 미참조)에 두고 로더 2차 `$E009` read로 cold RAM에 적재.
      원본 482 extent는 0바이트 변경이므로 공유 컨텍스트 파괴가 원천
      차단된다.
- [x] A-2 RAM 목적지 산정: mode-06 read는 bank 정렬이므로 전체 free bank만
      사용 — cold full bank `$7A,$7B`(16 KiB) + `$7E`(8 KiB) + `$6D`(8 KiB)
      = 32 KiB ≥ 28,369 B(14섹터). 3회 read(count 8/4/2)로 적재 가능.
- [x] Z8.9d 코드 공간 감사: `$5230` 00-run은 CDL 런타임 접근으로 기각,
      **`$C737..$C900` FF 457 B는 CDL 5캡처 cold + 참조 0건으로 채택**.
      Z4 v1의 `$C737` 실패는 상주 실행(MPR6 변경 컨텍스트) 탓이며, 이번
      훅은 로더 호출 창(MPR6=$84 관측 확정)에서만 실행되어 해당 없음.
- [x] Z8.9d 로더 훅 구현: `$66FC JSR $E009` → `JSR $C737`. 훅 **155 B** (코드 140 B `$C737..$C7C2` + 매핑 테이블 15 B `$C7C3`) —
      *(2026-08-22 정정: 본래 153 B로 기록했으나 매니페스트 `hook_hex`
      310 hex = 155 B가 실제 값이다. `$C737..$C900` FF 창 457 B 안이므로
      배치 판정에는 영향 없음.)*
      비-field 로드는 `JMP $E009` tail-call, field(482/96/06) 로드는 원본
      로드 후 P/A/X/Y·zp `$F8-$FF` 스택 보존 하에 3회 read
      (9178/8→$7A, 9186/4→$7E, 9190/2→$6D) 후 복원·RTS.
      huc6280_disasm_verifier `--raw` 검산 PASS(분기 5개·테이블 참조 일치).
- [x] A-2 canary 빌드 v1: 풀 LBA 9178 — **런타임 FAIL**. BizHawk
      `ReadLBA_2048` "unhandled sector type" 예외. 원인: CUE상 트랙3
      `INDEX 01`(12693) − `PREGAP`(150) = 12543 = 3365+9178, 즉
      **데이터 트랙 실사용 끝은 LBA 9178**이고 9178..9328은 트랙3 pregap
      (오디오 타입)이다. Z8.9a의 9178 승인은 트랙 경계 모델링 오류로 폐기.
- [x] 기존 한국어 패치 diff로 교차 확인: 그 패치도 9178..9205에 데이터를
      뒀다(실기 기준). 또한 **5474..6018 544섹터 갭은 기존 패치도 미사용 +
      두 테이블·전 trace 무참조**임을 확인.
- [x] A-2 canary 빌드 v2: 풀을 **LBA 5480..5494**로 이전(원본 내용 비영 —
      덮어쓰기 안전성은 canary가 검증). 훅 테이블만 변경, 디스어셈블·diff
      감사 PASS, 변경 27,577 B.
- [x] A-2 canary 런타임 게이트: **PASS (2026-08-22)** — 회귀 경로 전체에서
      원본과 동일 동작, 오디오 이상 0건. 풀 LBA 5480..5494와 RAM 목적지
      ($7A-$7B/$7E/$6D 전반부) 덮어쓰기 안전 확정.
- [ ] PASS 시: wire v2 재배치(bank 정렬 목적지) + reader redirect 훅 설계

결과 문서: `Z8_9a_disc_reference_audit_result.md`. CUE/BIN/ISO 변경 없음.
