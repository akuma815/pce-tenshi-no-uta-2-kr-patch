# Z5 — 전투 1글자 공용 renderer PoC

## 결론

첫 전투의 문자 출력은 LBA 290 전용 renderer가 아니라 상주 `field.main_engine`의
공용 renderer를 사용한다. field와 battle은 같은 코드를 공유하지만 서로 다른 text code와
32바이트 글리프 record로 분리할 수 있다.

- field: `$8754` → runtime `$9172`
- battle: `$8755` → runtime `$9192`
- 공용 dispatcher: runtime `$966A..$9697`
- BIOS fallback call: runtime `$967E`의 `JSR $E060`

## 런타임 소유권 증거

`trace_ziria_z5_battle_getfnt.lua`에서 364회 모두 call PC `$967E`, MPR4=`$82`였다.
후속 exact stream trace는 `$4036`의 실제 read 지점 `$42AB/$42BA`를 관측했다.

- 전투 원문: MPR6=`$84`, physical `$108ADA-$109F67`
- 공용 문자열: MPR5=`$83`, physical `$106145-$10614D`
- 치환 버퍼: MPR1=`$F8` Work RAM
- LBA 290 bank `$68-$7F` 문자 read: 0회

따라서 `scene.battle_first`는 전투 리소스·상태 패키지이며 문자 소유 모듈이 아니다.

## PoC 변경

Z4 v3 런타임 PASS 빌드를 기준으로 다음 두 write만 추가했다.

1. `field.main_engine` 모듈 `$5192`의 기존 `$8755` record를 Galmuri8x8 `가`로 교체
2. 모듈 `$96A5` 공격 메시지의 `8D55` 한 글자를 `8755`로 교체

두 바이트 문자 write는 lead만 달라 실제 변경 1바이트이며, 글리프 record 실제 변경
13바이트를 합쳐 Z5 증분은 14바이트다. Z4를 포함한 Track02 총 변경은 34바이트다.

실행 코드, callsite, BIOS, MPR, Work RAM, loader table, sector 수, LBA 290, audio는
변경하지 않았다.

## 런타임 결과

- [x] 필드 Z4 `가` 유지
- [x] 캐릭터 그래픽 정상
- [x] Memo 진입·복귀 정상
- [x] 첫 전투 공격 메시지 `가` 출력
- [x] 공격 처리 후 필드 복귀 정상
- [x] 전투 후 탑 진입 정상

판정: **Z5 RUNTIME PASS**.

근거:

- `translation/ziria_z5_battle_oneglyph_v1_manifest.json`
- `translation/ziria_z5_battle_getfnt_trace.tsv`
- `translation/ziria_z5_battle_stream_reader_trace.tsv`
- `tools/build_ziria_z5_battle_oneglyph.py`
- `tools/trace_ziria_z5_battle_getfnt.lua`
- `tools/trace_ziria_z5_battle_stream_reader.lua`
