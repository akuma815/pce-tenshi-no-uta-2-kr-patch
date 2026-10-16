#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검증용 최소 HuC6280 인터프리터 (BIOS 루틴을 카드 이미지 위에서 직접 실행해 결과를 비교하는 용도).

메모리: 논리 주소 → MPR[addr>>13] 뱅크. 뱅크 $00-$3F = 카드 ROM(쓰기 무시), 그 외 = RAM(뱅크별 8KB, 0 초기화).
I/O·인터럽트·타이밍·십진 모드는 없다. 모르는 명령은 예외로 멈춘다(조용히 넘어가지 않음).
"""
from __future__ import annotations


class Halt(Exception):
    pass


class CPU:
    def __init__(self, card: bytes):
        self.card = card
        self.ram: dict[int, bytearray] = {}
        self.mpr = [0xFF, 0xF8, 0, 0, 0, 0, 0, 0]
        self.a = self.x = self.y = 0
        self.s = 0xFF
        self.pc = 0
        self.n = self.v = self.z = self.c = 0
        self.steps = 0

    # ---- 메모리 ----
    def _phys(self, addr):
        return self.mpr[(addr >> 13) & 7], addr & 0x1FFF

    def rd(self, addr):
        addr &= 0xFFFF
        bank, off = self._phys(addr)
        if bank < 0x40:
            o = bank * 0x2000 + off
            return self.card[o] if o < len(self.card) else 0xFF
        return self.ram.setdefault(bank, bytearray(0x2000))[off]

    def wr(self, addr, v):
        addr &= 0xFFFF
        bank, off = self._phys(addr)
        if bank < 0x40:
            return
        self.ram.setdefault(bank, bytearray(0x2000))[off] = v & 0xFF

    def zp(self, z):
        return 0x2000 | (z & 0xFF)

    def rd16zp(self, z):
        return self.rd(self.zp(z)) | self.rd(self.zp((z + 1) & 0xFF)) << 8

    def push(self, v):
        self.wr(0x2100 | self.s, v); self.s = (self.s - 1) & 0xFF

    def pop(self):
        self.s = (self.s + 1) & 0xFF; return self.rd(0x2100 | self.s)

    def fetch(self):
        v = self.rd(self.pc); self.pc = (self.pc + 1) & 0xFFFF; return v

    def fetch16(self):
        lo = self.fetch(); return lo | self.fetch() << 8

    # ---- 플래그 ----
    def nz(self, v):
        v &= 0xFF; self.n = v >> 7; self.z = int(v == 0); return v

    def getp(self):
        return self.n << 7 | self.v << 6 | 0x20 | self.c | self.z << 1

    def setp(self, p):
        self.n, self.v, self.z, self.c = p >> 7 & 1, p >> 6 & 1, p >> 1 & 1, p & 1

    def adc(self, m):
        r = self.a + m + self.c
        self.v = int(((self.a ^ r) & (m ^ r) & 0x80) != 0)
        self.c = int(r > 0xFF); self.a = self.nz(r)

    def sbc(self, m):
        self.adc(m ^ 0xFF)

    def cmp(self, r, m):
        t = r - m; self.c = int(t >= 0); self.nz(t)

    # ---- 주소 모드 ----
    def ea(self, mode):
        if mode == "zp": return self.zp(self.fetch())
        if mode == "zpx": return self.zp(self.fetch() + self.x)
        if mode == "abs": return self.fetch16()
        if mode == "absx": return (self.fetch16() + self.x) & 0xFFFF
        if mode == "absy": return (self.fetch16() + self.y) & 0xFFFF
        if mode == "ind": return self.rd16zp(self.fetch())
        if mode == "indy": return (self.rd16zp(self.fetch()) + self.y) & 0xFFFF
        if mode == "indx": return self.rd16zp(self.fetch() + self.x)
        raise ValueError(mode)

    def branch(self, cond):
        r = self.fetch()
        if cond:
            self.pc = (self.pc + (r - 256 if r >= 128 else r)) & 0xFFFF

    def call(self, addr, max_steps=200000):
        """addr 를 JSR 처럼 호출하고 대응 RTS 까지 실행."""
        self.push(0xFF); self.push(0xFE)          # 복귀 주소 $FFFF → 표지
        self.pc = addr
        while True:
            if self.pc == 0xFFFF:
                return
            self.step()
            self.steps += 1
            if self.steps > max_steps:
                raise Halt("step limit")

    def step(self):
        pc0 = self.pc
        op = self.fetch()
        LD = {0xA9: "imm", 0xA5: "zp", 0xB5: "zpx", 0xAD: "abs", 0xBD: "absx", 0xB9: "absy", 0xB2: "ind", 0xB1: "indy", 0xA1: "indx"}
        if op in LD:
            m = self.fetch() if LD[op] == "imm" else self.rd(self.ea(LD[op])); self.a = self.nz(m); return
        ST = {0x85: "zp", 0x95: "zpx", 0x8D: "abs", 0x9D: "absx", 0x99: "absy", 0x92: "ind", 0x91: "indy", 0x81: "indx"}
        if op in ST:
            self.wr(self.ea(ST[op]), self.a); return
        ALU = {0x69: ("adc", "imm"), 0x65: ("adc", "zp"), 0x6D: ("adc", "abs"), 0x7D: ("adc", "absx"), 0x79: ("adc", "absy"), 0x72: ("adc", "ind"), 0x71: ("adc", "indy"),
               0xE9: ("sbc", "imm"), 0xE5: ("sbc", "zp"), 0xED: ("sbc", "abs"), 0xFD: ("sbc", "absx"), 0xF9: ("sbc", "absy"), 0xF2: ("sbc", "ind"), 0xF1: ("sbc", "indy"),
               0x29: ("and", "imm"), 0x25: ("and", "zp"), 0x2D: ("and", "abs"), 0x3D: ("and", "absx"), 0x39: ("and", "absy"), 0x32: ("and", "ind"), 0x31: ("and", "indy"),
               0x09: ("ora", "imm"), 0x05: ("ora", "zp"), 0x0D: ("ora", "abs"), 0x1D: ("ora", "absx"), 0x19: ("ora", "absy"), 0x12: ("ora", "ind"), 0x11: ("ora", "indy"),
               0x49: ("eor", "imm"), 0x45: ("eor", "zp"), 0x4D: ("eor", "abs"), 0x5D: ("eor", "absx"),
               0xC9: ("cmp", "imm"), 0xC5: ("cmp", "zp"), 0xCD: ("cmp", "abs"), 0xDD: ("cmp", "absx"), 0xD9: ("cmp", "absy"), 0xD2: ("cmp", "ind"), 0xD1: ("cmp", "indy")}
        if op in ALU:
            f, mode = ALU[op]
            m = self.fetch() if mode == "imm" else self.rd(self.ea(mode))
            if f == "adc": self.adc(m)
            elif f == "sbc": self.sbc(m)
            elif f == "and": self.a = self.nz(self.a & m)
            elif f == "ora": self.a = self.nz(self.a | m)
            elif f == "eor": self.a = self.nz(self.a ^ m)
            else: self.cmp(self.a, m)
            return
        if op in (0xA2, 0xA6, 0xAE, 0xB6, 0xBE):
            mode = {0xA2: "imm", 0xA6: "zp", 0xAE: "abs", 0xBE: "absy"}.get(op)
            if op == 0xB6:
                m = self.rd(self.zp(self.fetch() + self.y))
            else:
                m = self.fetch() if mode == "imm" else self.rd(self.ea(mode))
            self.x = self.nz(m); return
        if op in (0xA0, 0xA4, 0xAC, 0xB4, 0xBC):
            mode = {0xA0: "imm", 0xA4: "zp", 0xAC: "abs", 0xB4: "zpx", 0xBC: "absx"}[op]
            m = self.fetch() if mode == "imm" else self.rd(self.ea(mode)); self.y = self.nz(m); return
        if op in (0x86, 0x8E):
            self.wr(self.ea("zp" if op == 0x86 else "abs"), self.x); return
        if op in (0x84, 0x8C):
            self.wr(self.ea("zp" if op == 0x84 else "abs"), self.y); return
        if op in (0x64, 0x74, 0x9C, 0x9E):
            self.wr(self.ea({0x64: "zp", 0x74: "zpx", 0x9C: "abs", 0x9E: "absx"}[op]), 0); return
        if op in (0xE0, 0xE4, 0xEC):
            m = self.fetch() if op == 0xE0 else self.rd(self.ea("zp" if op == 0xE4 else "abs")); self.cmp(self.x, m); return
        if op in (0xC0, 0xC4, 0xCC):
            m = self.fetch() if op == 0xC0 else self.rd(self.ea("zp" if op == 0xC4 else "abs")); self.cmp(self.y, m); return
        RMW = {0xE6: ("inc", "zp"), 0xF6: ("inc", "zpx"), 0xEE: ("inc", "abs"), 0xFE: ("inc", "absx"),
               0xC6: ("dec", "zp"), 0xD6: ("dec", "zpx"), 0xCE: ("dec", "abs"), 0xDE: ("dec", "absx"),
               0x06: ("asl", "zp"), 0x0E: ("asl", "abs"), 0x46: ("lsr", "zp"), 0x4E: ("lsr", "abs"),
               0x26: ("rol", "zp"), 0x2E: ("rol", "abs"), 0x66: ("ror", "zp"), 0x6E: ("ror", "abs")}
        if op in RMW or op in (0x1A, 0x3A, 0x0A, 0x4A, 0x2A, 0x6A):
            if op in RMW:
                f, mode = RMW[op]; ad = self.ea(mode); m = self.rd(ad)
            else:
                f = {0x1A: "inc", 0x3A: "dec", 0x0A: "asl", 0x4A: "lsr", 0x2A: "rol", 0x6A: "ror"}[op]; ad = None; m = self.a
            if f == "inc": r = self.nz(m + 1)
            elif f == "dec": r = self.nz(m - 1)
            elif f == "asl": self.c = m >> 7; r = self.nz(m << 1)
            elif f == "lsr": self.c = m & 1; r = self.nz(m >> 1)
            elif f == "rol": r = self.nz(m << 1 | self.c); self.c = m >> 7
            else: r = self.nz(m >> 1 | self.c << 7); self.c = m & 1
            if ad is None: self.a = r
            else: self.wr(ad, r)
            return
        BR = {0x10: lambda: not self.n, 0x30: lambda: self.n, 0x50: lambda: not self.v, 0x70: lambda: self.v,
              0x90: lambda: not self.c, 0xB0: lambda: self.c, 0xD0: lambda: not self.z, 0xF0: lambda: self.z, 0x80: lambda: True}
        if op in BR:
            self.branch(BR[op]()); return
        if op & 0x0F == 0x0F:                      # BBRn / BBSn zp, rel
            bit = (op >> 4) & 7; m = self.rd(self.zp(self.fetch()))
            self.branch(((m >> bit) & 1) == (1 if op & 0x80 else 0)); return
        if op & 0x0F == 0x07:                      # RMBn / SMBn
            bit = (op >> 4) & 7; ad = self.zp(self.fetch()); m = self.rd(ad)
            self.wr(ad, m | 1 << bit if op & 0x80 else m & ~(1 << bit)); return
        if op == 0x20:
            t = self.fetch16(); r = (self.pc - 1) & 0xFFFF; self.push(r >> 8); self.push(r & 0xFF); self.pc = t; return
        if op == 0x44:                             # BSR
            r = self.fetch(); ret = (self.pc - 1) & 0xFFFF; self.push(ret >> 8); self.push(ret & 0xFF)
            self.pc = (self.pc + (r - 256 if r >= 128 else r)) & 0xFFFF; return
        if op == 0x60:
            lo = self.pop(); hi = self.pop(); self.pc = ((hi << 8 | lo) + 1) & 0xFFFF; return
        if op == 0x4C:
            self.pc = self.fetch16(); return
        if op == 0x6C:
            p = self.fetch16(); self.pc = self.rd(p) | self.rd(p + 1) << 8; return
        if op == 0x7C:
            p = (self.fetch16() + self.x) & 0xFFFF; self.pc = self.rd(p) | self.rd(p + 1) << 8; return
        if op == 0x53:                             # TAM
            m = self.fetch()
            for i in range(8):
                if m >> i & 1: self.mpr[i] = self.a
            return
        if op == 0x43:                             # TMA
            m = self.fetch()
            for i in range(8):
                if m >> i & 1: self.a = self.mpr[i]
            return
        SIMPLE = {0x48: lambda: self.push(self.a), 0x68: lambda: setattr(self, "a", self.nz(self.pop())),
                  0xDA: lambda: self.push(self.x), 0xFA: lambda: setattr(self, "x", self.nz(self.pop())),
                  0x5A: lambda: self.push(self.y), 0x7A: lambda: setattr(self, "y", self.nz(self.pop())),
                  0x08: lambda: self.push(self.getp() | 0x10), 0x28: lambda: self.setp(self.pop()),
                  0xAA: lambda: setattr(self, "x", self.nz(self.a)), 0x8A: lambda: setattr(self, "a", self.nz(self.x)),
                  0xA8: lambda: setattr(self, "y", self.nz(self.a)), 0x98: lambda: setattr(self, "a", self.nz(self.y)),
                  0xBA: lambda: setattr(self, "x", self.nz(self.s)), 0x9A: lambda: setattr(self, "s", self.x),
                  0xE8: lambda: setattr(self, "x", self.nz(self.x + 1)), 0xCA: lambda: setattr(self, "x", self.nz(self.x - 1)),
                  0xC8: lambda: setattr(self, "y", self.nz(self.y + 1)), 0x88: lambda: setattr(self, "y", self.nz(self.y - 1)),
                  0x18: lambda: setattr(self, "c", 0), 0x38: lambda: setattr(self, "c", 1), 0xB8: lambda: setattr(self, "v", 0),
                  0x58: lambda: None, 0x78: lambda: None, 0xD8: lambda: None, 0xF8: lambda: None, 0xEA: lambda: None,
                  0x62: lambda: setattr(self, "a", 0), 0x82: lambda: setattr(self, "x", 0), 0xC2: lambda: setattr(self, "y", 0)}
        if op in SIMPLE:
            SIMPLE[op](); return
        if op == 0x22: self.a, self.x = self.x, self.a; return
        if op == 0x42: self.a, self.y = self.y, self.a; return
        if op == 0x02: self.x, self.y = self.y, self.x; return
        if op in (0x24, 0x2C, 0x89):
            m = self.fetch() if op == 0x89 else self.rd(self.ea("zp" if op == 0x24 else "abs"))
            self.z = int((self.a & m) == 0)
            if op != 0x89: self.n, self.v = m >> 7 & 1, m >> 6 & 1
            return
        raise Halt(f"미구현 명령 {op:02X} @ {pc0:04X}")


def ex_getfnt(card: bytes, code: int, mode: int, buf_window: str = "low") -> tuple[int, bytes]:
    """EX_GETFNT($E060) 실행: code = SJIS(hi<<8|lo), mode = 0(16x16)/1(12x12).
    buf_window: 'low' = 버퍼 $3000(RAM $F8) / 'high' = 버퍼 $A000(CD RAM $80 을 MPR5 에) — 두 창 경로 모두 시험.
    반환 (A 레지스터, 32B 출력)."""
    cpu = CPU(card)
    cpu.mpr = [0xFF, 0xF8, 0x81, 0x82, 0x83, 0x80 if buf_window == "high" else 0x84, 0x85, 0x00]
    buf = 0xA000 if buf_window == "high" else 0x3000
    for i in range(32):
        cpu.wr(buf + i, 0xEE)
    cpu.wr(0x20F8, code & 0xFF); cpu.wr(0x20F9, code >> 8)
    cpu.wr(0x20FA, buf & 0xFF); cpu.wr(0x20FB, buf >> 8)
    cpu.wr(0x20FF, mode)
    mpr_before = list(cpu.mpr)
    cpu.call(0xE060)
    assert cpu.mpr == mpr_before, f"MPR 복원 실패 {cpu.mpr} != {mpr_before}"
    assert cpu.rd(0x20FF) == mode, "$FF(모드 인자) 변경됨"
    return cpu.a, bytes(cpu.rd(buf + i) for i in range(32))
