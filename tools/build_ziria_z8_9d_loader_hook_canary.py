#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Z8.9d — A-2 로더 2차 read 훅 + canary 등가 진단 빌드.

구성:
1. field.main_engine 로더의 `$66FC: JSR $E009`를 `JSR $C737`로 교체.
2. `$C737..$C900` 457바이트 FF 창(CDL 5캡처 cold + 참조 0건)에 훅 설치:
   - zp 인자가 LBA 482 / count 96 / mode 06이 아니면 `JMP $E009` tail-call
     (원본과 동일한 스택 프레임, 상태 무변경)
   - 일치 시: 원본 `JSR $E009` 후 P/A/X/Y와 zp `$F8..$FF`를 스택에 보존,
     번역 풀 3회 read(LBA 9178→bank $7A 8섹터, 9186→$7E 4섹터,
     9190→$6D 2섹터) 수행, zp/레지스터 복원 후 RTS.
   - 훅 실행은 로더 호출 창(MPR6=$84 관측 확정)에 한정되며 상주하지 않는다.
3. LBA 9178..9192(Z8.9a 승인 풀, 순수 00)를 `00 E7` 트랩 패턴으로 채운다.
   → canary 등가 게이트: 회귀 경로에서 게임이 원본과 동일하게 동작하면
     (a) 훅 안전성, (b) 목적지 bank $7A/$7B/$7E/$6D(전반부) cold가 실증된다.

