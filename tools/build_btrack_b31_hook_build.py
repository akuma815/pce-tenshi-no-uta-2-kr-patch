#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# B31 = b30 드라이버와 동일(출력 이름만 b31): b30 bin 이 플레이 중인 EmuHawk 에 잠겨 있어 새 이름으로 빌드 (2026-10-10).
"""B트랙 B30 — b29 + 카드 미니게임 말풍선 문구 수정(역이 완성되어 / 줄당 ≤14셀) + 결과 화면 「마스터」 혼합 폭
+ **카드 게임 종료 후 도박사 대사 일문 수정(PRESENT 재무장)**.

원인(2026-10-10 실측): 카드 모듈은 TurboCD RAM $80-$87 전체를 쓰므로 종료 시 엔진(lba 258, 20섹터)+리소스(lba 278)를
mode-01 로 다시 읽는다(모듈 0x1CA6 파라미터 블록 → 워크 RAM $2300 루틴 → RTS 로 $4000 엔진 벡터 복귀). 씬 770 뱅크($68-$7F)는
그대로지만 엔진 이미지의 PRESENT 초기값 0 이 복원돼 리더가 native 로 간다(TurboNyma 실측 f933 PRESENT=00).
수정: 모듈 블록의 복귀 주소 $3FFF → $C89E 로 바꿔 엔진 창 꼬리($C89F, FF 16B)의 스텁을 거치게 하고, 스텁은 MPR5=$5F 브래킷으로
카드 뱅크 $5F:$AF00 의 재무장 루틴을 호출한 뒤 $4000 으로 간다. 루틴: PRESENT=0 이고 뱅크 $75:$120C 16B 가 씬 770 서명(도박사
대사 원문)과 같을 때만 씬 770 테이블 행 42B → SCRATCH, PRESENT=1, FLAG=0. 부팅 경로($4000 벡터)는 건드리지 않는다.
말풍선 = tools/build_card_balloon_text.py → translation/btrack_b30_card_balloon.json (card@ 행은 b30 메뉴 패치 JSON 에 합쳐 둠).
타일 = tools/cardgame_tiles_kr.py → translation/btrack_b29_cardgame_tiles.json (재생성). 카드 소스 full_v6(= full_v5 와 동일 내용)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b28_hook_build as b28
import build_btrack_b29_hook_build as b29

b28.PATCHES = ROOT / "translation" / "btrack_b30_menu_patches.json"
b28.CARD_SRC_V3 = ROOT / "probes" / "SystemCard3_btrack_full_v6.pce"
b29.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b31.bin"
b29.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b31.cue"
b29.CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b31.pce"
b29.OUT_MANIFEST = ROOT / "translation" / "btrack_b31_hook_manifest.json"

REARM = 0xAF00                 # 뱅크 $5F 안 (게이트 $AE00 뒤)
STUB = 0xC89F                  # 엔진 창 꼬리 (post 루틴 뒤 FF 41B 중 16B)
MODULE_RET = 0xBD5000 + 0x1CBC  # 모듈 종료 파라미터 블록 +0x16/+0x17 (FF 3F = RTS→$4000)
SIG_ISO = 0x19C20C             # 씬 770 뱅크 $75 오프셋 $120C (도박사 대사 원문 16B)
SCENE_LBA = 770
_orig_josa_bank_image = b28.josa_bank_image


def scene_rows(card: bytes) -> bytes:
    import build_btrack_b7_hook_build as b7
    off = b7.CARD_TABLE_OFF
    while card[off] != 0xFF:
        if (card[off] << 8) | card[off + 1] == SCENE_LBA:
            return bytes(card[off + 2:off + 44])
        off += 44
    raise ValueError("씬 770 테이블 항목 없음")


def asm_rearm(sig: bytes, rows: bytes) -> bytes:
    assert len(sig) == 16 and len(rows) == 42
    code = bytes((
        0xAD, 0xFE, 0xC8,              # AF00 LDA PRESENT
        0xD0, 0x2A,                    # AF03 BNE done
        0x43, 0x10, 0x48,              # AF05 TMA4 PHA
        0xA9, 0x75, 0x53, 0x10,        # AF08 LDA #$75 TAM4   (씬 770 뱅크 $75 → $8000)
        0xA2, 0x0F,                    # AF0C LDX #15
        0xBD, 0x0C, 0x92,              # AF0E LDA $920C,X
        0xDD, 0x60, 0xAF,              # AF11 CMP sig,X
        0xD0, 0x16,                    # AF14 BNE nomatch
        0xCA,                          # AF16 DEX
        0x10, 0xF5,                    # AF17 BPL AF0E
        0xA2, 0x29,                    # AF19 LDX #41
        0xBD, 0x80, 0xAF,              # AF1B LDA rows,X
        0x9D, 0xC8, 0xC8,              # AF1E STA SCRATCH,X
        0xCA,                          # AF21 DEX
        0x10, 0xF7,                    # AF22 BPL AF1B
        0xA9, 0x01, 0x8D, 0xFE, 0xC8,  # AF24 LDA #1 STA PRESENT
        0x9C, 0xF9, 0xC8,              # AF29 STZ FLAG
        0x68, 0x53, 0x10,              # AF2C nomatch: PLA TAM4
        0x60,                          # AF2F done: RTS
    ))
    assert len(code) == 0x30
    return code + bytes([0xFF]) * 0x30 + sig + bytes([0xFF]) * 0x10 + rows


def josa_bank_image_b30() -> bytes:
    img = bytearray(_orig_josa_bank_image())
    card = b28.CARD_OUT.read_bytes()
    iso = b28.OUT_BIN.read_bytes()
    sig = bytes(iso[b28.T2 + SIG_ISO:b28.T2 + SIG_ISO + 16])
    blob = asm_rearm(sig, scene_rows(card))
    lo = REARM - 0xA000
    assert set(img[lo:lo + len(blob)]) == {0xFF}, "뱅크 $5F $AF00 자리 비어 있지 않음"
    img[lo:lo + len(blob)] = blob
    return bytes(img)


# 「祈りの盾」 등 포인터 수정 (b10 인플레이스 빌더 결함, 2026-10-10 실측): 4행짜리 armour_names 런(ルナテクター…)의 delta 패턴이
# accessory 테이블의 17~20번 항목(祈りの盾·月の首飾り·樹妖精の手袋·神酒リレイト)과 우연히 일치해 find_pointer_tables 가 그 자리를
# 2번째 1차 테이블로 오인 → self 모드 값으로 덮어써 4항목이 엉뚱한 곳(공백/다른 이름)을 가리켰다. 3,729 항목 디코드 감사에서 이 2×4건만.
# 문자열 자체는 아레나가 제대로 배치했으므로 포인터만 되돌린다. (site, 현재값, 올바른값, 문자열 ISO 오프셋, 인코딩)
ENC = {"기도방패": "88BACAD88CA700", "달목걸이": "8BCC8A6B89B5A900", "나무요정장갑": "B2C988C6894B897BD400", "신주리레이트": "88E588F0ACB9A9AD00",
       "강철대검": "8A878BF589448A6100", "밤블레이드": "8A638EC4B9A9AE00", "전처녀검": "89568A8D89A58A6100"}
PTR_FIX = [  # 뱅크 0x48000 창: 논리 = ISO - 0x3D000 / 뱅크 0x88000 창: 논리 = ISO - 0x7D000
    (0x498D8 + 2 * 17, 0xCE42, 0xCE19, 0x49E19, "기도방패"), (0x498D8 + 2 * 18, 0xCE48, 0xCE35, 0x49E35, "달목걸이"),
    (0x498D8 + 2 * 19, 0xCE2E, 0xD46C, 0x4A46C, "나무요정장갑"), (0x498D8 + 2 * 20, 0xCE3A, 0xC9F3, 0x499F3, "신주리레이트"),
    (0x89A08 + 2 * 17, 0xCF7A, 0xCDC2, 0x89DC2, "기도방패"), (0x89A08 + 2 * 18, 0xCF80, 0xCF6D, 0x89F6D, "달목걸이"),
    (0x89A08 + 2 * 19, 0xCF66, 0xD06D, 0x8A06D, "나무요정장갑"), (0x89A08 + 2 * 20, 0xCF72, 0xD0F7, 0x8A0F7, "신주리레이트"),
    # 같은 결함 2건째: 4행 런 大般若長光…(진짜 테이블 0x899A4)이 12행 weapon 테이블(0x8998A, base CC8F) 앞 3항목을 가짜 테이블(0x89988)로 덮어씀
    (0x8998A, 0xCC8F, 0xD09D, 0x8A09D, "강철대검"), (0x8998C, 0xCC8F, 0xCEF5, 0x89EF5, "밤블레이드"), (0x8998E, 0xCC97, 0xD0A6, 0x8A0A6, "전처녀검"),
]
STUB_CODE = bytes((0x43, 0x20, 0x48, 0xA9, 0x5F, 0x53, 0x20, 0x20, REARM & 0xFF, REARM >> 8, 0x68, 0x53, 0x20, 0x4C, 0x00, 0x40))


def main() -> None:
    b28.josa_bank_image = josa_bank_image_b30
    b29.main()
    import build_btrack_b7_hook_build as b7
    out = bytearray(b29.OUT_BIN.read_bytes())
    so = b7.eng_off(STUB)
    assert set(out[so:so + len(STUB_CODE)]) == {0xFF}, "엔진 스텁 자리($C89F) 비어 있지 않음"
    out[so:so + len(STUB_CODE)] = STUB_CODE
    mo = b28.T2 + MODULE_RET
    assert bytes(out[mo:mo + 2]) == bytes([0xFF, 0x3F]), "모듈 복귀 주소 원본 불일치"
    out[mo:mo + 2] = bytes(((STUB - 1) & 0xFF, (STUB - 1) >> 8))
    # --- 「祈りの盾」 포인터 수정 (b10 인플레이스 빌더 결함): 아레나가 문자열을 0x49E19/0x89DC2 에 두고도 1차 테이블 17번
    #     항목은 0 으로 지워진 자리(CE42/CF7A)를 가리켜 장비 목록에서 이름이 공백이었다(3,729 항목 감사 중 이 2건만).
    for toff, cur, new, soff, name in PTR_FIX:
        assert bytes(out[b28.T2 + toff:b28.T2 + toff + 2]) == cur.to_bytes(2, "little"), f"포인터 원본 불일치 @{toff:07X}"
        e = bytes.fromhex(ENC[name])
        assert out[b28.T2 + soff:b28.T2 + soff + len(e)] == e, f"{name} 문자열 불일치 @{soff:07X}"
        out[b28.T2 + toff:b28.T2 + toff + 2] = new.to_bytes(2, "little")
    b29.OUT_BIN.write_bytes(bytes(out))
    print({"rearm": hex(REARM), "stub": hex(STUB), "module_ret_patch": hex(MODULE_RET), "ptr_fix": len(PTR_FIX)})


if __name__ == "__main__":
    main()
