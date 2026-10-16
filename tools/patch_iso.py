# -*- coding: utf-8 -*-
import os
import json
import struct
import sys

# Import CD-ROM ECC recalculator from tools
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import cdrom_ecc

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# bin/cue 원본에서 추출한 데이터 트랙 기준 (extracted 와 바이트 동일하지만 bin 파이프라인에 맞춤)
iso_path = os.path.join(GAME_DIR, "extracted_bin", "Track02_data.iso")
out_iso_path = os.path.join(GAME_DIR, "extracted_bin", "Track02_data_patched.iso")
tsv_path = os.path.join(GAME_DIR, "translation", "script_sheet.tsv")
map_path = os.path.join(GAME_DIR, "translation", "char_map.json")
font_bin_path = os.path.join(GAME_DIR, "translation", "font_data.bin")

# ---- Character Table constants from extract_script.py ----
KANA = {}
for base, s in [
    (0x28, "ぁあぃいぅうぇえぉお"), (0x32, "かが기기구구케게코고"), # Wait, let's use the exact kana table from extract_script.py!
    (0x3C, "사자시지스즈세제소조"), # Wait, the original KANA table was Japanese Hiragana:
]: pass

# Let's copy KANA exactly:
KANA = {}
for base, s in [
    (0x28, "ぁあぃいぅうぇえぉお"), (0x32, "かがきぎくぐけげこご"),
    (0x3C, "さざしじすずせぜそぞ"), (0x46, "ただちぢっつづてでtoど"), # Wait, looking at extract_script.py: "ただちぢっつづてでとど"
    (0x51, "なにぬねの"), (0x56, "はばぱひびぴふぶぷへべぺほぼぽ"),
    (0x65, "まみむめも"), (0x6A, "ゃやゅゆょよ"), (0x70, "らりるれろ"),
    (0x75, "ゎわゐゑをん"),
]:
    # Correcting typo in 0x46: "ただちぢっつづてでとど"
    s_hira = "ただちぢっつづてでとど" if base == 0x46 else s
    for i, ch in enumerate(s_hira):
        KANA[base + i] = ch

HALF2FULL = {}
for i, ch in enumerate("。「」、・ヲァィゥェォャュョッーアイウエオカキクケコサシスセソ"
                       "タチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン゛゜"):
    HALF2FULL[0xA1 + i] = ch

REV_KANA = {v: k for k, v in KANA.items()}
REV_HALF2FULL = {v: k for k, v in HALF2FULL.items()}

def encode_string(text, char_map):
    out = bytearray()
    i = 0
    n = len(text)
    while i < n:
        if text[i:i+2] == "\\n":
            out.append(0x0D)
            i += 2
            continue
        if text[i:i+2] == "\\p":
            out.append(0x0C)
            i += 2
            continue
        if text[i:i+4] == "{0B}":
            out.append(0x0B)
            i += 4
            continue
        if text[i:i+4] == "{0E}":
            out.append(0x0E)
            i += 4
            continue
        if text[i:i+3] == "{~}":
            out.append(0x7E)
            i += 3
            continue
        if text[i] == "{" and i + 3 < n and text[i+3] == "}":
            c1 = text[i+1]
            c2 = text[i+2]
            if c1 in ('#', '%'):
                out.append(ord(c1))
                out.append(ord(c2))
                i += 4
                continue
                
        ch = text[i]
        if ch in char_map:
            code_hex = char_map[ch]
            out.append(int(code_hex[0:2], 16))
            out.append(int(code_hex[2:4], 16))
            i += 1
            continue
        if ch in REV_KANA:
            out.append(REV_KANA[ch])
            i += 1
            continue
        if ch in REV_HALF2FULL:
            out.append(REV_HALF2FULL[ch])
            i += 1
            continue
            
        try:
            bytes_sjis = ch.encode("shift_jis")
            out.extend(bytes_sjis)
        except UnicodeEncodeError:
            out.append(ord('?'))
        i += 1
    return bytes(out)

