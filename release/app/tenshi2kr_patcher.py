# -*- coding: utf-8 -*-
"""천사의 시 II ~타천사의 선택~ 한글판 패처 (v1.0.1)
 0) 이전 판(v1.0·v0.3) 패치 결과물(*_KR.bin/.cue, Redump (Track 02)_KR.bin, SystemCard3_KR.pce)을 지정하면 SHA-1 로 알아보고 그 자리에서 v1.0.1 로 교체
    (v1.0.1 = v1.0 + 카드 미니게임 모듈 초기화 수정 9바이트. 시스템 카드는 v1.0 과 같고, v0.3 카드는 from_v0.3 패치로 올린다)
 1) 원본 디스크 이미지(.bin/.cue)에 xdelta 패치 → *_KR.bin + *_KR.cue
 2) 원본 시스템 카드(PCECD_3.0-(J).pce, 256KB)에 xdelta 패치 → SystemCard3_KR.pce (256KB, 원본과 같은 크기)
 3) BizHawk(EmuHawk.exe) 선택 → 한글 카드로 바로 실행되는 바로가기(.lnk) + 전용 config 생성 + gamedb 에 한글 카드 등록(PCEHawk 코어용)
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

APP_TITLE = "천사의 시 II 한글판 패처 v1.0.1"
DISC_PATCH = "Tenshi_no_Uta_II_KR_disc.xdelta"
CARD_PATCH = "SystemCard3_KR.xdelta"
CUE_TEMPLATE = "cue_template.cue"
ORIG_BIN_SIZE = 523184384
ORIG_BIN_SHA1 = "67ec659f387accd4544057a8bff4ab84bf5e153b"
ORIG_CARD_SIZE = 262144
ORIG_CARD_SHA1 = "79f5ff55dd10187c7fd7b8daab0b3ffbd1f56a2c"
OUT_BIN_SHA1 = "78496ddcba76b6e519a2cb292c29d5909514b73a"
OUT_CARD_SHA1 = "aeea911116af35f1bf7035487c0a6438b1a37877"
T2_PATCH = "Tenshi_no_Uta_II_KR_track02_redump.xdelta"
REDUMP_T2_SIZE = 22466304
REDUMP_T2_SHA1 = "e0a7dbed4f3f4d57d4bb044cb1520aa26c0324d4"
OUT_T2_SHA1 = "5b1c1f7168a08218269918bb9a932118c9e6cb85"
# 이전 판(v1.0; 디스크·Track 02 는 v0.3 과 같은 내용) 결과물 → 이번 판으로 올리는 패치. 카드는 v1.0 = v1.0.1 이라 v0.3 카드만 올린다. 이전 판 결과물을 지정하면 SHA-1 로 알아보고 그 자리에서 교체한다
# (파일 이름이 그대로라 BizHawk·RetroArch 의 세이브가 이어진다). 원본 덤프를 지정하면 지금처럼 새로 패치(같은 이름으로 덮어씀).
PREV_LABEL = "이전 판(v1.0/v0.3)"
PREV_BIN_SIZE = 523184384
PREV_BIN_SHA1 = "46af005cd4fb5e912f505f12c5929fa5af1bf3e5"
PREV_T2_SIZE = 22466304
PREV_T2_SHA1 = "d80d35170802964f09831b17f35e4ff69d989581"
PREV_CARD_SHA1 = "c1d5c3f17615012fefda78ffb1752f35e0b121fe"
UPG_DISC_PATCH = "Tenshi_no_Uta_II_KR_disc_from_v1.0.xdelta"
UPG_T2_PATCH = "Tenshi_no_Uta_II_KR_track02_redump_from_v1.0.xdelta"
UPG_CARD_PATCH = "SystemCard3_KR_from_v0.3.xdelta"
CONFIG_NAME = "config_tenshi2kr.ini"
SHORTCUT_NAME = "천사의 시 II 한글판.lnk"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def res_dir():
    """번들 리소스(xdelta3.exe) 위치."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def app_dir():
    """패치 파일이 놓인 곳 = exe(또는 스크립트) 폴더."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_file(name):
    for d in (app_dir(), res_dir(), os.getcwd()):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(name + " 을(를) 찾을 수 없습니다. 패처와 같은 폴더에 두세요.")


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 22)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def run_xdelta(src, patch, out):
    exe = find_file("xdelta3.exe")
    r = subprocess.run([exe, "-d", "-f", "-s", src, patch, out],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip()
        if "checksum" in msg.lower():
            raise RuntimeError("원본 파일이 패치 기준과 다릅니다(체크섬 불일치).\n" + msg)
        raise RuntimeError("xdelta 적용 실패:\n" + msg)


def upgrade_inplace(path, patch, want_sha1, what, log=print):
    """이전 판 결과물(path)을 이번 판으로: 같은 폴더 임시 파일에 패치 → SHA-1 확인 → 원래 이름으로 교체."""
    tmp = path + ".upgrade_tmp"
    log(what + ": " + PREV_LABEL + " 결과물 감지 → 이번 판으로 올리는 패치 적용 중...")
    try:
        run_xdelta(path, find_file(patch), tmp)
        if sha1(tmp) != want_sha1:
            raise RuntimeError(what + " 업그레이드 결과 검증 실패(SHA-1 불일치).")
        try:
            os.replace(tmp, path)
        except PermissionError:
            raise RuntimeError(path + " 를 바꿀 수 없습니다. 에뮬레이터에서 열려 있으면 닫고 다시 하세요.")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    log("완료(교체): " + path)


def cue_files(cue_path):
    names = []
    with open(cue_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip().upper().startswith("FILE "):
                names.append(line.strip().split('"')[1])
    return names


def patch_multibin(cue_path, log=print):
    """Redump 식 멀티 bin(트랙별 파일, 데이터 트랙 MODE1/2352): 트랙 2 파일만 패치하고 cue 를 새로 쓴다."""
    cue_path = os.path.abspath(cue_path)
    folder = os.path.dirname(cue_path)
    names = cue_files(cue_path)
    if len(names) < 2:
        raise RuntimeError("멀티 bin cue 로 보이지만 FILE 줄이 2개 미만입니다.")
    track2 = os.path.join(folder, names[1])
    if not os.path.exists(track2):
        raise FileNotFoundError("데이터 트랙 파일이 없습니다: " + track2)
    size = os.path.getsize(track2)
    # (v1.0) 0.3 부터 결과물이 원본과 크기가 같고 0.3·1.0 디스크는 내용도 같다 → 크기가 아니라 SHA-1 로 원본/이전 판/이번 판을 가른다
    if size not in (PREV_T2_SIZE, REDUMP_T2_SIZE):
        raise RuntimeError("데이터 트랙(Track 02) 크기가 Redump 기준과 다릅니다: {:,} B (기대 {:,} B).".format(size, REDUMP_T2_SIZE))
    log("데이터 트랙 체크섬 확인 중...")
    h2 = sha1(track2)
    if h2 == OUT_T2_SHA1:
        log("데이터 트랙은 이미 이번 판과 같습니다: 그대로 씁니다: " + track2)
        return cue_path
    if h2 == PREV_T2_SHA1:
        upgrade_inplace(track2, UPG_T2_PATCH, OUT_T2_SHA1, "데이터 트랙", log)
        log("cue 는 그대로 씁니다: " + cue_path)
        return cue_path
    if size != REDUMP_T2_SIZE or h2 != REDUMP_T2_SHA1:
        raise RuntimeError("데이터 트랙(Track 02)의 SHA-1 이 Redump 기준·" + PREV_LABEL + " 결과 어느 것과도 다릅니다.")
    missing = [n for n in names if not os.path.exists(os.path.join(folder, n))]
    if missing:
        raise RuntimeError("cue 가 가리키는 파일이 없습니다: " + ", ".join(missing[:3]))
    stem2, ext2 = os.path.splitext(names[1])
    out_t2 = os.path.join(folder, stem2 + "_KR" + ext2)
    stem_c = os.path.splitext(os.path.basename(cue_path))[0]
    out_cue = os.path.join(folder, stem_c + "_KR.cue")
    log("데이터 트랙 패치 적용 중...")
    run_xdelta(track2, find_file(T2_PATCH), out_t2)
    log("결과 검증 중...")
    if sha1(out_t2) != OUT_T2_SHA1:
        raise RuntimeError("데이터 트랙 패치 결과 검증 실패(SHA-1 불일치).")
    with open(cue_path, encoding="utf-8", errors="replace") as f:
        cue = f.read()
    new_cue = cue.replace('FILE "' + names[1] + '"', 'FILE "' + os.path.basename(out_t2) + '"', 1)
    if new_cue == cue:
        raise RuntimeError("cue 의 트랙 2 FILE 줄을 바꾸지 못했습니다.")
    with open(out_cue, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(new_cue)
    log("완료: " + out_t2)
    log("완료: " + out_cue + "  (다른 트랙 파일은 원본을 그대로 참조)")
    return out_cue


def patch_disc(src, log=print):
    src = os.path.abspath(src)
    if src.lower().endswith(".cue"):
        names = cue_files(src)
        if not names:
            raise RuntimeError("cue 에서 FILE 줄을 찾지 못했습니다.")
        if len(names) > 1:
            log("멀티 bin cue 감지 (트랙 파일 {}개)".format(len(names)))
            return patch_multibin(src, log)
        src = os.path.join(os.path.dirname(src), names[0])
    elif os.path.getsize(src) == REDUMP_T2_SIZE:
        raise RuntimeError("Redump 멀티 bin 덤프는 .bin 이 아니라 .cue 파일을 선택하세요.")
    if not os.path.exists(src):
        raise FileNotFoundError(src)
    size = os.path.getsize(src)
    if size not in (PREV_BIN_SIZE, ORIG_BIN_SIZE):
        raise RuntimeError("원본 .bin 크기가 다릅니다: {:,} B (기대 {:,} B). "
                           "단일 bin 덤프(cue 1개 + bin 1개)가 필요합니다.".format(size, ORIG_BIN_SIZE))
    log("디스크 체크섬 확인 중...")
    hb = sha1(src)   # (v1.0) 크기가 아니라 SHA-1 로 원본/이전 판/이번 판 구분(0.3 부터 결과물 크기 = 원본, 0.3·1.0 디스크 동일)
    if hb == OUT_BIN_SHA1:
        log("디스크는 이미 이번 판과 같습니다: 그대로 씁니다: " + src)
        out_cue = os.path.splitext(src)[0] + ".cue"
        if not os.path.exists(out_cue):
            with open(find_file(CUE_TEMPLATE), encoding="utf-8") as f:
                tpl = f.read()
            with open(out_cue, "w", encoding="utf-8", newline="\r\n") as f:
                f.write(tpl.replace("{BIN}", os.path.basename(src)))
        return out_cue
    if hb == PREV_BIN_SHA1:
        upgrade_inplace(src, UPG_DISC_PATCH, OUT_BIN_SHA1, "디스크", log)
        out_cue = os.path.splitext(src)[0] + ".cue"           # 트랙 위치가 바뀌었으므로 cue 도 새로 쓴다
        with open(find_file(CUE_TEMPLATE), encoding="utf-8") as f:
            tpl = f.read()
        with open(out_cue, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(tpl.replace("{BIN}", os.path.basename(src)))
        log("완료(cue 새로 씀): " + out_cue)
        return out_cue
    if size != ORIG_BIN_SIZE or hb != ORIG_BIN_SHA1:
        raise RuntimeError("원본 .bin 의 SHA-1 이 기준·" + PREV_LABEL + " 결과 어느 것과도 다릅니다. 지원하지 않는 덤프입니다.")
    stem = os.path.splitext(os.path.basename(src))[0]
    out_bin = os.path.join(os.path.dirname(src), stem + "_KR.bin")
    out_cue = os.path.join(os.path.dirname(src), stem + "_KR.cue")
    log("디스크 패치 적용 중... (수십 초)")
    run_xdelta(src, find_file(DISC_PATCH), out_bin)
    log("결과 검증 중...")
    if sha1(out_bin) != OUT_BIN_SHA1:
        raise RuntimeError("패치 결과 검증 실패(SHA-1 불일치).")
    with open(find_file(CUE_TEMPLATE), encoding="utf-8") as f:
        tpl = f.read()
    with open(out_cue, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(tpl.replace("{BIN}", os.path.basename(out_bin)))
    log("완료: " + out_bin)
    log("완료: " + out_cue)
    return out_cue


def patch_card(src, log=print):
    src = os.path.abspath(src)
    size = os.path.getsize(src)
    base = src
    tmp = None
    if size == ORIG_CARD_SIZE + 512:
        # 512B HuCard 헤더가 붙은 덤프 → 헤더를 뗀 임시 사본에 패치 (결과는 헤더 없는 256KB)
        with open(src, "rb") as f:
            body = f.read()[512:]
        if hashlib.sha1(body).hexdigest() != ORIG_CARD_SHA1:
            raise RuntimeError("헤더(512B)를 뗀 본체가 기준 시스템 카드와 다릅니다.")
        fd, tmp = tempfile.mkstemp(suffix=".pce")
        os.close(fd)
        with open(tmp, "wb") as f:
            f.write(body)
        base = tmp
        log("512B 헤더 덤프 감지 → 헤더를 제거하고 패치합니다.")
    elif size == ORIG_CARD_SIZE and sha1(src) == OUT_CARD_SHA1:
        log("시스템 카드는 이미 이번 판과 같습니다: 그대로 씁니다: " + src)
        return src
    elif size == ORIG_CARD_SIZE and sha1(src) == PREV_CARD_SHA1:
        upgrade_inplace(src, UPG_CARD_PATCH, OUT_CARD_SHA1, "시스템 카드", log)
        return src
    elif size != ORIG_CARD_SIZE or sha1(src) != ORIG_CARD_SHA1:
        raise RuntimeError("원본 시스템 카드가 기준(Super System Card 3.0 (J), 256KB 또는 헤더 포함 262,656B)과 다릅니다.")
    out = os.path.join(os.path.dirname(src), "SystemCard3_KR.pce")
    log("시스템 카드 패치 적용 중...")
    try:
        run_xdelta(base, find_file(CARD_PATCH), out)
    finally:
        if tmp:
            os.unlink(tmp)
    if sha1(out) != OUT_CARD_SHA1:
        raise RuntimeError("카드 패치 결과 검증 실패.")
    log("완료: " + out)
    return out


def make_config(emu_exe, card_path):
    emu_dir = os.path.dirname(os.path.abspath(emu_exe))
    base = os.path.join(emu_dir, "config.ini")
    cfg = {}
    if os.path.exists(base):
        try:
            with open(base, encoding="utf-8-sig") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg.setdefault("FirmwareUserSpecifications", {})["PCECD+Bios"] = os.path.abspath(card_path)
    cfg.setdefault("PreferredCores", {})["PCECD"] = "TurboNyma"
    out = os.path.join(emu_dir, CONFIG_NAME)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return out


GAMEDB_FILE = os.path.join("gamedb", "gamedb_pce_hucards.txt")
GAMEDB_NAME = "Super CD-ROM2 System V3.00 (J) [Tenshi no Uta II KR]"


def add_gamedb(emu_exe, card_path, log=print):
    """BizHawk 의 PCEHawk 코어는 gamedb 에 MD5 로 등록된 카드에만 Super System Card 추가 RAM(SuperSysCard)을 켠다.
    한글 카드는 해시가 달라 미등록 → 추가 RAM 없이 돌아 필드 화면이 깨진다(시작 때 '알 수 없는 BIOS' 경고도 같은 이유).
    상태 칸 = H(해킹) — V 는 BizHawk 에서 BadDump(「알려진 배드 덤프」 경고)라 쓰면 안 된다.
    → 그 BizHawk 의 gamedb_pce_hucards.txt 에 한글 카드 MD5 한 줄을 넣는다(처음 한 번 원본을 .bak_tenshi2kr 로 백업). TurboNyma 코어에는 영향 없음."""
    db = os.path.join(os.path.dirname(os.path.abspath(emu_exe)), GAMEDB_FILE)
    if not os.path.exists(db):
        log("참고: " + db + " 이 없어 PCEHawk 용 등록은 건너뜁니다(TurboNyma 코어는 상관없음).")
        return None
    h = hashlib.md5()
    with open(card_path, "rb") as f:
        h.update(f.read())
    md5 = h.hexdigest().upper()
    with open(db, "rb") as f:
        raw = f.read()
    # 상태 칸은 H(해킹). 0.3 패처는 V 를 썼는데 BizHawk 에서 V = BadDump 라 「알려진 배드 덤프」 경고가 떴다(2026-10-14) → 이미 있는 V 줄도 H 로 고친다
    bad = (md5 + "\tV\t" + GAMEDB_NAME).encode("utf-8")
    if bad in raw:
        with open(db, "wb") as f:
            f.write(raw.replace(bad, (md5 + "\tH\t" + GAMEDB_NAME).encode("utf-8")))
        log("BizHawk gamedb 의 한글 카드 줄 상태를 고쳤습니다(V → H, 배드 덤프 경고 제거).")
        return db
    if md5.encode("ascii") in raw.upper():
        log("BizHawk gamedb 에 한글 카드가 이미 등록돼 있습니다.")
        return db
    bak = db + ".bak_tenshi2kr"
    if not os.path.exists(bak):
        with open(bak, "wb") as f:
            f.write(raw)
    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    line = (md5 + "\tH\t" + GAMEDB_NAME + "\tPCE\t\tBRAM;SuperSysCard;BIOS").encode("utf-8")
    with open(db, "wb") as f:
        f.write(raw.rstrip(b"\r\n") + nl + line + nl)
    log("BizHawk gamedb 에 한글 카드 등록(PCEHawk 코어용): " + db)
    return db


def _ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def make_shortcut(lnk_path, target, args, workdir, icon):
    ps = "\n".join([
        "$ws = New-Object -ComObject WScript.Shell",
        "$s = $ws.CreateShortcut(" + _ps_quote(lnk_path) + ")",
        "$s.TargetPath = " + _ps_quote(target),
        "$s.Arguments = " + _ps_quote(args),
        "$s.WorkingDirectory = " + _ps_quote(workdir),
        "$s.IconLocation = " + _ps_quote(icon + ",0"),
        "$s.Save()",
    ])
    fd, tmp = tempfile.mkstemp(suffix=".ps1")
    os.close(fd)
    with open(tmp, "w", encoding="utf-8-sig") as f:
        f.write(ps)
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp],
                           capture_output=True, text=True, creationflags=NO_WINDOW)
    finally:
        os.unlink(tmp)
    if r.returncode != 0 or not os.path.exists(lnk_path):
        raise RuntimeError("바로가기 생성 실패:\n" + (r.stderr or r.stdout))


def make_launcher(emu_exe, cue_path, card_path, shortcut_dir=None, log=print):
    for p, what in ((emu_exe, "EmuHawk.exe"), (cue_path, "패치된 .cue"), (card_path, "패치된 시스템 카드")):
        if not p or not os.path.exists(p):
            raise FileNotFoundError(what + " 경로가 없습니다: " + str(p))
    cfg = make_config(emu_exe, card_path)
    log("전용 설정 생성: " + cfg)
    add_gamedb(emu_exe, card_path, log)
    args = '"' + os.path.abspath(cue_path) + '" --config="' + cfg + '"'
    if shortcut_dir:
        dirs = [shortcut_dir]
    else:
        dirs = [os.path.join(os.path.expanduser("~"), "Desktop"), os.path.dirname(os.path.abspath(cue_path))]
    made = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        lnk = os.path.join(d, SHORTCUT_NAME)
        make_shortcut(lnk, os.path.abspath(emu_exe), args,
                      os.path.dirname(os.path.abspath(emu_exe)), os.path.abspath(emu_exe))
        made.append(lnk)
        log("바로가기 생성: " + lnk)
    return made


def gui(selftest=False):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    try:
        from tkinterdnd2 import TkinterDnD, DND_FILES
        root = TkinterDnD.Tk()
        dnd_ok = True
    except Exception:
        root = tk.Tk()
        dnd_ok = False
    root.title(APP_TITLE)
    root.geometry("800x600")
    root.resizable(False, False)
    txt = tk.Text(root, height=12, wrap="word", state="disabled", cursor="arrow")

    def log(s):
        txt.configure(state="normal")
        txt.insert("end", s + "\n")
        txt.see("end")
        txt.configure(state="disabled")
        root.update()

    def guard(fn):
        def w(*a):
            try:
                fn(*a)
            except Exception as e:
                log("오류: " + str(e))
                messagebox.showerror("오류", str(e))
        return w

    def dropped_path(event):
        paths = root.tk.splitlist(event.data)
        return paths[0] if paths else ""

    def make_row(parent, row, label, var, button_text, on_pick, on_drop, pady=0):
        ttk.Label(parent, text=label, wraplength=760).grid(row=row, column=0, columnspan=2, sticky="w", pady=(pady, 0))
        ent = ttk.Entry(parent, textvariable=var, width=82, state="readonly")
        ent.grid(row=row + 1, column=0, sticky="w")
        ttk.Button(parent, text=button_text, command=guard(on_pick)).grid(row=row + 1, column=1, padx=6)
        if dnd_ok:
            ent.drop_target_register(DND_FILES)
            ent.dnd_bind("<<Drop>>", guard(lambda e: on_drop(dropped_path(e))))
        return ent

    frm = ttk.Frame(root, padding=10)
    frm.pack(fill="x")
    v_cue, v_card, v_emu = tk.StringVar(), tk.StringVar(), tk.StringVar()
    hint = " (파일을 이 칸에 끌어다 놓아도 됩니다)" if dnd_ok else ""

    def pick_disc():
        p = filedialog.askopenfilename(title="원본 디스크 이미지", filetypes=[("디스크 이미지", "*.cue *.bin"), ("모든 파일", "*.*")])
        if p:
            v_cue.set(p)

    def pick_card():
        p = filedialog.askopenfilename(title="원본 시스템 카드", filetypes=[("PCE 시스템 카드", "*.pce *.bin *.rom"), ("모든 파일", "*.*")])
        if p:
            v_card.set(p)

    def pick_emu():
        p = filedialog.askopenfilename(title="EmuHawk.exe", filetypes=[("EmuHawk", "EmuHawk.exe"), ("실행 파일", "*.exe")])
        if p:
            v_emu.set(p)

    make_row(frm, 0, "1. 원본 디스크 이미지 .cue (단일 bin 또는 Redump 멀티 bin) — v1.0/v0.3 으로 패치해 둔 *_KR.cue 를 지정하면 v1.0.1 로 올립니다" + hint, v_cue, "선택", pick_disc, v_cue.set)
    make_row(frm, 2, "2. 원본 시스템 카드 PCECD_3.0-(J).pce (256KB, 헤더 포함 262,656B 도 가능) — v1.0/v0.3 의 SystemCard3_KR.pce 도 가능" + hint, v_card, "선택", pick_card, v_card.set, pady=10)
    make_row(frm, 4, "3. BizHawk - EmuHawk.exe (선택 사항: 지정하면 한글판 바로가기를 바탕화면·게임 폴더에 만듭니다)" + hint, v_emu, "선택", pick_emu, v_emu.set, pady=10)

    def run_all():
        disc, card, emu = v_cue.get().strip(), v_card.get().strip(), v_emu.get().strip()
        if not disc or not card:
            raise RuntimeError("1번(디스크 이미지)과 2번(시스템 카드)을 모두 지정한 뒤 패치하세요.")
        btn.configure(state="disabled")
        try:
            log("=== 패치 시작 ===")
            out_cue = patch_disc(disc, log)
            out_card = patch_card(card, log)
            if emu:
                make_launcher(emu, out_cue, out_card, None, log)
            log("=== 모두 완료 ===")
            if emu:
                tail = "\n바탕화면의 '천사의 시 II 한글판' 바로가기로 실행하세요."
            else:
                tail = ("\n에뮬레이터에서 " + os.path.basename(out_cue) + " 를 열고, PC엔진 CD 시스템 카드(BIOS)를 "
                        + os.path.basename(out_card) + " 로 지정하세요. (BizHawk·Mednafen·RetroArch Beetle PCE 등, README 참고)")
            messagebox.showinfo("완료", "패치가 끝났습니다." + tail)
        finally:
            btn.configure(state="normal")

    btn = ttk.Button(frm, text="패치 + 바로가기 만들기", command=guard(run_all))
    btn.grid(row=6, column=0, columnspan=2, pady=(16, 4), ipadx=20, ipady=4)
    ttk.Label(root, text="진행 상황", padding=(10, 8, 0, 0)).pack(anchor="w")
    txt.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    log("기준: 원본 bin SHA-1 " + ORIG_BIN_SHA1 + " (523,184,384 B) 또는 Redump Track 02, 시스템 카드 Super System Card 3.0 (J).")
    log(PREV_LABEL + " 패치 결과물(*_KR.cue / SystemCard3_KR.pce)을 지정하면 그 파일을 이번 판으로 교체합니다(이름 그대로: 세이브 유지).")
    if not dnd_ok:
        log("(끌어다 놓기 모듈을 불러오지 못해 버튼 선택만 됩니다)")
    if selftest:
        root.after(800, lambda: (log("selftest dnd=" + str(dnd_ok)), root.destroy()))
    root.mainloop()
    return dnd_ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--disc")
    ap.add_argument("--card")
    ap.add_argument("--emu")
    ap.add_argument("--cue")
    ap.add_argument("--card-out")
    ap.add_argument("--shortcut-dir")
    ap.add_argument("--selftest-gui", action="store_true")
    a = ap.parse_args()
    if a.selftest_gui:
        ok = gui(selftest=True)
        print("GUI selftest ok, dnd=" + str(ok))
        return
    if not any((a.disc, a.card, a.emu)):
        return gui()
    cue, card = a.cue, a.card_out
    if a.disc:
        cue = patch_disc(a.disc)
    if a.card:
        card = patch_card(a.card)
    if a.emu:
        make_launcher(a.emu, cue, card, a.shortcut_dir)


if __name__ == "__main__":
    main()
