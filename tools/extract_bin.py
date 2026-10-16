# -*- coding: utf-8 -*-
r"""bin/cue 원본에서 트랙 추출 → extracted_bin/

이 bin은 트랙2가 MODE1/2048(유저데이터만)로 저장되어 있어
- 데이터 트랙 = extracted/Track02_data.iso 와 1:1 (postgap 150섹터만 없음)
- 패치 시 EDC/ECC 재계산 불필요
- 데이터 트랙의 bin 내 파일 오프셋 = 7,914,480 + (ISO 섹터 × 2048)
"""
import os, re, struct

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(GAME_DIR, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin")
CUE = os.path.join(GAME_DIR, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue")
OUT = os.path.join(GAME_DIR, "extracted_bin")
os.makedirs(OUT, exist_ok=True)

# ---- cue 파싱 ---------------------------------------------------------------
tracks = []   # (num, type, index_frame)
for line in open(CUE, encoding="ascii", errors="replace"):
    m = re.match(r"\s*TRACK (\d+) (\S+)", line)
    if m:
        tracks.append([int(m.group(1)), m.group(2), None])
        continue
    m = re.match(r"\s*INDEX 01 (\d+):(\d+):(\d+)", line)
    if m:
        mm, ss, ff = map(int, m.groups())
        tracks[-1][2] = (mm * 60 + ss) * 75 + ff

SIZE = {"AUDIO": 2352, "MODE1/2048": 2048, "MODE1/2352": 2352}
fsize = os.path.getsize(BIN)

# 프레임 → 파일 오프셋: 트랙별 섹터 크기가 섞여 있으므로 누적 계산
total_frames = tracks[-1][2]
# 마지막 트랙 길이 역산을 위해 전체 프레임 수 계산
offset = 0
bounds = []   # (num, type, file_offset, n_sectors)
for i, (num, typ, frame) in enumerate(tracks):
    next_frame = tracks[i + 1][2] if i + 1 < len(tracks) else None
    if next_frame is not None:
        n = next_frame - frame
    else:
        n = (fsize - offset) // SIZE[typ]
    bounds.append((num, typ, offset, n))
    offset += n * SIZE[typ]

assert offset + (0 if bounds[-1][3] else 0) <= fsize
print(f"bin size check: computed end {offset} vs file {fsize} -> {'OK' if offset == fsize else 'MISMATCH'}")

def wav_header(pcm_len):
    return (b"RIFF" + struct.pack("<I", 36 + pcm_len) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 2, 44100, 176400, 4, 16) +
            b"data" + struct.pack("<I", pcm_len))

f = open(BIN, "rb")
for num, typ, off, n in bounds:
    f.seek(off)
    if typ == "MODE1/2048":
        path = os.path.join(OUT, f"Track{num:02d}_data.iso")
        with open(path, "wb") as o:
            remain = n * 2048
            while remain:
                chunk = f.read(min(remain, 1 << 20))
                o.write(chunk); remain -= len(chunk)
        print(f"Track {num:02d}: DATA  {n:6d} sectors (2048B)  file_off={off}")
    else:
        path = os.path.join(OUT, f"Track{num:02d}_audio.wav")
        pcm = n * 2352
        with open(path, "wb") as o:
            o.write(wav_header(pcm))
            remain = pcm
            while remain:
                chunk = f.read(min(remain, 1 << 20))
                o.write(chunk); remain -= len(chunk)
        print(f"Track {num:02d}: AUDIO {n:6d} sectors")
f.close()

# ---- 검증: 기존 img 추출본과 데이터 트랙 비교 ---------------------------------
old = os.path.join(GAME_DIR, "extracted", "Track02_data.iso")
new = os.path.join(OUT, "Track02_data.iso")
if os.path.exists(old):
    a = open(old, "rb").read()
    b = open(new, "rb").read()
    same = a[:len(b)] == b
    tail_zero = all(c == 0 for c in a[len(b):])
    print(f"\nverify vs extracted/Track02_data.iso:")
    print(f"  first {len(b)} bytes identical: {same}")
    print(f"  img-side extra tail ({len(a)-len(b)} bytes) all zero: {tail_zero}")
    print(f"  -> 기존 분석 오프셋(번역 키) 유효: {'YES' if same else 'NO!!'}")
print(f"\n데이터 트랙 bin 패치 공식: bin_offset = 7,914,480 + iso_offset (iso_offset < {9328*2048})")
