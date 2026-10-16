# -*- coding: utf-8 -*-
import os
import json
from PIL import Image, ImageFont, ImageDraw

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tsv_path = os.path.join(GAME_DIR, "translation", "script_sheet.tsv")
ttf_path = os.path.join(GAME_DIR, "font", "Galmuri11-Condensed.ttf")
out_bin_path = os.path.join(GAME_DIR, "translation", "font_data.bin")
out_map_path = os.path.join(GAME_DIR, "translation", "char_map.json")

# 1. Collect all unique Hangul characters from script_sheet.tsv translation column and count frequencies
import collections
char_counts = collections.Counter()
with open(tsv_path, "r", encoding="utf-8-sig") as f:
    header = f.readline()
    for line in f:
        cols = line.rstrip("\n").split("\t")
        if len(cols) > 4:
            translation = cols[4].strip()
            for ch in translation:
                if '가' <= ch <= '힣':
                    char_counts[ch] += 1

# Sort by frequency (descending), then alphabetically to ensure deterministic order
sorted_chars = sorted(char_counts.keys(), key=lambda c: (-char_counts[c], c))

# Limit to 896 characters (4 banks * 224 slots)
LIMIT = 896
hangul_chars = sorted(sorted_chars[:LIMIT])
discarded = sorted_chars[LIMIT:]
print(f"Total unique Hangul characters found: {len(char_counts)}")
print(f"Keeping top {len(hangul_chars)} characters.")
if discarded:
    print(f"Discarded {len(discarded)} rare characters: {''.join(discarded)}")

# 2. Map Hangul characters to custom SJIS lead/trail bytes (0xEB20 to 0xEEFF)
# Lead bytes: 0xEB, 0xEC, 0xED, 0xEE (4 banks)
# Trail bytes: 0x20 to 0xFF (224 valid low bytes per bank)
char_map = {}
lead_bytes = [0xEB, 0xEC, 0xED, 0xEE]
trail_min, trail_max = 0x20, 0xFF
slots_per_bank = trail_max - trail_min + 1  # 224

# Let's assign mapping
for idx, ch in enumerate(hangul_chars):
    bank_idx = idx // slots_per_bank
    offset = idx % slots_per_bank
    if bank_idx >= len(lead_bytes):
        raise ValueError(f"Too many Hangul characters! Exceeds maximum slots ({len(lead_bytes) * slots_per_bank})")
    
    high = lead_bytes[bank_idx]
    low = trail_min + offset
    char_map[ch] = f"{high:02X}{low:02X}"

with open(out_map_path, "w", encoding="utf-8") as f:
    json.dump(char_map, f, ensure_ascii=False, indent=2)
print(f"Character mapping table saved to: {out_map_path}")

# 3. Load font and render glyphs into binary buffer
font = ImageFont.truetype(ttf_path, 11)

# Buffer size: 5 banks * 8192 bytes/bank = 40960 bytes
font_data = bytearray(len(lead_bytes) * 8192)

for ch, code_str in char_map.items():
    high = int(code_str[0:2], 16)
    low = int(code_str[2:4], 16)
    
    # Render character to 16x16 monochrome image
    img = Image.new("1", (16, 16), 0)
    draw = ImageDraw.Draw(img)
    
    # Calculate width of glyph for horizontal centering within 12px
    mask = font.getmask(ch)
    w, h = mask.size
    x_offset = max(0, (12 - w) // 2)
    y_offset = 1  # Standard baseline offset
    
    draw.text((x_offset, y_offset), ch, font=font, fill=1)
    
    # Convert image pixels to 32 bytes (16 rows * 2 bytes/row, MSB-first)
    pixels = img.load()
    glyph_bytes = bytearray(32)
    for y in range(16):
        b1, b2 = 0, 0
        for x in range(8):
            if pixels[x, y]:
                b1 |= (1 << (7 - x))
        for x in range(8, 16):
            if pixels[x, y]:
                b2 |= (1 << (15 - x))
        glyph_bytes[y*2] = b1
        glyph_bytes[y*2 + 1] = b2
        
    # Write to correct position in buffer
    bank_idx = high - 0xEB
    offset_in_bank = low * 32
    buffer_idx = bank_idx * 8192 + offset_in_bank
    
    font_data[buffer_idx : buffer_idx + 32] = glyph_bytes

# Save compiled font data
with open(out_bin_path, "wb") as f:
    f.write(font_data)

print(f"Hangul font compiled successfully: {out_bin_path} ({len(font_data)} bytes)")