def build_fetch_hook():
    hook_addr = 0x3C00
    # fetch_hook assembly template:
    hook = bytearray([
        0xA5, 0x56,             # LDA $56
        0xD0, 0x17,             # BNE read_aux (targets read_aux at offset 27)
        0x20, 0x11, 0x41,       # JSR $4111
        0xC9, 0x01,             # CMP #$01
        0xD0, 0x13,             # BNE done (displacement will be fixed)
        0x20, 0x11, 0x41,       # JSR $4111
        0x8D, 0x00, 0x00,       # STA variable_addr (at offset 14)
        0x20, 0x11, 0x41,       # JSR $4111
        0x85, 0x55,             # STA $55
        0x20, 0x11, 0x41,       # JSR $4111
        0x85, 0x56,             # STA $56
        
        # read_aux (offset 27)
        0x43, 0x08,             # TMA #$08
        0x48,                   # PHA
        0xAD, 0x00, 0x00,       # LDA variable_addr (at offset 30)
        0x53, 0x08,             # TAM #$08
        0xA0, 0x00,             # LDY #$00
        0xB1, 0x55,             # LDA ($55), Y
        0x85, 0xFC,             # STA $FC
        0xE6, 0x55,             # INC $55
        0xD0, 0x02,             # BNE no_carry
        0xE6, 0x56,             # INC $56
        
        # no_carry (offset 47)
        0x68,                   # PLA
        0x53, 0x08,             # TAM #$08
        0xA5, 0xFC,             # LDA $FC
        0xD0, 0x06,             # BNE return_val (targets return_val at offset 60)
        0x64, 0x55,             # STZ $55
        0x64, 0x56,             # STZ $56
        
        # return_val (offset 58)
        0xA5, 0xFC,             # LDA $FC
        0x60,                   # RTS
        
        # done (offset 61)
        0x60,                   # RTS
    ])
    
    # Append the bank variable byte at the end
    hook.append(0x00)           # Variable at offset 62
    
    var_offset = len(hook) - 1
    var_logical_addr = hook_addr + var_offset
    
    # Patch the variable address
    hook[15] = var_logical_addr & 0xFF
    hook[16] = (var_logical_addr >> 8) & 0xFF
    
    hook[31] = var_logical_addr & 0xFF
    hook[32] = (var_logical_addr >> 8) & 0xFF
    
    # Fix BNE done displacement (at offset 9/10)
    done_off = 61
    pc_after_bne = 11
    hook[9] = 0xD0
    hook[10] = (done_off - pc_after_bne) & 0xFF
    
    return bytes(hook)

