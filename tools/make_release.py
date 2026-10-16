#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""테스트 배포판 재생성: <build> bin/카드 → Redump 트랙2 재구성 → 패처 해시 상수 → xdelta 3종 → PyInstaller exe → 배포 폴더 복사.
사용: python -X utf8 tools/make_release.py b31 [배포 폴더 이름] [--prev=<이전 판 빌드>:<라벨>:<이전 판 패처 .py>]
  --prev (2026-10-12 v0.3): 이전 판 결과물 → 이번 판 업그레이드 xdelta 3종(_from_<라벨>) + 패처 PREV_* 상수. 이전 판 결과(단일 bin·Redump 트랙 2·카드)를
  빌드에서 다시 만들어 이전 판 패처의 OUT_* 해시와 같은지 먼저 확인한다(다르면 중단).
  (zip 과 패처 실행 검증은 따로 — tools/verify_release_patcher.py)"""
import hashlib, re, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "release" / "app")); sys.path.insert(0, str(ROOT / "tools")); argv = sys.argv[1:]; sys.argv = ["x"]
from cdrom_mode1 import mode1_sector
from build_btrack_b7_hook_build import T2
PREV = next((a[len("--prev="):] for a in argv if a.startswith("--prev=")), None)
argv = [a for a in argv if not a.startswith("--prev=")]
tag = argv[0]
BIN = ROOT / f"Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_{tag}.bin"
CARD = ROOT / "probes" / f"SystemCard3_btrack_{tag}.pce"
ORIG = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin"
T2_ORIG = ROOT / "original" / "Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track 02).bin"
T2_KR = ROOT / "release" / "work" / "Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track 02)_KR.bin"
CARD_ORIG = Path("H:/BizHawk/Firmware/PCECD_3.0-(J).pce")
X = ROOT / "tools" / "xdelta3-3.2.0-windows-x86_64" / "xdelta3.exe"
APP = ROOT / "release" / "app"; DST = ROOT / "release" / (argv[1] if len(argv) > 1 else "Tenshi2_KR_test_20261010")   # 2번째 인자 = 배포 폴더 이름(0.2 부터)
DST.mkdir(exist_ok=True)
PRE, SEC, LBA0 = 224, 2352, 3590

data = BIN.read_bytes(); orig_t2 = T2_ORIG.read_bytes()
# (2026-10-11 b57) 트랙 2 길이 = 원본 Redump 트랙 2 + 빌드의 데이터 트랙 확장(빌드 bin − 원본 bin). b56 까지는 +1024 로 고정(10576)이었으나,
# 확장이 뒤 오디오 트랙의 절대 위치를 밀어 비주얼 씬 음성 싱크가 어긋남(절대 위치 탐색) → b57 부터 확장 0. cue 서식도 빌드 cue 에서 만든다.
EXT = (len(data) - ORIG.stat().st_size) // 2048
assert len(data) - ORIG.stat().st_size == EXT * 2048
TOTAL = len(orig_t2) // SEC + EXT
cue = (ROOT / BIN.with_suffix(".cue").name).read_text(encoding="ascii")
(APP / "cue_template.cue").write_text(cue.replace(f'FILE "{BIN.name}"', 'FILE "{BIN}"', 1), encoding="ascii", newline="\n")
print("track ext sectors", EXT, "redump track02 sectors", TOTAL)
out = bytearray(orig_t2[:PRE * SEC])
for i in range(TOTAL - PRE):
    out += mode1_sector(data[T2 + i * 2048:T2 + (i + 1) * 2048], LBA0 + i)
T2_KR.write_bytes(out)
h = {"OUT_BIN_SHA1": hashlib.sha1(data).hexdigest(), "OUT_T2_SHA1": hashlib.sha1(out).hexdigest(), "OUT_CARD_SHA1": hashlib.sha1(CARD.read_bytes()).hexdigest()}
UPG = []
if PREV:
    ptag, plabel, ppatcher = PREV.split(":", 2)
    pbin = (ROOT / f"Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_{ptag}.bin").read_bytes()
    pcard = (ROOT / "probes" / f"SystemCard3_btrack_{ptag}.pce").read_bytes()
    pext = (len(pbin) - ORIG.stat().st_size) // 2048
    pt2 = bytearray(orig_t2[:PRE * SEC])
    for i in range(len(orig_t2) // SEC + pext - PRE):
        pt2 += mode1_sector(pbin[T2 + i * 2048:T2 + (i + 1) * 2048], LBA0 + i)
    ps = Path(ppatcher).read_text(encoding="utf-8")
    want = {k: re.search(rf'^{k} = "([0-9a-f]+)"', ps, flags=re.M).group(1) for k in ("OUT_BIN_SHA1", "OUT_T2_SHA1", "OUT_CARD_SHA1")}
    got = {"OUT_BIN_SHA1": hashlib.sha1(pbin).hexdigest(), "OUT_T2_SHA1": hashlib.sha1(pt2).hexdigest(), "OUT_CARD_SHA1": hashlib.sha1(pcard).hexdigest()}
    assert got == want, f"이전 판 결과 재현 불일치 {got} != {want}"
    PT2 = ROOT / "release" / "work" / f"Tenshi no Uta II - Datenshi no Sentaku (Japan) (Track 02)_KR_{plabel}.bin"
    PT2.write_bytes(pt2)
    PBIN_TMP = ROOT / "release" / "work" / f"prev_{ptag}_card.pce"; PBIN_TMP.write_bytes(pcard)
    h.update({"PREV_BIN_SHA1": got["OUT_BIN_SHA1"], "PREV_T2_SHA1": got["OUT_T2_SHA1"], "PREV_CARD_SHA1": got["OUT_CARD_SHA1"]})
    hn = {"PREV_BIN_SIZE": len(pbin), "PREV_T2_SIZE": len(pt2)}
    UPG = [(ROOT / f"Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_{ptag}.bin", BIN, f"Tenshi_no_Uta_II_KR_disc_from_{plabel}.xdelta"),
           (PT2, T2_KR, f"Tenshi_no_Uta_II_KR_track02_redump_from_{plabel}.xdelta"),
           (PBIN_TMP, CARD, f"SystemCard3_KR_from_{plabel}.xdelta")]
    print("prev reproduced:", plabel, got)
p = APP / "tenshi2kr_patcher.py"; s = p.read_text(encoding="utf-8")
for k, v in h.items(): s = re.sub(rf'^{k} = "[0-9a-f]+"', f'{k} = "{v}"', s, flags=re.M)
if PREV:
    for k, v in hn.items(): s = re.sub(rf'^{k} = \d+', f'{k} = {v}', s, flags=re.M)
    s = re.sub(r'^PREV_LABEL = "[^"]*"', f'PREV_LABEL = "{plabel}"', s, flags=re.M)
    for k, (_, _, name) in zip(("UPG_DISC_PATCH", "UPG_T2_PATCH", "UPG_CARD_PATCH"), UPG):
        s = re.sub(rf'^{k} = "[^"]*"', f'{k} = "{name}"', s, flags=re.M)
p.write_text(s, encoding="utf-8", newline="\n"); print(h)
for args in ([str(X), "-e", "-f", "-S", "djw", "-B", "1073741824", "-s", str(ORIG), str(BIN), str(APP / "Tenshi_no_Uta_II_KR_disc.xdelta")],
             [str(X), "-e", "-f", "-S", "djw", "-B", "1073741824", "-s", str(T2_ORIG), str(T2_KR), str(APP / "Tenshi_no_Uta_II_KR_track02_redump.xdelta")],
             [str(X), "-e", "-f", "-S", "djw", "-s", str(CARD_ORIG), str(CARD), str(APP / "SystemCard3_KR.xdelta")]) + tuple(
             [str(X), "-e", "-f", "-S", "djw", "-B", "1073741824", "-s", str(a), str(b), str(APP / n)] for a, b, n in UPG):
    subprocess.run(args, check=True)
r = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noconsole", "--name", "Tenshi2KR_Patcher",
                    "--collect-all", "tkinterdnd2", "--add-binary", "xdelta3.exe;.", "tenshi2kr_patcher.py"], cwd=APP, capture_output=True, text=True)
(APP / "build.log").write_text(r.stdout + r.stderr, encoding="utf-8"); assert r.returncode == 0, "PyInstaller 실패"
for f in ["dist/Tenshi2KR_Patcher.exe", "Tenshi_no_Uta_II_KR_disc.xdelta", "Tenshi_no_Uta_II_KR_track02_redump.xdelta", "SystemCard3_KR.xdelta", "README.txt", "cue_template.cue"] + [n for _, _, n in UPG]:
    shutil.copy2(APP / f, DST / Path(f).name)
print("release folder updated:", DST)
