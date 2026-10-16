# -*- coding: utf-8 -*-
r"""전체 패치 빌드 파이프라인 (bin/cue 기준).

  1) generate_font.py   → translation/font_data.bin, char_map.json
  2) patch_iso.py       → extracted_bin/Track02_data_patched.iso
  3) 원본 .bin 복사 후 데이터 트랙(offset 7,914,480)에 패치 ISO 오버레이 → *_patched.bin
  4) xdelta3 로 원본→패치 델타 생성 → *_Korean_Translation.xdelta

데이터 트랙이 MODE1/2048 이라 EDC/ECC 재계산 불필요, 물리 레이아웃 1:1 유지.
"""
import os, sys, shutil, subprocess, runpy

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(GAME_DIR, "tools")

ORIG_BIN   = os.path.join(GAME_DIR, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin")
PATCHED_BIN= os.path.join(GAME_DIR, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_patched.bin")
PATCHED_ISO= os.path.join(GAME_DIR, "extracted_bin", "Track02_data_patched.iso")
XDELTA_OUT = os.path.join(GAME_DIR, "Tenshi_no_Uta_II_Korean_Translation.xdelta")
XDELTA_EXE = os.path.join(TOOLS, "xdelta3-3.2.0-windows-x86_64", "xdelta3.exe")

DATA_TRACK_OFFSET = 7914480       # bin 내 데이터 트랙 시작 (LBA 3365 * 2352? no → MODE1/2048)
DATA_TRACK_BYTES  = 9328 * 2048   # 19,103,744


def run_step(name, path):
    print(f"\n=== {name} ===")
    runpy.run_path(path, run_name="__main__")


def main():
    # 1) 폰트 재생성 (script_sheet 최신 번역 반영)
    run_step("1/4 generate_font.py", os.path.join(TOOLS, "generate_font.py"))

    # 2) ISO 패치
    run_step("2/4 patch_iso.py", os.path.join(TOOLS, "patch_iso.py"))

    # 3) 패치 ISO를 원본 bin 사본의 데이터 트랙에 오버레이
    #    정식 patched.bin 이 잠겨있을 수 있으므로 임시 파일에 먼저 빌드
    print("\n=== 3/4 build patched .bin ===")
    with open(PATCHED_ISO, "rb") as f:
        iso = f.read()
    assert len(iso) == DATA_TRACK_BYTES, f"패치 ISO 크기 이상: {len(iso)} != {DATA_TRACK_BYTES}"

    orig_size = os.path.getsize(ORIG_BIN)
    tmp_bin = PATCHED_BIN + ".tmp"
    with open(ORIG_BIN, "rb") as f:
        a = bytearray(f.read())
    a[DATA_TRACK_OFFSET:DATA_TRACK_OFFSET + DATA_TRACK_BYTES] = iso
    with open(tmp_bin, "wb") as f:
        f.write(a)
    assert os.path.getsize(tmp_bin) == orig_size, "패치 bin 크기가 원본과 다름!"

    with open(ORIG_BIN, "rb") as f:
        orig = f.read()
    diff = sum(1 for i in range(0, len(orig), 2048) if orig[i:i+2048] != a[i:i+2048])
    print(f"  임시 patched bin 빌드: {tmp_bin} ({orig_size} bytes, 변경 2KB 블록 {diff}개)")

    # 잠금 안 걸렸으면 정식 파일명으로 승격
    build_target = tmp_bin
    try:
        os.replace(tmp_bin, PATCHED_BIN)
        build_target = PATCHED_BIN
        print(f"  정식 파일로 배치: {PATCHED_BIN}")
    except PermissionError:
        print(f"  [주의] {os.path.basename(PATCHED_BIN)} 가 다른 프로그램에 잠겨 있어")
        print(f"         임시 파일 {os.path.basename(tmp_bin)} 로 유지합니다.")
        print(f"         에뮬레이터를 닫은 뒤 이 파일을 {os.path.basename(PATCHED_BIN)} 로 바꾸세요.")
    PATCHED_FOR_DELTA = build_target

    # 4) xdelta 생성 (원본 → 패치)
    print("\n=== 4/4 xdelta3 encode ===")
    if os.path.exists(XDELTA_OUT):
        try:
            os.remove(XDELTA_OUT)
        except PermissionError:
            pass
    cmd = [XDELTA_EXE, "-e", "-9", "-f", "-s", ORIG_BIN, PATCHED_FOR_DELTA, XDELTA_OUT]
    print("  " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"  xdelta 생성: {XDELTA_OUT} ({os.path.getsize(XDELTA_OUT)} bytes)")

    # 검증: 원본에 xdelta 적용 → 패치 bin 과 동일한지
    print("\n=== verify: 원본 + xdelta == 패치 bin ===")
    test_out = os.path.join(GAME_DIR, "_verify_patched.bin")
    subprocess.run([XDELTA_EXE, "-d", "-f", "-s", ORIG_BIN, XDELTA_OUT, test_out], check=True)
    with open(test_out, "rb") as f1, open(PATCHED_FOR_DELTA, "rb") as f2:
        ok = f1.read() == f2.read()
    os.remove(test_out)
    print("  검증:", "OK (원본에 패치 적용 시 patched bin 재현)" if ok else "실패!!")
    if not ok:
        sys.exit(1)

    print("\n완료. 배포 파일:")
    print(f"  - {os.path.basename(XDELTA_OUT)}  (원본 .bin 에 적용)")
    print(f"  - {os.path.basename(PATCHED_FOR_DELTA)} (직접 테스트용, patched.cue 로 로드)")


if __name__ == "__main__":
    main()