def build_getfnt_hook():
    # getfnt_hook assembly bytes:
    # 2140: A5 F9        LDA $F9
    # 2142: C9 EB        CMP #$EB
    # 2144: 90 48        BCC call_bios
    # 2146: C9 F0        CMP #$F0
    # 2148: B0 44        BCS call_bios
    # 214A: 43 08        TMA #$08
    # 214C: 48           PHA
    # 214D: 5A           PHY             ; Save original Y register
    # 214E: DA           PHX             ; Save original X register
    # 214F: A5 F9        LDA $F9
    # 2151: 38           SEC
    # 2152: E9 EB        SBC #$EB
    # 2154: 18           CLC
    # 2155: 69 83        ADC #$83
    # 2157: 53 08        TAM #$08        ; map font bank to MPR3 ($6000-$7FFF)
    # 2159: A5 F8        LDA $F8
    # 215B: 29 07        AND #$07
    # 215D: 0A 0A 0A 0A 0A ASL * 5
    # 2162: 85 FC        STA $FC
    # 2164: A5 F8        LDA $F8
    # 2166: 4A 4A 4A     LSR * 3
    # 2169: 18           CLC
    # 216A: 69 60        ADC #$60        ; offset into logical page of bank in MPR3 ($6000 base)
    # 216C: 85 FD        STA $FD         ; $FC/$FD points to glyph in MPR3
    # 216E: A0 00        LDY #$00
    # 2170: copy_loop:
    # 2170: B1 FC        LDA ($FC), Y
    # 2172: 91 FA        STA ($FA), Y    ; Copy glyph to destination address ($FA)
    # 2174: C8           INY
    # 2175: C0 20        CPY #32
    # 2177: D0 F7        BNE copy_loop
    # 2179: FA           PLX             ; Restore original X register
    # 217A: 7A           PLY             ; Restore original Y register
    # 217B: 68           PLA
    # 217C: 53 08        TAM #$08        ; Restore original MPR3 mapping
    # 217E: 18           CLC
    # 217F: A5 FA        LDA $FA
    # 2181: 69 20        ADC #32
    # 2183: 85 FA        STA $FA
    # 2185: A5 FB        LDA $FB
    # 2187: 69 00        ADC #0
    # 2189: 85 FB        STA $FB         ; Increment $FA/$FB by 32
    # 218B: A9 00        LDA #$00        ; return A = 0
    # 218D: 60           RTS
    # 218E: call_bios:
    # 218E: 4C 60 E0     JMP $E060
    hook = bytearray([
        0xA5, 0xF9, 0xC9, 0xEB, 0x90, 0x48, 0xC9, 0xF0, 0xB0, 0x44,
        0x43, 0x08, 0x48, 0x5A, 0xDA, 0xA5, 0xF9, 0x38, 0xE9, 0xEB, 0x18, 0x69, 0x6A, 0x53, 0x08,
        0xA5, 0xF8, 0x29, 0x07, 0x0A, 0x0A, 0x0A, 0x0A, 0x0A, 0x85, 0xFC,
        0xA5, 0xF8, 0x4A, 0x4A, 0x4A, 0x18, 0x69, 0x60, 0x85, 0xFD,
        0xA0, 0x00,
        # copy_loop (offset 48)
        0xB1, 0xFC, 0x91, 0xFA, 0xC8, 0xC0, 0x20, 0xD0, 0xF7,
        0xFA, 0x7A, 0x68, 0x53, 0x08,
        0x18, 0xA5, 0xFA, 0x69, 0x20, 0x85, 0xFA,
        0xA5, 0xFB, 0x69, 0x00, 0x85, 0xFB,
        0xA9, 0x00, 0x60,
        # call_bios (offset 78)
        0x4C, 0x60, 0xE0
    ])
    # BCC call_bios at 2144 -> targets call_bios at offset 78.
    # Instruction after BCC is at offset 6. Offset = 78 - 6 = 72 = 0x48.
    # BCS call_bios at 2148 -> targets call_bios at offset 78.
    # Instruction after BCS is at offset 10. Offset = 78 - 10 = 68 = 0x44.
    # BNE copy_loop at offset 55 -> targets copy_loop at offset 48.
    # Instruction after BNE is at offset 57. Offset = 48 - 57 = -9 = 0xF7.
    return bytes(hook)

