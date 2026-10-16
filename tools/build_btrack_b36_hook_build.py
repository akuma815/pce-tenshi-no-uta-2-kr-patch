#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B트랙 B36 — b35 와 같은 번역 내용을 **512KB 시스템 카드(뱅크 $00-$3F)** 로 재배치 (ares 호환).

원인 (2026-10-11, 테스트 배포 후 제보 + 사용자 ares 재현 「새 게임 직후 화면 깨짐」):
  ares 의 Super System Card 보드(ares/pce/cartridge/board/super-system-card.cpp)는 카드 ROM 을 뱅크 $00-$3F 만 읽고
  $40 이상은 열린 버스를 돌려준다. b35 의 768KB 카드는 텍스트 풀 $44, 인덱스 $45-$50, 훅 뱅크 $5F(받침 표·조사 문자열·
  호출자 게이트·PRESENT 재무장 코드)를 써서, 첫 대사 무장 때 인덱스/게이트를 열린 버스로 읽어 탈선했다.
  (Mednafen/TurboNyma 는 768KB 를 선형 매핑해서 동작했다.)

해결:
  1) 풀 텍스트 사전 압축 (tools/pool_dict_compress.py): 266KB → ~139KB + 사전 ~16KB. 토큰은 풀 어디에도 없는 바이트 값.
  2) 창 리더의 serve 를 카드 디코더 호출로 교체: `TMA3 PHA / LDA #$3F TAM3 / JSR SERVE / PLA TAM3 / RTS`.
     디코더(뱅크 $3F 오프셋 $1400, MPR3 창 $7400)는 토큰을 펼쳐 한 바이트씩 $2D80 으로 돌려준다(엔진이 보는 바이트열 동일).
     상태: FLAG=1 본문 / FLAG=2 사전 항목 읽는 중, SAVEL/SAVEH($C8F6/7) = 본문 복귀 위치, DBANK($C8F8) = 사전 뱅크.
  3) 훅 뱅크 $5F → $3F (내부 배치 동일: 받침 표 $A000, 조사 $AD00, 게이트 $AE00, 재무장 $AF00).
     상위 4KB = 토큰 표(KIND/DBANK/DLO/DHI 각 256B, $7000-$73FF) + 디코더 + 사전 일부.
  4) 사전 그룹은 $3E 부터 아래로, 텍스트·인덱스는 $20 부터 위로. 카드 512KB.
출력: *_btrack_b36.bin/.cue + probes/SystemCard3_btrack_b36.pce
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b9_hook_build as b9
import build_btrack_b28_hook_build as b28
import build_btrack_b29_hook_build as b29
import build_btrack_b35_hook_build as b35
import pool_dict_compress as pdc
from build_btrack_b7_hook_build import FLAG, TBANK, CURL, CURH, PRESENT, SCRATCH, CARD_TABLE_OFF, ENTRY_LEN
Asm = b9.Asm

HOOK_BANK = 0x3F
CARD_SIZE = 512 * 1024
SAVEL, SAVEH, DBANK = 0xC8F6, 0xC8F7, 0xC8F8      # 창 끝 FF 스크래치 (b7 이래 미사용 3B)
TAB_OFF = 0x1000                                   # 뱅크 $3F 안 토큰 표 (MPR3 $7000)
KIND_T, DBANK_T, DLO_T, DHI_T = (0x6000 + TAB_OFF + i * 0x100 for i in range(4))
SERVE_OFF = 0x1400
SERVE = 0x6000 + SERVE_OFF                         # $7400
DICT_LO_OFF = 0x1500                               # 뱅크 $3F 의 사전 영역 시작

b29.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b36.bin"
b29.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b36.cue"
b29.CARD_OUT = ROOT / "probes" / "SystemCard3_btrack_b36.pce"
b29.OUT_MANIFEST = ROOT / "translation" / "btrack_b36_hook_manifest.json"
OUT_DICT = ROOT / "translation" / "btrack_b36_pool_dict.json"

