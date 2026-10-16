#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""시스템 카드 폰트 압축 + BIOS EX_GETFNT 패치 (256KB 카드 1단계, 2026-10-11).

원본 EX_GETFNT($E060 → $F124): SJIS → 글리프 번호 i($F8/$F9, $F1E3) → $F151-$F1A3 에서 주소 계산
(16x16: 0x10000 + i*32 / 12x12: 0x30000 + i*18) → 창 매핑 → 16x16 은 32B 복사, 12x12 는 18B→32B 확장($F2CC).
패치:
  · $F151: `JSR NEWADDR / JMP $F1A5` — NEWADDR(뱅크 0 빈칸 $FEC4) 가 $EC/$ED(창 기준)/$EE(뱅크) 를 채우고
    C=1(12x12 확장) / C=0(16x16 복사) 를 돌려준다.
  · $F1B6: `BBS0 $FF,+12` → `BCS +13 / NOP` — 확장 여부를 캐리로. 호출자의 $FF(모드 인자)는 건드리지 않는다.
NEWADDR:
  · 12x12: 사용표(비트맵, i 의 비트) 가 1 이면 압축 번호 j = 누적표[i>>3] + popcount(비트맵[i>>3] & 아래비트) →
    BASE12 + j*18. 0 이면 표시 글리프(□, j = BOX).
  · 16x16: 말풍선 목록(LIST16, i 의 정렬 목록)에서 찾으면 BASE16 + k*32, 없으면 12x12 경로로.
  · 표들은 TAB 뱅크(페이지 정렬)를 EX_GETFNT 가 이미 저장해 둔 창의 첫 MPR 에 잠시 매핑해서 읽는다.
  · (2026-10-12 b58) 크레딧 한자: 16x16 요청이 말풍선 목록에 없으면 LISTK(표 $800/$900 페이지)를 찾아, 있으면 원본 BIOS 12x12 한자 글리프
    (12x12 저장소의 □ 뒤, j = BOXJ+1+k)를 12x12 확장으로 준다. 비주얼 씬 스태프 크레딧(16x16 모드, 원문 일본어 유지 — 사용자 결정)의
    한자 코드가 한글 배정으로 재사용돼 다른 글자로 나오던 문제. 검색 코드는 EX_GETFNT 의 죽은 원래 주소 계산부 $F157-$F1A4(78B)에 둔다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import analyze_system_card_font_slots as fs
from build_btrack_b7_hook_build import Asm

ASSIGN = ROOT / "translation" / "btrack_slot_assignment.json"
BALLOON = ROOT / "translation" / "btrack_b30_card_balloon.json"
FONT16 = r"G:\Downloads\Korean Traslate Project\Font\Galmuri14.ttf"   # 원 픽셀 크기 15px (14 로 렌더하면 획이 빠짐)
FONT16_PX = 15

N_IDX = 3640                       # 12x12 슬롯 수 (0x30000 + 3640*18 = 0x3FFF0)
BASE12 = 0x30000
OLD16, OLD12 = 0x10000, 0x30000
NEWADDR = 0xFEC4                   # 뱅크 0 FF 런 0x1EC4..0x1FDB (280B, CDL cold)
NEWADDR_END = 0xFFDC
PAGE_BMP, PAGE_CUMLO, PAGE_CUMHI, PAGE_L16LO, PAGE_L16HI = 0, 2, 4, 6, 7
PROTECT_FROM = 0x3F054             # 씬 테이블·armchk·조사 코드·BIOS 후행 데이터 (건드리지 않음)
PAGE_LKLO, PAGE_LKHI = 8, 9        # (b58) 크레딧 한자 목록 LISTK
KSEARCH, KSEARCH_END = 0xF157, 0xF1A5   # EX_GETFNT 원래 주소 계산부 — $F151 패치 뒤 도달 불가(참조 0, 2026-10-12 확인)
TAB_SIZE = 0xA00
ORIG_CARD = ROOT / "probes" / "SystemCard3_original_noheader.pce"