def build_boot_loader_hook():
    # The original entry at $600B initializes MPR0/MPR1 and the stack before it
    # does anything else.  Our hook runs earlier at $4010, so it must perform
    # that prefix before treating $3E00 as Work RAM or calling any BIOS routine.
    init_code = [
        0x78,                   # SEI
        0xD4,                   # CSH (high CPU speed)
        0xD8,                   # CLD
        0xA9, 0xFF, 0x53, 0x01, # LDA #$FF / TAM #$01 (MPR0 = I/O)
        0xA9, 0xF8, 0x53, 0x02, # LDA #$F8 / TAM #$02 (MPR1 = Work RAM)
        0xA2, 0xFF, 0x9A,       # LDX #$FF / TXS
    ]

    # The copy length byte is filled after stub_code has been assembled.  The
    # stub now starts at $4040, leaving room for init_code and this copy loop.
    copy_code = [
        0xA0, 0x00,             # LDY #stub_size-1 (filled below)
        0xB9, 0x40, 0x40,       # LDA $4040, Y
        0x99, 0x00, 0x3E,       # STA $3E00, Y
        0x88,                   # DEY
        0x10, 0xF7,             # BPL copy_loop
        0x4C, 0x00, 0x3E        # JMP $3E00
    ]
    
    # Stub code: runs in Work RAM ($3E00), loads CD data, restores bank mappings,
    # copies hooks, and jumps to $600B.
    #
    # Use CD_READ destination mode 2 (MPR2) for one contiguous 28-sector read.
    # The BIOS starts at physical bank BL and advances banks as necessary.  This
    # avoids changing MPR2 around repeated BIOS calls and avoids relying on any
    # CPU register or zero-page argument surviving a BIOS call.
    stub_code = [
        0xA9, 0x00, 0x85, 0xFC, # LDA #$00 / STA $FC  (LBA high)
        0xA9, 0x23, 0x85, 0xFD, # LDA #$23 / STA $FD  (LBA mid)
        0xA9, 0xDA, 0x85, 0xFE, # LDA #$DA / STA $FE  (LBA low = 9178)
        0xA9, 0x68, 0x85, 0xFA, # LDA #$68 / STA $FA  (BL = first resident bank)
        0xA9, 0x1C, 0x85, 0xF8, # LDA #$1C / STA $F8  (AL = 28 sectors)
        0xA9, 0x02, 0x85, 0xFF, # LDA #$02 / STA $FF  (DH = MPR2 mode)
        0x20, 0x09, 0xE0,       # JSR $E009 (CD_READ)

        # IPL header banks 00..04 are relative to the CD RAM base $80.
        0xA9, 0x80, 0x53, 0x04, # LDA #$80 / TAM #$04 (restore MPR2)
        0xA9, 0x81, 0x53, 0x08, # LDA #$81 / TAM #$08 (restore MPR3)
        
        # Copy fetch_hook to safe Work RAM ($3C00), outside the $2100 stack page.
        0xA0, 0x55,             # LDY #85 (copies 86 bytes: $4100 to $4155)
        # fetch_copy_loop:
        0xB9, 0x00, 0x41,       # LDA $4100, Y
        0x99, 0x00, 0x3C,       # STA $3C00, Y
        0x88,                   # DEY
        0x10, 0xF7,             # BPL fetch_copy_loop
        
        # Copy getfnt_hook to $3C80 (no overlap with fetch_hook at $3C00).
        0xA0, 0x50,             # LDY #80 (copies 81 bytes: $41A0 to $41F0)
        # getfnt_copy_loop:
        0xB9, 0xA0, 0x41,       # LDA $41A0, Y
        0x99, 0x80, 0x3C,       # STA $3C80, Y
        0x88,                   # DEY
        0x10, 0xF7,             # BPL getfnt_copy_loop
        
        # Resume immediately after the original MPR0/MPR1/SP init prefix.
        0x4C, 0x19, 0x60        # JMP $6019
    ]
    
    if len(stub_code) > 256:
        raise ValueError(f"Boot loader stub too large for the 8-bit copy loop: {len(stub_code)} bytes")
    copy_code[1] = len(stub_code) - 1

    hook = bytearray(init_code)
    while len(hook) < 16:
        hook.append(0xEA)
    hook.extend(copy_code)
    # Hook starts at $4010; pad through $403F so the copied stub is at $4040.
    while len(hook) < 48:
        hook.append(0xEA) # NOP
        
    hook.extend(stub_code)
    return bytes(hook)