_orig_payload = b9.payload
_COMP: dict[str, str] = {}


def payload_b36(lba: int):
    return [{**r, "encoded_hex": _COMP[r["encoded_hex"]], "encoded_length": len(_COMP[r["encoded_hex"]]) // 2}
            for r in _orig_payload(lba)]


def asm_reader_v36(origin: int) -> Asm:
    """v3m 와 같은 앞부분(무장 판정·armchk) + serve 는 카드 디코더 호출. 길이는 v3m(86B)에 맞춰 FF 로 채운다
    (post 진입점 = reader + 86 을 b28 트램펄린이 상수로 쓴다)."""
    a = Asm(origin)
    a.emit(0xA5, 0x55)
    a.branch(0xD0, "native")
    a.emit(0xAD, FLAG & 0xFF, FLAG >> 8)
    a.branch(0xD0, "serve")
    a.emit(0xAD, PRESENT & 0xFF, PRESENT >> 8)
    a.branch(0xF0, "native")
    a.emit(0x43, 0x20, 0x48)                             # TMA5 PHA
    a.emit(0xAD, (SCRATCH + 4) & 0xFF, (SCRATCH + 4) >> 8)
    a.emit(0x53, 0x20)                                   # MPR5 = IBANK
    a.emit(0x43, 0x08, 0x48)                             # TMA3 PHA
    a.emit(0xA9, 0x1F, 0x53, 0x08)                       # MPR3 = $1F (armchk)
    a.jsr(b9.ARMCHK_EXEC)
    a.emit(0x68, 0x53, 0x08)
    a.emit(0x68, 0x53, 0x20)
    a.branch(0xB0, "native")
    a.label("serve")
    a.emit(0x43, 0x08, 0x48)                             # TMA3 PHA
    a.emit(0xA9, HOOK_BANK, 0x53, 0x08)                  # MPR3 = $3F (디코더)
    a.jsr(SERVE)
    a.emit(0x68, 0x53, 0x08)                             # PLA TAM3 (carry 보존)
    a.emit(0x60)
    a.label("native")
    a.emit(0x38, 0x60)
    assert len(a.buf) <= b28.READER_V3M_LEN
    a.emit(*([0xFF] * (b28.READER_V3M_LEN - len(a.buf))))
    return a


def asm_serve() -> bytes:
    """카드 serve 디코더 (MPR3=$3F, $7400). 반환: C=0 + $2D80 = 바이트 / C=1 = 레코드 끝(FLAG=0, native).
    X·Y 보존, zp $00/$01 사용(원 serve 와 같음)."""
    a = Asm(SERVE)
    a.emit(0xDA, 0x5A)                                   # PHX PHY
    a.emit(0x43, 0x20, 0x48)                             # TMA5 PHA
    a.label("again")
    a.emit(0xAD, FLAG & 0xFF, FLAG >> 8, 0xC9, 0x02)     # LDA FLAG CMP #2
    a.branch(0xF0, "dict")
    a.emit(0xAD, TBANK & 0xFF, TBANK >> 8, 0x53, 0x20)   # MPR5 = TBANK
    a.jsr("rdcur")
    a.branch(0xF0, "nul")
    a.emit(0xAA)                                         # TAX
    a.emit(0xBD, KIND_T & 0xFF, KIND_T >> 8)             # LDA KIND,X
    a.branch(0xD0, "tok")
    a.jsr("inc1")
    a.emit(0x8A)                                         # TXA
    a.label("out")
    a.emit(0x8D, 0x80, 0x2D)                             # STA $2D80
    a.emit(0x68, 0x53, 0x20)                             # PLA TAM5
    a.emit(0x7A, 0xFA, 0x18, 0x60)                       # PLY PLX CLC RTS
    a.label("nul")
    a.emit(0x68, 0x53, 0x20)                             # PLA TAM5
    a.emit(0x9C, FLAG & 0xFF, FLAG >> 8)                 # STZ FLAG
    a.emit(0x7A, 0xFA, 0x38, 0x60)                       # PLY PLX SEC RTS
    a.label("tok")
    a.emit(0xC9, 0x01)
    a.branch(0xF0, "t1")
    a.emit(0xA0, 0x01, 0xB1, 0x00, 0xA8)                 # LDY #1 LDA ($00),Y TAY  (그룹 색인)
    a.jsr("inc1")
    a.jsr("inc1")
    a.jsr("save")
    a.emit(0xBD, DBANK_T & 0xFF, DBANK_T >> 8)           # LDA DBANK_T,X
    a.emit(0x8D, DBANK & 0xFF, DBANK >> 8, 0x53, 0x20)   # STA DBANK TAM5
    a.emit(0x64, 0x00)                                   # STZ $00
    a.emit(0xBD, DHI_T & 0xFF, DHI_T >> 8, 0x85, 0x01)   # LDA DHI_T,X STA $01 (그룹 lo 표 페이지)
    a.emit(0xB1, 0x00, 0x48)                             # LDA ($00),Y PHA
    a.emit(0xE6, 0x01)                                   # INC $01 (hi 표)
    a.emit(0xB1, 0x00, 0x8D, CURH & 0xFF, CURH >> 8)     # LDA ($00),Y STA CURH
    a.emit(0x68, 0x8D, CURL & 0xFF, CURL >> 8)           # PLA STA CURL
    a.branch(0x80, "arm")
    a.label("t1")
    a.jsr("inc1")
    a.jsr("save")
    a.emit(0xBD, DBANK_T & 0xFF, DBANK_T >> 8, 0x8D, DBANK & 0xFF, DBANK >> 8)
    a.emit(0xBD, DLO_T & 0xFF, DLO_T >> 8, 0x8D, CURL & 0xFF, CURL >> 8)
    a.emit(0xBD, DHI_T & 0xFF, DHI_T >> 8, 0x8D, CURH & 0xFF, CURH >> 8)
    a.label("arm")
    a.emit(0xA9, 0x02, 0x8D, FLAG & 0xFF, FLAG >> 8)     # FLAG = 2 (사전)
    a.label("dict")
    a.emit(0xAD, DBANK & 0xFF, DBANK >> 8, 0x53, 0x20)   # MPR5 = DBANK
    a.jsr("rdcur")
    a.branch(0xF0, "dend")
    a.jsr("inc1")
    a.branch(0x80, "out")
    a.label("dend")
    a.emit(0xAD, SAVEL & 0xFF, SAVEL >> 8, 0x8D, CURL & 0xFF, CURL >> 8)
    a.emit(0xAD, SAVEH & 0xFF, SAVEH >> 8, 0x8D, CURH & 0xFF, CURH >> 8)
    a.emit(0xA9, 0x01, 0x8D, FLAG & 0xFF, FLAG >> 8)     # FLAG = 1 (본문 복귀)
    a.jmp("again")
    a.label("rdcur")
    a.emit(0xAD, CURL & 0xFF, CURL >> 8, 0x85, 0x00)
    a.emit(0xAD, CURH & 0xFF, CURH >> 8, 0x85, 0x01)
    a.emit(0xB2, 0x00, 0x60)                             # LDA ($00) RTS  (Z = 바이트==0)
    a.label("inc1")
    a.emit(0xEE, CURL & 0xFF, CURL >> 8)
    a.branch(0xD0, "i1r")
    a.emit(0xEE, CURH & 0xFF, CURH >> 8)
    a.label("i1r")
    a.emit(0x60)
    a.label("save")
    a.emit(0xAD, CURL & 0xFF, CURL >> 8, 0x8D, SAVEL & 0xFF, SAVEL >> 8)
    a.emit(0xAD, CURH & 0xFF, CURH >> 8, 0x8D, SAVEH & 0xFF, SAVEH >> 8)
    a.emit(0x60)
    code = a.resolve()
    assert len(code) <= DICT_LO_OFF - SERVE_OFF, f"serve {len(code)}B"
    return code


def layout_dict(res):
    """사전 배치. 반환 (뱅크→{오프셋: bytes}, 표 4개, 사전이 쓰는 최저 뱅크)."""
    regions = [[HOOK_BANK, DICT_LO_OFF, 0x2000]]          # [뱅크, 커서, 끝]
    nxt = HOOK_BANK - 1
    writes: dict[int, dict[int, bytes]] = {}
    kind, dbank, dlo, dhi = (bytearray(256) for _ in range(4))

    def alloc(size, align):
        nonlocal nxt
        for r in regions:
            st = (r[1] + align - 1) & -align
            if st + size <= r[2]:
                r[1] = st + size
                return r[0], st
        regions.append([nxt, 0, 0x2000]); nxt -= 1
        return alloc(size, align)

    for p, ents in sorted(res["groups"].items(), key=lambda kv: -sum(len(e) + 1 for e in kv[1])):
        size = 512 + sum(len(e) + 1 for e in ents)
        bank, st = alloc(size, 0x100)
        lo, hi, blob = bytearray(256), bytearray(256), bytearray()
        for i, e in enumerate(ents, start=1):
            addr = 0xA000 + st + 512 + len(blob)
            lo[i], hi[i] = addr & 0xFF, addr >> 8
            blob += e + b"\x00"
        writes.setdefault(bank, {})[st] = bytes(lo) + bytes(hi) + bytes(blob)
        kind[p], dbank[p], dhi[p] = 2, bank, 0xA0 + (st >> 8)
    for v, e in sorted(res["tokens1"].items()):
        bank, st = alloc(len(e) + 1, 1)
        writes.setdefault(bank, {})[st] = e + b"\x00"
        addr = 0xA000 + st
        kind[v], dbank[v], dlo[v], dhi[v] = 1, bank, addr & 0xFF, addr >> 8
    return writes, (bytes(kind), bytes(dbank), bytes(dlo), bytes(dhi)), min(r[0] for r in regions)


def verify_card(card: bytes, tabs) -> int:
    """씬 테이블 → 인덱스 → (뱅크, 주소) → 카드 표로 디코드한 바이트열이 원 레코드(압축 전)와 같은지 전수 확인."""
    kind, dbank, dlo, dhi = tabs
    def rd(bank, addr):
        assert 0x20 <= bank <= 0x3F and 0xA000 <= addr < 0xC000, (hex(bank), hex(addr))
        return card[bank * 0x2000 + addr - 0xA000]
    def decode(bank, addr):
        out = bytearray()
        while True:
            b = rd(bank, addr)
            if b == 0:
                return bytes(out)
            if kind[b] == 0:
                out.append(b); addr += 1; continue
            if kind[b] == 1:
                db, da = dbank[b], dlo[b] | dhi[b] << 8; addr += 1
            else:
                i = rd(bank, addr + 1); addr += 2
                db, pg = dbank[b], dhi[b] << 8
                da = rd(db, pg + i) | rd(db, pg + 0x100 + i) << 8
            while (c := rd(db, da)) != 0:
                assert kind[c] == 0 or True
                out.append(c); da += 1
    n, off = 0, CARD_TABLE_OFF
    while card[off] != 0xFF:
        lba = card[off] << 8 | card[off + 1]
        ibank, ibase = card[off + 2 + 4], card[off + 2 + 5] << 8
        assert ibank <= 0x3F
        want = {int.from_bytes(bytes.fromhex(r["source_key_u24le"]), "little"): bytes.fromhex(r["encoded_hex"])[:-1]
                for r in _orig_payload(lba)}
        assert rd(ibank, ibase) == b9.INDEX_MAGIC[0] and rd(ibank, ibase + 1) == b9.INDEX_MAGIC[1]
        got = 0
        for kb in range(24):
            p = rd(ibank, ibase + 2 + kb * 2) | rd(ibank, ibase + 3 + kb * 2) << 8
            while rd(ibank, p) != 0xFF:
                key = kb << 13 | rd(ibank, p) << 8 | rd(ibank, p + 1)
                tb, ta = rd(ibank, p + 2), rd(ibank, p + 3) | rd(ibank, p + 4) << 8
                assert decode(tb, ta) == want[key], f"scene {lba} key {key:06X} 디코드 불일치"
                got += 1; p += 7
        assert got == len(want), f"scene {lba}: {got} != {len(want)}"
        n += got; off += ENTRY_LEN
    return n


def main() -> None:
    # 1) 사전 압축
    recs = [r["encoded_hex"] for lba in b9.SCENES_B9 for r in _orig_payload(lba)]
    res = pdc.build(recs)
    _COMP.update(res["comp"])
    writes, tabs, dict_low = layout_dict(res)
    assert dict_low > 0x2A, f"사전이 너무 많은 뱅크를 씀 ({dict_low:02X})"
    # 2) 체인 설정
    b9.CARD_SIZE = CARD_SIZE
    b9.EXT_BANKS = list(range(0x20, dict_low))
    b9.payload = payload_b36
    b28._ORIG_READER_V3M = asm_reader_v36
    b28.JOSA_BANK = HOOK_BANK
    b35.STUB_CODE = bytes((0x43, 0x20, 0x48, 0xA9, HOOK_BANK, 0x53, 0x20, 0x20, b35.REARM & 0xFF, b35.REARM >> 8,
                           0x68, 0x53, 0x20, 0x4C, 0x00, 0x40))
    b35.main()
    # 3) 카드 후처리: 뱅크 $3F 상위(표·디코더) + 사전
    card = bytearray(b29.CARD_OUT.read_bytes())
    assert len(card) == CARD_SIZE, len(card)
    hb = HOOK_BANK * 0x2000
    assert set(card[hb + TAB_OFF:hb + 0x2000]) == {0xFF}, "뱅크 $3F 상위 4KB 가 비어 있지 않음"
    for i, t in enumerate(tabs):
        card[hb + TAB_OFF + i * 0x100:hb + TAB_OFF + (i + 1) * 0x100] = t
    serve = asm_serve()
    card[hb + SERVE_OFF:hb + SERVE_OFF + len(serve)] = serve
    for bank, items in writes.items():
        for st, data in items.items():
            o = bank * 0x2000 + st
            assert set(card[o:o + len(data)]) == {0xFF}, f"사전 자리 비어 있지 않음 {bank:02X}:{st:04X}"
            card[o:o + len(data)] = data
    b29.CARD_OUT.write_bytes(bytes(card))
    n = verify_card(bytes(card), tabs)
    # 뱅크 사용 요약
    m = json.loads(b28.OUT_MANIFEST.read_text(encoding="utf-8")) if b28.OUT_MANIFEST.exists() else {}
    stage = json.loads((ROOT / "translation" / "btrack_b28_b9stage_manifest.json").read_text(encoding="utf-8"))
    OUT_DICT.write_text(json.dumps({
        "format": "BTRACK-B36-POOL-DICT", "hook_bank": f"{HOOK_BANK:02X}", "dict_banks_from": f"{dict_low:02X}",
        "tokens1": {f"{v:02X}": e.hex().upper() for v, e in res["tokens1"].items()},
        "groups": {f"{p:02X}": [e.hex().upper() for e in g] for p, g in res["groups"].items()},
        "pool": stage["pool"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"status": "B36_OK", "card_size": len(card), "verified_entries": n,
                      "text_bytes": stage["pool"]["text_bytes"], "text_banks": stage["pool"]["text_bank_list"][-1],
                      "index_banks": stage["pool"]["index_bank_list"], "dict_low": f"{dict_low:02X}",
                      "serve_bytes": len(serve)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