def bank0(addr: int) -> int:
    assert 0xE000 <= addr < 0x10000
    return addr - 0xE000


def render16(ch: str) -> bytes:
    f = ImageFont.truetype(FONT16, FONT16_PX)
    im = Image.new("L", (16, 16), 0)
    d = ImageDraw.Draw(im)
    bb = f.getbbox(ch)
    d.text(((16 - (bb[2] - bb[0])) // 2 - bb[0], (16 - (bb[3] - bb[1])) // 2 - bb[1]), ch, font=f, fill=255)
    px = im.load()
    assert {px[x, y] for x in range(16) for y in range(16)} <= {0, 255}, f"{ch}: 계조 발생 — 렌더 크기 확인"
    out = bytearray()
    for y in range(16):
        v = sum(0x8000 >> x for x in range(16) if px[x, y])
        out += bytes((v >> 8, v & 0xFF))
    return bytes(out)


def box12() -> bytes:
    rows = [0] * 12
    for y in range(1, 11):
        rows[y] = 0x7FE if y in (1, 10) else 0x402
    out = bytearray()
    for y in range(0, 12, 2):
        r0, r1 = rows[y], rows[y + 1]
        out += bytes((r0 >> 4, ((r0 & 0xF) << 4) | (r1 >> 8), r1 & 0xFF))
    return bytes(out)


def codes_in(hexs) -> set[int]:
    out = set()
    for h in hexs:
        d = bytes.fromhex(h); i = 0
        while i < len(d):
            if 0x81 <= d[i] <= 0x9F or 0xE0 <= d[i] <= 0xEF:
                out.add(d[i] << 8 | d[i + 1]); i += 2
            else:
                i += 1
    return out


def asm_newaddr(tab_bank: int, base16: int, n16: int, boxj: int, nk: int = 0):
    a = Asm(NEWADDR)
    # 표 뱅크를 창 첫 MPR 에 (EX_GETFNT 가 이미 원래 값을 $22B8-$22BB 에 저장해 둠)
    a.emit(0xA9, tab_bank)
    a.emit(0xFF, 0xFC); a.fixups.append((len(a.buf), "rel", "w5")); a.emit(0x00)   # BBS7 $FC,w5
    a.emit(0x53, 0x08)                                   # TAM #$08 (MPR3, 창 $6000)
    a.branch(0x80, "wd")
    a.label("w5")
    a.emit(0x53, 0x20)                                   # TAM #$20 (MPR5, 창 $A000)
    a.label("wd")
    a.emit(0x64, 0xEC)                                   # STZ $EC
    # 범위: i < $0F00 (비트맵 512B 중 N_IDX 이후 비트는 0 → □)
    a.emit(0xA5, 0xF9, 0xC9, 0x0F)
    a.branch(0xB0, "box")
    a.emit(0x0F, 0xFF); a.fixups.append((len(a.buf), "rel", "s16")); a.emit(0x00)  # BBR0 $FF,s16 (16x16 요청)
    a.jmp("do12")
    # --- 16x16: LIST16 선형 검색 ---
    a.label("s16")
    a.emit(0xA5, 0xFC, 0x18, 0x69, PAGE_L16LO, 0x85, 0xED)   # $ED = 창 + L16LO 페이지
    a.emit(0xC2)                                         # CLY
    a.label("l16")
    a.emit(0xC0, n16)                                    # CPY #n16
    a.branch(0xB0, "kjump" if nk else "do12")            # 목록에 없음 → (크레딧 한자 목록) → 12x12 경로
    a.emit(0xB1, 0xEC, 0xC5, 0xF8)                       # LDA ($EC),Y / CMP $F8
    a.branch(0xD0, "n16")
    a.emit(0xE6, 0xED, 0xB1, 0xEC, 0xC6, 0xED)           # INC $ED / LDA ($EC),Y / DEC $ED
    a.emit(0xC5, 0xF9)
    a.branch(0xF0, "f16")
    a.label("n16")
    a.emit(0xC8)                                         # INY
    a.branch(0x80, "l16")
    a.label("f16")                                       # 주소 = base16 + Y*32
    a.emit(0x98, 0x85, 0xEC, 0x64, 0xED)                 # TYA STA $EC / STZ $ED
    a.emit(0xA2, 0x05)
    a.label("sh16")
    a.emit(0x06, 0xEC, 0x26, 0xED, 0xCA)                 # ASL $EC ROL $ED DEX
    a.branch(0xD0, "sh16")
    a.emit(0xA9, base16 & 0xFF, 0xA0, (base16 >> 8) & 0xFF, 0xA2, base16 >> 16)   # A/Y/X = base 하/중/상
    a.emit(0x20); a.fixups.append((len(a.buf), "abs", "add24")); a.emit(0, 0)
    a.emit(0x18, 0x60)                                   # CLC RTS (16x16 복사)
    if nk:                                               # (b58) 말풍선 목록에 없음 → 크레딧 한자 목록 (분기 거리 때문에 여기)
        a.label("kjump")
        a.jmp(KSEARCH)
    # --- 12x12 ---
    a.label("box")
    a.emit(0xA9, boxj & 0xFF, 0x85, 0xEC, 0xA9, boxj >> 8, 0x85, 0xED)
    a.jmp("mul18")
    a.label("do12")
    # 바이트 번호 b = i>>3 (16비트) → $EC(하) / $ED(창 + 페이지 + 상)
    a.emit(0xA5, 0xF9, 0x85, 0xED, 0xA5, 0xF8)           # $ED=i_hi, A=i_lo
    a.emit(0x46, 0xED, 0x6A, 0x46, 0xED, 0x6A, 0x46, 0xED, 0x6A)   # (i_hi:A) >>= 3
    a.emit(0x85, 0xEC)
    a.emit(0xA5, 0xED, 0x18, 0x65, 0xFC, 0x85, 0xED)     # $ED += 창 (PAGE_BMP = 0)
    a.emit(0xA5, 0xF8, 0x29, 0x07, 0xAA)                 # X = i & 7
    a.emit(0xB2, 0xEC)                                   # LDA (bmp)
    a.emit(0x3D); a.fixups.append((len(a.buf), "abs", "bitmask")); a.emit(0, 0)   # AND bitmask,X
    a.branch(0xF0, "box")
    a.emit(0xBD); a.fixups.append((len(a.buf), "abs", "bitmask")); a.emit(0, 0)   # LDA bitmask,X
    a.emit(0x3A, 0x32, 0xEC)                             # DEC A / AND (bmp)  → 아래 비트만
    a.emit(0xC2)                                         # CLY (popcount)
    a.label("pc")
    a.branch(0xF0, "pcd")
    a.emit(0x4A)                                         # LSR A
    a.branch(0x90, "pc0")
    a.emit(0xC8)                                         # INY
    a.label("pc0")
    a.emit(0xC9, 0x00)
    a.branch(0x80, "pc")
    a.label("pcd")
    a.emit(0x98, 0x48)                                   # TYA PHA (popcount)
    a.emit(0xA5, 0xED, 0x18, 0x69, PAGE_CUMLO, 0x85, 0xED)
    a.emit(0xB2, 0xEC, 0xAA)                             # X = cum_lo
    a.emit(0xA5, 0xED, 0x18, 0x69, PAGE_CUMHI - PAGE_CUMLO, 0x85, 0xED)
    a.emit(0xB2, 0xEC, 0x85, 0xED)                       # $ED = cum_hi
    a.emit(0x68, 0x86, 0xEC, 0x18, 0x65, 0xEC, 0x85, 0xEC)   # PLA / STX $EC / CLC ADC $EC / STA $EC
    a.branch(0x90, "mul18")
    a.emit(0xE6, 0xED)
    a.label("mul18")                                     # ($ED:$EC) = j → j*18 = j*16 + j*2
    a.emit(0x06, 0xEC, 0x26, 0xED)                       # j*2
    a.emit(0xA5, 0xEC, 0x48, 0xA5, 0xED, 0x48)           # 보관
    a.emit(0x06, 0xEC, 0x26, 0xED, 0x06, 0xEC, 0x26, 0xED, 0x06, 0xEC, 0x26, 0xED)   # j*16
    a.emit(0x68, 0xA8, 0x68)                             # Y = (j*2)_hi, A = (j*2)_lo
    a.emit(0x18, 0x65, 0xEC, 0x85, 0xEC, 0x98, 0x65, 0xED, 0x85, 0xED)
    a.emit(0xA9, BASE12 & 0xFF, 0xA0, (BASE12 >> 8) & 0xFF, 0xA2, BASE12 >> 16)
    a.emit(0x20); a.fixups.append((len(a.buf), "abs", "add24")); a.emit(0, 0)
    a.emit(0x38, 0x60)                                   # SEC RTS (12x12 확장)
    # add24: ($ED:$EC) + (X:Y:A) → 뱅크 $EE, $ED = 창 + (주소>>8 & $1F), $EC
    a.label("add24")
    a.emit(0x18, 0x65, 0xEC, 0x85, 0xEC)
    a.emit(0x98, 0x65, 0xED, 0x85, 0xED)
    a.emit(0x8A, 0x69, 0x00)                             # A = 상위 바이트 (+캐리)
    a.emit(0x0A, 0x0A, 0x0A, 0x85, 0xEE)                 # 상위*8
    a.emit(0xA5, 0xED, 0x4A, 0x4A, 0x4A, 0x4A, 0x4A, 0x05, 0xEE, 0x85, 0xEE)   # 뱅크 = 상위*8 | ($ED>>5)
    a.emit(0xA5, 0xED, 0x29, 0x1F, 0x18, 0x65, 0xFC, 0x85, 0xED)
    a.emit(0x60)
    a.label("bitmask")
    a.emit(*[1 << k for k in range(8)])
    code = a.resolve()
    assert NEWADDR + len(code) <= NEWADDR_END, f"NEWADDR {len(code)}B > {NEWADDR_END - NEWADDR}"
    return code, dict(a.labels)


def asm_ksearch(nk: int, kbase_j: int, labels: dict) -> bytes:
    """(b58) LISTK 선형 검색. 진입 상태 = NEWADDR s16 경로(표 뱅크 매핑됨, $EC=0, $F8/$F9=글리프 번호 i).
    찾으면 ($ED:$EC) = kbase_j + k → NEWADDR 의 mul18(12x12 확장, SEC), 없으면 do12."""
    assert 0 < nk < 256
    a = Asm(KSEARCH)
    a.emit(0xA5, 0xFC, 0x18, 0x69, PAGE_LKLO, 0x85, 0xED)   # $ED = 창 + LKLO 페이지
    a.emit(0xC2)                                         # CLY
    a.label("kl")
    a.emit(0xC0, nk)                                     # CPY #nk
    a.branch(0xB0, "kfail")
    a.emit(0xB1, 0xEC, 0xC5, 0xF8)                       # LDA ($EC),Y / CMP $F8
    a.branch(0xD0, "kn")
    a.emit(0xE6, 0xED, 0xB1, 0xEC, 0xC6, 0xED)           # INC $ED / LDA ($EC),Y / DEC $ED
    a.emit(0xC5, 0xF9)
    a.branch(0xF0, "kf")
    a.label("kn")
    a.emit(0xC8)                                         # INY
    a.branch(0x80, "kl")
    a.label("kf")                                        # j = kbase_j + Y
    a.emit(0x98, 0x18, 0x69, kbase_j & 0xFF, 0x85, 0xEC)
    a.emit(0xA9, kbase_j >> 8, 0x69, 0x00, 0x85, 0xED)
    a.jmp(labels["mul18"])
    a.label("kfail")
    a.jmp(labels["do12"])
    code = a.resolve()
    assert KSEARCH + len(code) <= KSEARCH_END, f"KSEARCH {len(code)}B > {KSEARCH_END - KSEARCH}"
    return code


def build(card_in: bytes, extra_text_hex: list[str], credit_codes=None) -> tuple[bytes, dict]:
    card = bytearray(card_in)
    assert len(card) >= 256 * 1024
    asg = json.loads(ASSIGN.read_text(encoding="utf-8"))["assignment"]
    rev = {int(v["sjis"], 16): ch for ch, v in asg.items()}
    gi = lambda code: fs.glyph_index((code >> 8, code & 0xFF), card_in)
    # 12x12 유지 목록: 비한자(행 $81-$87) + 배정 한글 + 최종 텍스트에 실제로 나오는 코드
    keep = set()
    for lead in range(0x81, 0x88):
        for t in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            i = gi(lead << 8 | t)
            if i is not None:
                keep.add(i)
    keep |= {gi(c) for c in rev}
    keep |= {gi(c) for c in codes_in(extra_text_hex) if gi(c) is not None}
    # (b59) 크레딧 글자 중 한글 배정이 없는 번호(아무 텍스트도 안 쓰던 한자 — 지금은 □)는 일반 12x12 유지 목록에 넣는다:
    #   크레딧 직함·제목은 12x12 모드(명령 01 01 …)라 LISTK(16x16 전용)로는 못 고친다(사용자 화면 「＜□□＞」). 한글 배정 번호만 LISTK.
    keep |= {gi(c) for c in (credit_codes or ()) if gi(c) is not None}
    keep = sorted(i for i in keep if i is not None and i < N_IDX)
    jmap = {i: j for j, i in enumerate(keep)}
    boxj = len(keep)
    store12 = b"".join(bytes(card_in[OLD12 + i * 18:OLD12 + i * 18 + 18]) for i in keep) + box12()
    # 16x16: 말풍선 문자
    bal = json.loads(BALLOON.read_text(encoding="utf-8"))
    c16 = sorted(codes_in([p["new_hex"] for p in bal["patches"]]), key=gi)
    l16 = [gi(c) for c in c16]
    # (b58) 크레딧 한자: 16x16 요청 때 12x12 경로가 원본과 다른 글리프(한글 배정·□)를 주는 번호만 원본 12x12 글리프로
    orig = ORIG_CARD.read_bytes()
    lk = []
    for c in sorted(set(credit_codes or ())):
        i = gi(c)
        if i is None or i in l16 or i in lk or i >= N_IDX:
            continue
        og = bytes(orig[OLD12 + i * 18:OLD12 + i * 18 + 18])
        cur = bytes(card_in[OLD12 + i * 18:OLD12 + i * 18 + 18]) if i in jmap else None
        if cur != og:
            lk.append(i)
    kbase_j = boxj + 1
    store12 += b"".join(bytes(orig[OLD12 + i * 18:OLD12 + i * 18 + 18]) for i in lk)
    base16 = (BASE12 + len(store12) + 0xFF) & ~0xFF
    assert len(l16) == len(set(l16)) and len(l16) < 256
    store16 = b"".join(render16(rev[c]) if c in rev else bytes(card_in[OLD16 + gi(c) * 32:OLD16 + gi(c) * 32 + 32]) for c in c16)
    tab_off = (base16 + len(store16) + 0x1FFF) & ~0x1FFF            # 표 = 다음 뱅크 머리
    tab_size = TAB_SIZE if lk else 0x800                            # LISTK 페이지는 크레딧 한자가 있을 때만(없으면 b57 이전과 같은 배치)
    tab_bank = tab_off // 0x2000
    assert tab_off + tab_size <= PROTECT_FROM, f"폰트·표가 보호 영역 침범 {tab_off + tab_size:#x}"
    # 표
    bmp = bytearray((N_IDX + 7) // 8)
    for i in keep:
        bmp[i >> 3] |= 1 << (i & 7)
    cum, run = [], 0
    for b in range(len(bmp)):
        cum.append(run); run += bin(bmp[b]).count("1")
    tab = bytearray(b"\xFF" * TAB_SIZE)
    tab[0:0x200] = bytes(0x200)                          # 비트맵 512B (N_IDX 이후 = 0)
    tab[0:len(bmp)] = bmp
    tab[0x200:0x200 + len(cum)] = bytes(c & 0xFF for c in cum)
    tab[0x400:0x400 + len(cum)] = bytes(c >> 8 for c in cum)
    tab[0x600:0x600 + len(l16)] = bytes(i & 0xFF for i in l16)
    tab[0x700:0x700 + len(l16)] = bytes(i >> 8 for i in l16)
    tab[PAGE_LKLO * 0x100:PAGE_LKLO * 0x100 + len(lk)] = bytes(i & 0xFF for i in lk)
    tab[PAGE_LKHI * 0x100:PAGE_LKHI * 0x100 + len(lk)] = bytes(i >> 8 for i in lk)
    # 카드 쓰기: 옛 16x16 영역과 옛 12x12 영역(보호 구역 앞까지)을 FF 로 지운 뒤 새 배치
    card[OLD16:0x2C000] = b"\xFF" * (0x2C000 - OLD16)
    card[OLD12:PROTECT_FROM] = b"\xFF" * (PROTECT_FROM - OLD12)
    card[BASE12:BASE12 + len(store12)] = store12
    card[base16:base16 + len(store16)] = store16
    card[tab_off:tab_off + len(tab)] = tab
    # BIOS 패치
    code, labels = asm_newaddr(tab_bank, base16, len(l16), boxj, len(lk))
    if lk:
        kcode = asm_ksearch(len(lk), kbase_j, labels)
        ko = bank0(KSEARCH)
        assert bytes(card[ko:ko + 4]) == bytes((0x85, 0xED, 0x64, 0xEE)), "EX_GETFNT $F157 원본 불일치"
        card[ko:ko + len(kcode)] = kcode
    o = bank0(NEWADDR)
    assert set(card[o:o + len(code)]) == {0xFF}, "NEWADDR 자리 비어 있지 않음"
    card[o:o + len(code)] = code
    p1 = bank0(0xF151)
    assert card[p1:p1 + 4] == bytes((0xA5, 0xF8, 0x85, 0xEC)), "EX_GETFNT $F151 원본 불일치"
    card[p1:p1 + 6] = bytes((0x20, NEWADDR & 0xFF, NEWADDR >> 8, 0x4C, 0xA5, 0xF1))
    p2 = bank0(0xF1B6)
    assert card[p2:p2 + 3] == bytes((0x8F, 0xFF, 0x0C)), "EX_GETFNT $F1B6 원본 불일치"
    card[p2:p2 + 3] = bytes((0xB0, 0x0D, 0xEA))
    info = {"keep12": len(keep), "boxj": boxj, "store12": len(store12), "base16": base16, "n16": len(l16),
            "store16": len(store16), "tab_bank": tab_bank, "tab_size": tab_size, "newaddr_bytes": len(code),
            "nk": len(lk), "kbase_j": kbase_j, "lk": lk, "credit_codes": sorted(set(credit_codes or ())),
            "free_after": {"16x16_region": [OLD16, 0x2C000], "12x12_tail": [tab_off + tab_size, PROTECT_FROM]},
            "c16": c16, "jmap": jmap}
    return bytes(card), info


def verify(card_old: bytes, card_new: bytes, info: dict) -> dict:
    """원본 EX_GETFNT(옛 카드) vs 패치 EX_GETFNT(새 카드) 실행 비교 — 유지 글자 전부, 두 창 경로, 두 모드."""
    import huc_mini_emu as E
    asg = json.loads(ASSIGN.read_text(encoding="utf-8"))["assignment"]
    rev = {int(v["sjis"], 16): ch for ch, v in asg.items()}
    gi = lambda code: fs.glyph_index((code >> 8, code & 0xFF), card_old)
    codes = set(rev)
    for lead in range(0x81, 0x88):
        for t in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            if gi(lead << 8 | t) is not None:
                codes.add(lead << 8 | t)
    stats = {"12_same": 0, "12_diff": 0, "16_balloon_ok": 0, "16_fallback12": 0, "box": 0, "err": []}
    c16 = set(info["c16"])
    i16 = {gi(c): c for c in c16}                        # 번호 기준 (원본 BIOS 는 서로 다른 코드가 같은 번호를 공유하기도 함)
    for code in sorted(codes):
        for w in ("low", "high"):
            a0, o12 = E.ex_getfnt(card_old, code, 1, w)
            a1, n12 = E.ex_getfnt(card_new, code, 1, w)
            if (a0, o12) == (a1, n12):
                stats["12_same"] += 1
            else:
                stats["12_diff"] += 1
                if len(stats["err"]) < 5: stats["err"].append(("12", hex(code), w))
            a1, n16 = E.ex_getfnt(card_new, code, 0, w)
            if gi(code) in i16:
                src = i16[gi(code)]
                want = render16(rev[src]) if src in rev else E.ex_getfnt(card_old, src, 0, w)[1]
                if n16 == want and a1 == 0:
                    stats["16_balloon_ok"] += 1
                elif len(stats["err"]) < 10:
                    stats["err"].append(("16", hex(code), w))
            elif gi(code) in set(info.get("lk", ())):
                stats["16_credit_shadow"] = stats.get("16_credit_shadow", 0) + 1   # 16x16 모드에서 이 번호는 크레딧 한자(위에서 따로 검증)
            else:
                if (a1, n16) == (a0, o12):
                    stats["16_fallback12"] += 1
                elif len(stats["err"]) < 10:
                    stats["err"].append(("16fb", hex(code), w))
    # (b58) 크레딧 한자: 16x16 요청 = 원본 카드의 12x12 출력 (같은 번호를 공유하는 코드는 하나만)
    stats["16_credit_ok"] = 0
    if info.get("lk"):
        orig = ORIG_CARD.read_bytes()
        want = set(info["lk"]); inv = {}
        for c in sorted(info.get("credit_codes", ())):
            i = gi(c)
            if i in want and i not in inv:
                inv[i] = c
        assert set(inv) == want, "LISTK 번호의 대표 코드 누락"
        for i in info["lk"]:
            for w in ("low", "high"):
                a1, n = E.ex_getfnt(card_new, inv[i], 0, w)
                if (a1, n) == E.ex_getfnt(orig, inv[i], 1, w):
                    stats["16_credit_ok"] += 1
                elif len(stats["err"]) < 10:
                    stats["err"].append(("16k", hex(inv[i]), w))
    # 미사용 한자 → □
    unused = [c for c in range(0x9440, 0x9480) if gi(c) is not None and gi(c) not in info["jmap"]][:3]
    for c in unused:                                     # 미사용 한자 → □ (두 모드 모두)
        for m in (0, 1):
            bx = E.ex_getfnt(card_new, c, m)[1]
            stats["box"] += int(bx[2:4] == bytes((0x7F, 0xE0)) and bx[4:6] == bytes((0x40, 0x20)))
    # 잘못된 코드(원본도 오류 1 반환)
    stats["invalid_code"] = (E.ex_getfnt(card_old, 0x0041, 1)[0], E.ex_getfnt(card_new, 0x0041, 1)[0])
    return stats
