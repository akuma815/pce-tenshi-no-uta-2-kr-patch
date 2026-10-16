# Z8.9a 디스크 참조 전수 감사 결과 / Z8.9b probe 준비

실행일: 2026-07-27
설계 문서: `Z8_9_field_확장할당_설계.md`

## Z8.9a 판정: **AUDIT_PASS**

원본 무수정 판독으로 Track02(MODE1/2048, 9,328섹터)의 참조 지도를 만들고
승인 규칙(미참조 ∧ 순수 00 fill ∧ run ≥ 8섹터 ∧ LBA ≥ 290)을 적용했다.

### 확정 사실

- CUE 기준 Track02는 **MODE1/2048 cooked** 트랙이며 BIN offset 7,914,480부터
  9,328섹터다. 슬라이스 SHA-256
  `7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9`은
  `extracted_bin/Track02_data.iso`와 바이트 단위로 동일하다.
- 정적 참조: primary 테이블(`0x424A5`) 55개 + scene 테이블(`0x83531`) 55개
  + LBA 0–290 시스템/부트/엔진 보수 예약.
- 런타임 참조: `translation/*.tsv` 전체에서 관측 CD_READ 11종 extent 수집
  (boot 2/16, 34/12, 98/20, 118/6, 226/28, 258/20, 278/12, 290/96, 482/96,
  2882/96, 3330/83).
- `JSR $E009` 콜사이트 160개를 전역 열거해 테이블 비경유 read의 존재 증거로
  기록했다(승인 판단에는 미사용, 위험 목록).
- 두 테이블 미참조 구간은 총 4,024섹터지만, **순수 fill이 아닌 미참조 데이터는
  전부 "외부 참조 추정"으로 거부**했다(ADPCM 등 비테이블 read 가능성).

### 승인 결과

| 구간 | 크기 | 내용 |
|---|---|---|
| **LBA 9178..9328** | **150섹터 / 307,200 B** | 순수 00 fill, 두 테이블·런타임 모두 미참조 |

Track02 말미의 이 구간은 과거 Task7이 sidecar 위치로 지목했던 곳과 일치하며,
Z8.7 자산 총량(26,852 B)의 11배 용량이다. Plan A-2의 디스크 배치 풀로 사용한다.
단, 오디오 트랙 직전 pregap 관례 구간이므로 실기 하드웨어 검증 항목으로 남긴다.

### 산출물·재현

- `translation/ziria_z8_9_disc_reference_audit_manifest.json`
- `module_relink/z8_9_disc_audit/referenced_extents.tsv`
- `module_relink/z8_9_disc_audit/approved_sectors.tsv`

```powershell
python -X utf8 tools\build_ziria_z8_9_disc_reference_audit.py
python -X utf8 tools\verify_ziria_z8_9_disc_reference_audit.py
```

독립 검증 결과: `PASS (approved 1 region(s), 150 sectors, 307200 bytes)`.
검증기는 해시 대조, 테이블 재파싱 대조, 승인-참조 무겹침, 순수 fill 재확인,
빌드 재실행 결정성을 확인한다.

## Z8.9b: PCEHawk CDL 세그먼트 coverage (v2 — Lua probe 폐기)

1차 Lua whole-bus probe(`tools/trace_ziria_z8_9_scene_ram_coverage.lua`)는
게임을 플레이 불가 속도로 만들어 **폐기**했다. 또한 field 재적재 시 BIOS의
mode-06 로드가 CPU 복사이므로 로드 순간을 포함한 어떤 coverage 로그도
scene RAM 전체가 접근된 것으로 오염된다는 결함을 확인했다.

대체: **PCEHawk 내장 Code Data Logger** (BizHawk 소스로 확인).

- CDL은 "Super System Card RAM"(물리 bank `$68-$7F`, 정확히 192 KiB,
  offset = `(bank-$68)*$2000 + offset` — source key 좌표와 동일)을
  **네이티브 속도(감속 없음)** 로 바이트 단위 기록한다.
- 플래그 Data/Code/CodeOperand/Stack/IndirectData/BlockXFer가 read·write·
  exec를 모두 포함하므로 **cold = 플래그 0 = 어떤 CPU 접근도 없음**.
- 로드 오염은 세그먼트 경계로 해결: 장면 로드 **완료 후 New**, 다음 장면
  전환 **전에 Save**.

분석기: `tools/analyze_ziria_z8_9_cdl_coverage.py`
(.cdl 바이너리 파서, 세그먼트 오염 검출(접근율>90% 거부), 세그먼트 2개
미만 거부, cold run + Z8.8 회수 range 병합, wire v2 feasibility 판정.
합성 .cdl로 정상·오염·부족 세 경로 모두 검증 완료.)

### 1차 캡처 결과 (2026-07-27)

- segment_b: 접근 15,019 B / 192 KiB → **cold 92.4%** (필드 콘텐츠만 포함, 유효)
- segment_a·c: 접근 100% (IndirectData 전면 마킹 = mode-06 로드 포함) → 제외
- 교훈: 전투·탑뿐 아니라 **건물 출입·맵 이동도 mode-06 로드**를 일으켜
  세그먼트를 오염시킨다. 분석기는 오염 세그먼트를 자동 제외하도록 개선했고
  (깨끗한 세그먼트 2개 미만이면 fail), 로드 순간을 화면에 표시하는
  무감속 알리미 `tools/notify_ziria_z8_9_scene_loads.lua`를 추가했다
  ($E009 단일 exec 훅 + CLEAN/DIRTY 오버레이, 키보드 Q로 세그먼트 리셋 신호).

### 캡처 절차 (사용자 실행 필요, 감속 없음)

1. BizHawk 코어 **PCEHawk** 설정, 원본 CUE 부팅.
2. **첫 필드가 보이면** Tools → Code Data Logger 열기 → **New**.
3. 필드 콘텐츠 플레이: 첫 대사, 마을 NPC 전원 대화, Memo 진입·복귀,
   초상화 이벤트. (Memo/초상화는 CD read가 없어 안전 — Z1 근거)
4. **전투에 들어가기 직전** Save As → `translation\cdl\segment_a.cdl`.
5. 전투 진행·필드 복귀 완료 후 → CDL **New** → 필드 콘텐츠 추가 플레이
   → 다음 전환(탑 등) 직전 Save As → `translation\cdl\segment_b.cdl`.
6. (선택) 탑 방문 후 필드 복귀 시 같은 방식으로 segment_c 등 추가.
7. 분석:

```powershell
python -X utf8 tools\analyze_ziria_z8_9_cdl_coverage.py translation\cdl\segment_a.cdl translation\cdl\segment_b.cdl
```

판정 분기:

- `CANDIDATES_FEASIBLE_PENDING_CANARY` → canary 진단 빌드 게이트로 진행.
- `CANDIDATES_INSUFFICIENT_ESCALATE_A2_OR_COMPRESSION` → text 압축 재평가
  후 Plan A-2(LBA 9178 번역 모듈 + 로더 2차 read) 승인 절차로 이관.

이 단계는 CUE/BIN/ISO, 로더, 원본 텍스트를 변경하지 않았다.