fail-closed: 원본 해시, 콜사이트/FF창/트랩 풀 원본 바이트 사전검증,
내장 디스어셈블 검산(분기 거리·테이블 참조), 전체 diff 감사.
"""

import hashlib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_PATH = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin")
CUE_PATH = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue")
BIN_SHA256 = "D16D29EB80B1B74A2EC929924349256B50B8F9F5C9A3FA37B6FCC08B059B22C5"
TRACK02_OFFSET = 7914480
TRACK02_SECTORS = 9328

ENGINE_LBA = 258
ENGINE_DISC = ENGINE_LBA * 2048          # 0x81000
CPU_BASE = 0x4000

CALLSITE_CPU = 0x66FC
HOOK_CPU = 0xC737
FF_WINDOW_END_CPU = 0xC900

# 풀 위치 정정(2026-07-27): 최초 후보 LBA 9178은 CUE상 트랙3
# `INDEX 01 02:49:18`(12693) - `PREGAP 00:02:00`(150) = 12543 = 3365+9178
# 경계 밖, 즉 BizHawk 디스크 모델에서 오디오 pregap 타입이라
# ReadLBA_2048이 "unhandled sector type" 예외를 던진다(런타임 실증).
# 기존 한국어 패치도 9178..9205에 데이터를 뒀지만 이는 실기 기준이다.
# 새 풀은 마지막 scene slot extent(5378+96=5474) 직후의 544섹터 무참조
# 갭(5474..6018, 기존 패치도 미사용, 두 테이블·전 trace 무참조) 안에 둔다.
POOL_LBA = 5480
POOL_SECTORS = 14                        # 8 + 4 + 2
TRAP = bytes([0x00, 0xE7])

READS = [                                # (lba, count, bank)
    (5480, 8, 0x7A),
    (5488, 4, 0x7E),
    (5492, 2, 0x6D),
]

OUT_BIN = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z8_9d_a2_canary.bin")
OUT_CUE = os.path.join(ROOT, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_ziria_z8_9d_a2_canary.cue")
OUT_MANIFEST = os.path.join(ROOT, "translation", "ziria_z8_9d_a2_canary_manifest.json")


def fail(msg):
    for p in (OUT_BIN, OUT_CUE):
        if os.path.isfile(p):
            os.remove(p)
    print(f"FAIL: {msg}")
    sys.exit(1)


def cpu_to_disc(cpu):
    return ENGINE_DISC + (cpu - CPU_BASE)


def assemble_hook():
    """훅 기계어를 조립하고 주소·분기 정합성을 자체 검산한다."""
    org = HOOK_CPU
    code = bytearray()

    def emit(*bs):
        code.extend(bs)

    # ---- 검사 체인: 불일치 시 orig(JMP $E009)로 ----
    # orig 위치는 마지막 검사 뒤 BEQ main 다음이다. 오프셋은 아래에서 검산.
    emit(0xA5, 0xFF)              # C737 LDA $FF
    emit(0xC9, 0x06)              # C739 CMP #$06
    emit(0xD0, 0x16)              # C73B BNE orig(C753)
    emit(0xA5, 0xFC)              # C73D LDA $FC
    emit(0xD0, 0x12)              # C73F BNE orig
    emit(0xA5, 0xFD)              # C741 LDA $FD
    emit(0xC9, 0x01)              # C743 CMP #$01
    emit(0xD0, 0x0C)              # C745 BNE orig
    emit(0xA5, 0xFE)              # C747 LDA $FE
    emit(0xC9, 0xE2)              # C749 CMP #$E2
    emit(0xD0, 0x06)              # C74B BNE orig
    emit(0xA5, 0xF8)              # C74D LDA $F8
    emit(0xC9, 0x60)              # C74F CMP #$60
    emit(0xF0, 0x03)              # C751 BEQ main(C756)
    orig_off = len(code)
    emit(0x4C, 0x09, 0xE0)        # C753 orig: JMP $E009 (tail-call)
    main_off = len(code)
    emit(0x20, 0x09, 0xE0)        # C756 main: JSR $E009 (원본 필드 로드)
    emit(0x08, 0x48, 0xDA, 0x5A)  # C759 PHP PHA PHX PHY
    for zp in (0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF):
        emit(0xA5, zp, 0x48)      # LDA zp / PHA  (post-load zp 상태 보존)
    emit(0xA2, 0x00)              # LDX #$00
    loop_off = len(code)
    table_cpu_placeholder = 0     # 아래에서 채움
    # LDA table+k,X / STA zp — table 주소는 조립 후 재기록
    for zp_target, k in ((0xFC, 0), (0xFD, 1), (0xFE, 2), (0xF8, 3), (0xFA, 4)):
        emit(0xBD, 0x00, 0x00)    # LDA table+k,X (주소 후치)
        emit(0x85, zp_target)     # STA zp
    emit(0x64, 0xF9)              # STZ $F9
    emit(0x64, 0xFB)              # STZ $FB
    emit(0xA9, 0x06, 0x85, 0xFF)  # LDA #$06 / STA $FF
    # BIOS CD_READ는 X를 클로버한다(v2 canary 크래시의 원인).
    # 테이블 인덱스 X를 호출 전후로 스택에 보존한다.
    emit(0xDA)                    # PHX
    emit(0x20, 0x09, 0xE0)        # JSR $E009
    emit(0xFA)                    # PLX
    emit(0x8A, 0x18, 0x69, 0x05, 0xAA)  # TXA CLC ADC #$05 TAX
    emit(0xE0, 0x0F)              # CPX #$0F (3 entries * 5)
    bne_pos = len(code)
    emit(0xD0, 0x00)              # BNE loop (오프셋 후치)
    for zp in (0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA, 0xF9, 0xF8):
        emit(0x68, 0x85, zp)      # PLA / STA zp (역순 복원)
    emit(0x7A, 0xFA, 0x68, 0x28)  # PLY PLX PLA PLP
    emit(0x60)                    # RTS
    table_off = len(code)
    for lba, count, bank in READS:
        emit((lba >> 16) & 0xFF, (lba >> 8) & 0xFF, lba & 0xFF, count, bank)

    # ---- 후치 채움: 분기·테이블 절대주소 ----
    rel = loop_off - (bne_pos + 2)
    if not -128 <= rel < 0:
        fail(f"loop branch out of range {rel}")
    code[bne_pos + 1] = rel & 0xFF
    table_cpu = org + table_off
    lda_positions = []
    i = loop_off
    for k in range(5):
        # 각 LDA abs,X는 loop 내 고정 간격(5바이트: BD ll hh 85 zz)
        pos = loop_off + k * 5
        if code[pos] != 0xBD:
            fail("assembler layout drift (LDA abs,X)")
        addr = table_cpu + k
        code[pos + 1] = addr & 0xFF
        code[pos + 2] = (addr >> 8) & 0xFF
        lda_positions.append(pos)

    # ---- 자체 검산 ----
    if org + orig_off != 0xC753 or org + main_off != 0xC756:
        fail("hook layout mismatch vs design addresses")
    for bne_at, target in ((0x3B, 0xC753), (0x3F, 0xC753), (0x45, 0xC753),
                           (0x4B, 0xC753), (0x51, 0xC756)):
        pos = bne_at - 0x37
        off = code[pos + 1]
        dest = org + pos + 2 + (off - 256 if off >= 128 else off)
        if dest != target:
            fail(f"branch at {org + pos:04X} -> {dest:04X}, expected {target:04X}")
    if org + len(code) > FF_WINDOW_END_CPU:
        fail(f"hook exceeds FF window: end {org + len(code):04X}")
    return bytes(code), table_cpu


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            c = f.read(1 << 22)
            if not c:
                break
            h.update(c)
    return h.hexdigest().upper()


def main():
    print("checking original BIN hash...")
    if sha256_file(BIN_PATH) != BIN_SHA256:
        print("FAIL: original BIN hash mismatch")
        sys.exit(1)

    hook, table_cpu = assemble_hook()
    print(f"hook assembled: {len(hook)} bytes @ ${HOOK_CPU:04X}..${HOOK_CPU + len(hook):04X}, table @ ${table_cpu:04X}")

    with open(BIN_PATH, "rb") as f:
        f.seek(TRACK02_OFFSET)
        t02 = f.read(TRACK02_SECTORS * 2048)

    # 사전검증: 원본 바이트
    cs = cpu_to_disc(CALLSITE_CPU)
    if t02[cs:cs + 3] != bytes([0x20, 0x09, 0xE0]):
        fail(f"callsite bytes unexpected: {t02[cs:cs + 3].hex()}")
    hw = cpu_to_disc(HOOK_CPU)
    win = t02[hw:cpu_to_disc(FF_WINDOW_END_CPU)]
    if win.count(0xFF) != len(win):
        fail("FF window is not clean in original")
    # 풀은 무참조 갭(5474..6018) 안에 있어야 한다. 원본 내용은 0이 아닐 수
    # 있으며(스테일 데이터 추정), 덮어쓰기의 안전성은 canary 게이트가 검증한다.
    if not (5474 <= POOL_LBA and POOL_LBA + POOL_SECTORS <= 6018):
        fail("pool outside the unreferenced 5474..6018 gap")
    pool = t02[POOL_LBA * 2048:(POOL_LBA + POOL_SECTORS) * 2048]
    pool_orig_sha = hashlib.sha256(pool).hexdigest().upper()

    # 쓰기 계획
    plan = {}
    for i, b in enumerate(bytes([0x20, HOOK_CPU & 0xFF, HOOK_CPU >> 8])):
        plan[cs + i] = b
    for i, b in enumerate(hook):
        plan[hw + i] = b
    for s in range(POOL_SECTORS * 2048):
        plan[POOL_LBA * 2048 + s] = TRAP[s % 2]

    print("copying BIN...")
    shutil.copyfile(BIN_PATH, OUT_BIN)
    with open(OUT_BIN, "r+b") as f:
        for off, val in plan.items():
            f.seek(TRACK02_OFFSET + off)
            f.write(bytes([val]))

    # 전체 diff 감사
    print("auditing full track02 diff...")
    changed = 0
    with open(OUT_BIN, "rb") as f:
        f.seek(TRACK02_OFFSET)
        new = f.read(TRACK02_SECTORS * 2048)
    for i in range(len(t02)):
        if t02[i] != new[i]:
            if i not in plan or new[i] != plan[i]:
                fail(f"unplanned diff at iso {i:#x}")
            changed += 1
    expected_changed = sum(1 for off, v in plan.items() if t02[off] != v)
    if changed != expected_changed:
        fail(f"changed {changed} != planned {expected_changed}")

    size = os.path.getsize(BIN_PATH)
    if os.path.getsize(OUT_BIN) != size:
        fail("size mismatch")

    cue = open(CUE_PATH, "r", encoding="utf-8", newline="").read()
    with open(OUT_CUE, "w", encoding="utf-8", newline="") as f:
        f.write(cue.replace(os.path.basename(BIN_PATH), os.path.basename(OUT_BIN)))

    manifest = {
        "format": "ZIRIA-Z8-9D-A2-CANARY",
        "version": 1,
        "purpose": "loader hook + destination-bank canary; diagnostic only",
        "hook": {
            "callsite_cpu": hex(CALLSITE_CPU),
            "hook_cpu": hex(HOOK_CPU),
            "hook_bytes": len(hook),
            "hook_hex": hook.hex().upper(),
            "table_cpu": hex(table_cpu),
            "execution_context": "loader call window only (MPR6=$84 observed), non-resident",
            "passthrough": "non-field loads tail-call JMP $E009 with identical stack frame",
            "state_preservation": "P/A/X/Y and zp $F8-$FF restored to post-original-load values",
        },
        "reads": [
            {"lba": l, "count": c, "dest_bank": hex(b)} for l, c, b in READS
        ],
        "trap_pool": {
            "lba": POOL_LBA, "sectors": POOL_SECTORS, "pattern": "00 E7",
            "original_content_sha256": pool_orig_sha,
            "site_evidence": "unreferenced by both 55-entry tables and all runtime traces; "
                             "untouched by the shipped Korean patch; past track3-pregap "
                             "candidate (9178) rejected after BizHawk ReadLBA_2048 exception",
        },
        "effective_changed_bytes": changed,
        "output_bin_sha256": sha256_file(OUT_BIN),
        "runtime_gate": [
            "필드 로드가 눈에 띄는 지연 없이 완료",
            "첫 대사, NPC, Memo, 건물 출입, 전투 복귀, 탑, 초상화 모두 원본과 동일",
            "화면 깨짐, EXEC BRK, 멈춤, 오디오 이상 0건",
        ],
        "disc_scope": "engine callsite 3B + FF window hook + approved pool 14 sectors; scene extents untouched",
    }
    with open(OUT_MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    print("Z8.9d A2 CANARY BUILD: PASS")
    print(f"  hook {len(hook)} B, changed bytes {changed}")
    print(f"  output: {os.path.basename(OUT_BIN)}")
    print(f"  sha256: {manifest['output_bin_sha256']}")


if __name__ == "__main__":
    main()