def main():
    print("Loading data...")
    with open(iso_path, "rb") as f:
        iso_data = bytearray(f.read())
        
    with open(map_path, "r", encoding="utf-8") as f:
        char_map = json.load(f)
        
    with open(font_bin_path, "rb") as f:
        font_bin = f.read()

    # ---- 1. Store resident image in the real zero-filled postgap ----
    # Original sectors 9178..9327 are a verified 150-sector all-zero run.
    # Sector 6052 is live battle/code data and must not be overwritten.
    font_offset = 9178 * 2048
    font_dest = font_offset + 16384
    iso_data[font_dest : font_dest + len(font_bin)] = font_bin

    # ---- 2. Build and Inject Hooks in Boot Program ----
    # fetch_hook at $4100 (offset 0x1100 in file)
    # getfnt_hook at $41A0 (offset 0x11A0 in file)
    # boot_loader_hook at $4010 (offset 0x1010 in file)
    fetch_hook_bytes = build_fetch_hook()
    getfnt_hook_bytes = build_getfnt_hook()
    boot_loader_hook_bytes = build_boot_loader_hook()
    
    print("Injecting hooks to boot program...")
    iso_data[0x1100 : 0x1100 + len(fetch_hook_bytes)] = fetch_hook_bytes
    iso_data[0x11A0 : 0x11A0 + len(getfnt_hook_bytes)] = getfnt_hook_bytes
    iso_data[0x1010 : 0x1010 + len(boot_loader_hook_bytes)] = boot_loader_hook_bytes
    
    # Patch main boot vector to JMP $4010 (at offset 0x1000)
    iso_data[0x1000 : 0x1003] = b"\x4C\x10\x40"

    # ---- 3. Patch Jump Table Entry and GETFNT calls ----
    # Patch $4033 in Field Engine jump table to JMP $3C00
    print("Patching fetch API jump table entry...")
    iso_data[0x41033 : 0x41036] = b"\x4C\x00\x3C"
    
    # Patch GETFNT calls to JSR $3C80
    getfnt_offsets = [
        0x3891, 0x32886, 0x45855, 0x8667e, 0xbd1ca6, 0xbd8a97, 0xc06886, 0xc76886,
        0xca59c6, 0xd6e886, 0xda615a, 0xdce886, 0xe2e886, 0xe8e886, 0xed3080,
        0xeee886, 0xf5e886, 0xfbe886, 0x101e886, 0x107e886, 0x10a1caa, 0x10de886
    ]
    print(f"Patching {len(getfnt_offsets)} GETFNT calls to hook at $3C80...")
    for offset in getfnt_offsets:
        iso_data[offset : offset + 3] = b"\x20\x80\x3C"


    # ---- 4. Re-encode and Inject Dialogue Text ----
    print("Re-encoding dialogue script and injecting...")
    
    # Parse translated script sheet
    # We will group dialogue entries by region/slot
    region_entries = {}
    with open(tsv_path, "r", encoding="utf-8-sig") as f:
        header = f.readline()
        for line in f:
            cols = line.rstrip("\n").split("\t")
            if len(cols) > 4:
                offset_hex = cols[0]
                region = cols[1]
                dup = cols[2]
                jp_text = cols[3]
                ko_text = cols[4].strip()
                
                if not ko_text:
                    continue  # Ignore empty translations
                    
                offset = int(offset_hex, 16)
                if region not in region_entries:
                    region_entries[region] = []
                region_entries[region].append({
                    "offset": offset,
                    "jp": jp_text,
                    "ko": ko_text,
                    "dup": dup
                })

    # Prepare slot append tables and resident tables
    # Slots start at LBA 162, size 96 sectors = 196,608 bytes.
    SLOT_BASE = 162 * 2048
    SLOT_SIZE = 96 * 2048
    
    # Read original slot table to load actual counts and LBA offsets
    with open(iso_path, "rb") as f:
        f.seek(0x424A5)
        slot_table_data = bytearray(f.read(55 * 4))

    # Determine which slot regions overflow and need to be deferred to the resident pool
    resident_regions = ["system", "late", "boot", "misc", "slot00", "slot01"]
    slot_regions = []
    for region, rows in region_entries.items():
        if region.startswith("slot") and region not in ["slot00", "slot01"]:
            slot_idx = int(region[4:6])
            
            # Read slot parameters from original table
            slot_entry_offset = slot_idx * 4
            entry = slot_table_data[slot_entry_offset : slot_entry_offset + 4]
            sectors = entry[3]
            
            # Calculate total unique translation size for this slot (since we'll deduplicate)
            seen_ko = set()
            slot_translation_size = 0
            for row in rows:
                if row["dup"]:
                    continue
                ko_bytes = encode_string(row["ko"], char_map) + b"\x00"
                if ko_bytes not in seen_ko:
                    seen_ko.add(ko_bytes)
                    slot_translation_size += len(ko_bytes)
                    
            needed_sectors = ((sectors * 2048 + slot_translation_size) + 2047) // 2048
            if needed_sectors > 96:
                print(f"Slot {slot_idx:02d} size {needed_sectors} sectors exceeds 96 sectors limit! Redirecting to resident pool.")
                resident_regions.append(region)
            else:
                slot_regions.append(region)

    # Unified resident translation allocator in Super CD RAM banks $68-$6E.
    # Banks $80-$83 contain the IPL boot program and must never be overwritten.
    # Pool 1: banks $68-$69 (16 KB) and bank $6E (8 KB) -> total 24 KB
    # Pool 2: banks $6A-$6D slots $00-$1F (4 * 1024 = 4096 bytes)
    pointer_map = {}
    resident_ptr = 0  # contiguous pointer from 0 to 28671
    allocated_strings = {} # ko_bytes -> (bank, logical_addr, dest_file_offset)
    
    def allocate_resident(length):
        nonlocal resident_ptr
        if resident_ptr < 24576:
            if resident_ptr + length > 24576:
                # Spill over to Pool 2 to keep string contiguous
                resident_ptr = 24576
                
        if resident_ptr >= 24576:
            offset_in_pool2 = resident_ptr - 24576
            bank_idx = offset_in_pool2 // 1024
            offset_in_bank = offset_in_pool2 % 1024
            
            if offset_in_bank + length > 1024:
                # Move to next bank to keep string contiguous
                bank_idx += 1
                offset_in_bank = 0
                offset_in_pool2 = bank_idx * 1024
                resident_ptr = 24576 + offset_in_pool2
                
            if bank_idx >= 4: # Banks $6A-$6D (4 banks)
                raise ValueError("Fatal: Contiguous resident translation pool completely full!")
                
            bank = 0x6A + bank_idx
            logical_addr = 0x6000 + offset_in_bank
            file_off = font_offset + (bank - 0x68) * 8192 + offset_in_bank
            resident_ptr += length
            return bank, logical_addr, file_off
        else:
            bank_idx = resident_ptr // 8192
            offset_in_bank = resident_ptr % 8192
            if bank_idx < 2:
                bank = 0x68 + bank_idx
            else:
                bank = 0x6E
            logical_addr = 0x6000 + offset_in_bank
            file_off = font_offset + (bank - 0x68) * 8192 + offset_in_bank
            resident_ptr += length
            return bank, logical_addr, file_off

    # Process resident regions (including slot00, slot01, and any overflowing slots)
    for region in resident_regions:
        if region not in region_entries:
            continue
        rows = region_entries[region]
        print(f"Processing resident region {region} ({len(rows)} messages)...")
        for row in rows:
            if row["dup"]:
                continue  # Handled by duplicate lookup
                
            ko_bytes = encode_string(row["ko"], char_map) + b"\x00"
            
            if ko_bytes in allocated_strings:
                bank, logical_addr, dest_file_offset = allocated_strings[ko_bytes]
            else:
                bank, logical_addr, dest_file_offset = allocate_resident(len(ko_bytes))
                # Write Korean string into the custom resident bank slot in the ISO
                iso_data[dest_file_offset : dest_file_offset + len(ko_bytes)] = ko_bytes
                allocated_strings[ko_bytes] = (bank, logical_addr, dest_file_offset)
            
            # Record pointer
            ptr_bytes = struct.pack("<B H", bank, logical_addr)
            pointer_map[row["offset"]] = ptr_bytes

    # Process non-overflowing slot regions
    for region in slot_regions:
        rows = region_entries[region]
        slot_idx = int(region[4:6])
        
        # Read slot parameters from original table
        slot_entry_offset = slot_idx * 4
        entry = slot_table_data[slot_entry_offset : slot_entry_offset + 4]
        rel_lba = (entry[0] << 16) | (entry[1] << 8) | entry[2]
        sectors = entry[3]
        
        # Calculate file offset of slot on CD
        slot_file_start = rel_lba * 2048
        
        # Append translated strings starting at the end of the slot data
        S = sectors
        offset_in_slot = S * 2048
        current_ptr = slot_file_start + offset_in_slot
        
        for row in rows:
            if row["dup"]:
                continue
                
            ko_bytes = encode_string(row["ko"], char_map) + b"\x00"
            
            # Check if this string is already allocated in this slot (slot-local deduplication)
            slot_key = (slot_idx, ko_bytes)
            if slot_key in allocated_strings:
                bank, logical_addr, dest_file_offset = allocated_strings[slot_key]
            else:
                needed_sectors = ((offset_in_slot + len(ko_bytes)) + 2047) // 2048
                if needed_sectors > sectors:
                    sectors = needed_sectors
                    if sectors > 96:
                        raise ValueError(f"Fatal: Slot {slot_idx:02d} size {sectors} sectors exceeds 96 sectors memory limit!")
                    
                # Write string to ISO
                iso_data[current_ptr : current_ptr + len(ko_bytes)] = ko_bytes
                
                # Calculate logical memory address:
                bank = 0x20 + S // 4
                offset_in_bank = (S % 4) * 2048 + (current_ptr % 2048)
                logical_addr = 0x6000 + offset_in_bank
                
                allocated_strings[slot_key] = (bank, logical_addr, current_ptr)
                
                current_ptr += len(ko_bytes)
                offset_in_slot = current_ptr - slot_file_start
                S = offset_in_slot // 2048
            
            ptr_bytes = struct.pack("<B H", bank, logical_addr)
            pointer_map[row["offset"]] = ptr_bytes
            
        # Update sector count in the slot table
        slot_table_data[slot_entry_offset + 3] = sectors
        print(f"Slot {slot_idx:02d} size increased from {entry[3]} to {sectors} sectors.")

    # Write the modified slot table back to ISO
    print("Writing updated slot table back to ISO...")
    iso_data[0x424A5 : 0x424A5 + len(slot_table_data)] = slot_table_data

    # ---- 5. Write Redirect Pointers in script ----
    # Now we write the `$01 [bank] [low] [high] 00` redirect commands to the original script locations
    print("Writing redirect pointers in-place to original script locations...")
    for region, rows in region_entries.items():
        for row in rows:
            # Resolve duplicate groups
            target_offset = row["offset"]
            if row["dup"]:
                rep_offset = int(row["dup"][1:], 16)
                if rep_offset in pointer_map:
                    ptr_bytes = pointer_map[rep_offset]
                else:
                    # Representative was not translated (empty)
                    continue
            else:
                if target_offset in pointer_map:
                    ptr_bytes = pointer_map[target_offset]
                else:
                    continue
                    
            # Write redirect command: 01, bank, low, high, 00
            bank = ptr_bytes[0]
            low = ptr_bytes[1]
            high = ptr_bytes[2]
            redirect_cmd = bytes([0x01, bank, low, high, 0x00])
            
            # Write to original script location
            iso_data[target_offset : target_offset + len(redirect_cmd)] = redirect_cmd

    # ---- 6. Save modified ISO ----
    print(f"Saving patched ISO to {out_iso_path}...")
    with open(out_iso_path, "wb") as f:
        f.write(iso_data)
    print("Patched ISO saved successfully.")

if __name__ == "__main__":
    main()
