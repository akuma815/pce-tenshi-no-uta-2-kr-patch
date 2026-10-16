#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배포판 패처 exe CLI 검증 (v0.3, 2026-10-12): 원본을 하드링크한 시험 폴더에서 exe 로 4경로 패치 → 결과 SHA-1 이 빌드와 같은지.
  ① 단일 bin + cue ② Redump 34트랙 cue(트랙 2 만 교체) ③ 카드(헤더 없음) ④ 카드(512B 헤더)
  + (있으면) 이전 판 결과물 → 이번 판 업그레이드 3경로: ⑤ 이전 판 단일 *_KR.cue(제자리 교체 + cue 새로) ⑥ 이전 판 Redump *_KR.cue ⑦ 이전 판 SystemCard3_KR.pce
    — 이전 판 결과물은 make_release --prev 가 재현해 둔 파일(빌드 bin·release/work 트랙 2·빌드 카드)을 하드링크(제자리 교체는 디렉터리 항목만 바꾸므로 원본 불변).
끝나면 시험 폴더를 지우고 원본 SHA-1 을 다시 확인한다(하드링크라 원본이 바뀌면 드러남).
사용: python -X utf8 tools/verify_release_patcher.py <빌드 태그> <배포 폴더 이름>
"""
import hashlib, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tag, rel = sys.argv[1:3]
REL = ROOT / "release" / rel
T = ROOT / "qa" / f"release_{rel}" / "work"
ORIG_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
ORIG_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue"
REDUMP = ROOT / "original"
CARD = Path("H:/BizHawk/Firmware/PCECD_3.0-(J).pce")
BUILD_BIN = ROOT / f"Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_{tag}.bin"
BUILD_CARD = ROOT / "probes" / f"SystemCard3_btrack_{tag}.pce"
T2_KR = ROOT / "release" / "work" / "Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track 02)_KR.bin"


def sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


before = {p: sha1(p) for p in [ORIG_BIN, REDUMP / "Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track 02).bin", CARD]}
if T.exists():
    shutil.rmtree(T)
(T / "single").mkdir(parents=True); (T / "redump").mkdir(); (T / "card").mkdir(); (T / "app").mkdir()
for f in REL.iterdir():
    shutil.copy2(f, T / "app" / f.name)
os.link(ORIG_BIN, T / "single" / ORIG_BIN.name); shutil.copy2(ORIG_CUE, T / "single" / ORIG_CUE.name)
for f in REDUMP.iterdir():
    if f.suffix == ".bin":
        os.link(f, T / "redump" / f.name)
    elif f.suffix == ".cue":
        shutil.copy2(f, T / "redump" / f.name)
shutil.copy2(CARD, T / "card" / "card_noheader.pce")
(T / "card" / "card_header.pce").write_bytes(bytes(512) + CARD.read_bytes())
(T / "card2").mkdir(); shutil.move(T / "card" / "card_header.pce", T / "card2" / "card_header.pce")
exe = T / "app" / "Tenshi2KR_Patcher.exe"

res = {}
for name, args in [("single", ["--disc", str(T / "single" / ORIG_CUE.name)]),
                   ("redump", ["--disc", str(next((T / "redump").glob("*.cue")))]),
                   ("card", ["--card", str(T / "card" / "card_noheader.pce")]),
                   ("card_hdr", ["--card", str(T / "card2" / "card_header.pce")])]:
    r = subprocess.run([str(exe)] + args, cwd=T / "app", capture_output=True, text=True, timeout=900)
    res[name] = r.returncode
want = {"single": sha1(BUILD_BIN), "redump": sha1(T2_KR), "card": sha1(BUILD_CARD)}
got = {"single": sha1(T / "single" / (ORIG_BIN.stem + "_KR.bin")),
       "redump": sha1(next((T / "redump").glob("*(Track 02)_KR.bin"))),
       "card": sha1(T / "card" / "SystemCard3_KR.pce"), "card_hdr": sha1(T / "card2" / "SystemCard3_KR.pce")}
ok = (got["single"] == want["single"] and got["redump"] == want["redump"]
      and got["card"] == want["card"] and got["card_hdr"] == want["card"] and all(v == 0 for v in res.values()))
cues = {"single_cue": (T / "single" / (ORIG_CUE.stem + "_KR.cue")).read_text(encoding="utf-8")[:200],
        "redump_cue_has_kr_t2": "(Track 02)_KR.bin" in next((T / "redump").glob("*_KR.cue")).read_text(encoding="utf-8")}
print({"exit": res, "match": {k: got[k] == want.get(k, want["card"]) for k in got}, "ok": ok})
print(cues)
keep = ROOT / "qa" / f"release_{rel}" / "out"
keep.mkdir(exist_ok=True)
for p in [T / "single" / (ORIG_CUE.stem + "_KR.cue"), next((T / "redump").glob("*_KR.cue"))]:
    shutil.copy2(p, keep / p.name)
# ── BizHawk gamedb 등록(PCEHawk 코어용, v0.3 2026-10-12) — 가짜 BizHawk 폴더에서 --emu 두 번: 한 줄만 추가·백업·카드 MD5 일치 ──
B = T / "bizhawk"; (B / "gamedb").mkdir(parents=True); (B / "lnk").mkdir()
(B / "EmuHawk.exe").write_bytes(b"MZ")
gsrc = ROOT / "BizHawk-master" / "output" / "gamedb" / "gamedb_pce_hucards.txt.bak_20261012"
shutil.copy2(gsrc, B / "gamedb" / "gamedb_pce_hucards.txt")
n0 = len((B / "gamedb" / "gamedb_pce_hucards.txt").read_bytes().splitlines())
kcard = T / "card" / "SystemCard3_KR.pce"; kcue = T / "single" / (ORIG_CUE.stem + "_KR.cue")
gr = []
for _ in range(2):
    r = subprocess.run([str(exe), "--emu", str(B / "EmuHawk.exe"), "--cue", str(kcue), "--card-out", str(kcard), "--shortcut-dir", str(B / "lnk")],
                       cwd=T / "app", capture_output=True, timeout=300)
    gr.append(r.returncode)
lines = (B / "gamedb" / "gamedb_pce_hucards.txt").read_bytes().splitlines()
md5 = hashlib.md5(kcard.read_bytes()).hexdigest().upper().encode()
gcheck = {"exit": gr, "added_once": len(lines) == n0 + 1 and sum(md5 in l for l in lines) == 1,
          "flags": lines[-1].endswith(b"BRAM;SuperSysCard;BIOS"), "backup": (B / "gamedb" / "gamedb_pce_hucards.txt.bak_tenshi2kr").exists(),
          "config": (B / "config_tenshi2kr.ini").exists()}
print({"gamedb_check": gcheck, "ok": all(v for k, v in gcheck.items() if k != "exit") and gr == [0, 0]})
# ── 이전 판 → 이번 판 업그레이드 ──
import re as _re
ps = (REL / "Tenshi2KR_Patcher.exe").exists() and (ROOT / "release" / "app" / "tenshi2kr_patcher.py").read_text(encoding="utf-8")
m = _re.search(r'^PREV_LABEL = "([^"]+)"', ps, flags=_re.M)
if m and len(sys.argv) > 3:
    plabel, ptag, pcue_tpl = m.group(1), sys.argv[3], Path(sys.argv[4])
    U = T.parent / "upgrade"
    if U.exists():
        shutil.rmtree(U)
    (U / "single").mkdir(parents=True); (U / "redump").mkdir(); (U / "card").mkdir()
    kr = ORIG_BIN.stem + "_KR"
    os.link(ROOT / f"Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_{ptag}.bin", U / "single" / (kr + ".bin"))
    (U / "single" / (kr + ".cue")).write_text(pcue_tpl.read_text(encoding="utf-8").replace("{BIN}", kr + ".bin"), encoding="utf-8", newline="\r\n")
    rcue = next(REDUMP.glob("*.cue")); names = []
    for f in REDUMP.iterdir():
        if f.suffix == ".bin" and "(Track 02)" not in f.name:
            os.link(f, U / "redump" / f.name)
    t2n = "Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track 02)_KR.bin"
    os.link(ROOT / "release" / "work" / f"Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track 02)_KR_{plabel}.bin", U / "redump" / t2n)
    rtxt = rcue.read_text(encoding="utf-8").replace('FILE "Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track 02).bin"', 'FILE "' + t2n + '"', 1)
    (U / "redump" / (rcue.stem + "_KR.cue")).write_text(rtxt, encoding="utf-8", newline="\r\n")
    shutil.copy2(ROOT / "probes" / f"SystemCard3_btrack_{ptag}.pce", U / "card" / "SystemCard3_KR.pce")
    ures = {}
    for name, args in [("up_single", ["--disc", str(U / "single" / (kr + ".cue"))]),
                       ("up_redump", ["--disc", str(U / "redump" / (rcue.stem + "_KR.cue"))]),
                       ("up_card", ["--card", str(U / "card" / "SystemCard3_KR.pce")])]:
        r = subprocess.run([str(exe)] + args, cwd=T / "app", capture_output=True, timeout=900)
        ures[name] = r.returncode
    tpl = (REL / "cue_template.cue").read_text(encoding="utf-8").replace("{BIN}", kr + ".bin")
    ucheck = {"up_single": sha1(U / "single" / (kr + ".bin")) == want["single"],
              "up_single_cue": (U / "single" / (kr + ".cue")).read_text(encoding="utf-8").replace("\r\n", "\n") == tpl.replace("\r\n", "\n"),
              "up_redump": sha1(U / "redump" / t2n) == want["redump"],
              "up_redump_cue_same": (U / "redump" / (rcue.stem + "_KR.cue")).read_text(encoding="utf-8") == rtxt,
              "up_card": sha1(U / "card" / "SystemCard3_KR.pce") == want["card"],
              "no_tmp_left": not any(p.name.endswith(".upgrade_tmp") for p in U.rglob("*"))}
    print({"upgrade_exit": ures, "upgrade_check": ucheck, "ok": all(ucheck.values()) and all(v == 0 for v in ures.values())})
    pb = ROOT / f"Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_{ptag}.bin"
    print("prev build bin intact:", sha1(pb) == _re.search(r'^PREV_BIN_SHA1 = "([0-9a-f]+)"', ps, flags=_re.M).group(1))
print("work kept for smoke:", T)
after = {p: sha1(p) for p in before}
assert before == after, "원본 SHA-1 이 바뀜!"
print("originals unchanged")
