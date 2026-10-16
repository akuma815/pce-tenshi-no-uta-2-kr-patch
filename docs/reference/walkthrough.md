# Walkthrough — Tenshi no Uta II Korean patch redesign

This document records the verified failures of the resident-memory prototype and the
replacement architecture. The current `patch_iso.py` is a research prototype; its
resident loader must not be treated as a release-ready patch.

## 1. What was verified

- The mixed text encoding and message fetch pipeline were decoded.
- Korean font generation and translation TSV pipelines work.
- The data track can be overlaid into the mixed-mode BIN without changing its size.
- xdelta encode/decode round-trip verification works.
- The only contiguous zero-filled disc run large enough for auxiliary data is relative
  LBA 9178..9327 (150 sectors).
- BizHawk reached the title after correcting the boot initialization and IPL mapping.

## 2. Why the resident prototype failed

The prototype attempted to preload about 56 KB of deduplicated Korean strings and
font data into fixed RAM banks, then installed fetch/font hooks at fixed Work RAM
addresses. Runtime debugging disproved every "unused RAM" assumption.

| Evidence | Result |
|---|---|
| CD_READ at PC `$E96A`, MPR2..6=`80,81,82,83,84` | IPL header banks `00..04` are relative to CD RAM base `$80` |
| First scene at PC `$B119`, MPR4=`73`, MPR5=`86`, MPR6=`87` | The game actively uses both Super CD RAM and CD RAM |
| Hooks previously placed at `$2100/$2140` | They overlapped each other and the hardware stack page |
| Hooks moved to `$3C00/$3C80` | These are still ordinary game Work RAM, not reserved storage |
| Resident image previously written at LBA 6052 | LBA 6052 is live battle/code data, not padding |

Moving the same resident image to another bank cannot solve the problem. Banks
`$68..$7F` and `$80..$87` change ownership as scenes and resources are loaded. A
fixed pointer into any of them eventually aliases game code, graphics, or workspace.

## 3. Replacement architecture

### 3.1 No permanently reserved game RAM

Remove the boot-time 28-sector resident read. Do not reserve `$68..$87`, stack page
`$2100`, BIOS variables in `$22xx`, or guessed Work RAM such as `$3Cxx`.

Translations and glyphs are packaged with the slot or executable module that uses
them. Their lifetime then exactly matches the original loader's lifetime.

### 3.2 Per-slot package

Use the unused tail inside each existing 96-sector area slot:

```text
original resources | translated strings | local glyph subset | manifest
```

The manifest maps original stream offsets to translated string addresses and records
the local glyph pool address. Redirects remain fixed-size, so event branches and
inline parameters do not move.

The fetch hook only switches to another address that is already present in the
currently loaded slot. It performs no CD read during character output and keeps no
pointer to a bank after the slot is unloaded.

### 3.3 Per-slot glyph subsets

Do not load the global 896-glyph/32 KB font. For every slot, collect only the Korean
characters used by that slot and emit 32 bytes per glyph. Custom character codes are
slot-local glyph indices interpreted through the current package manifest.

Shared menu, item, and name glyphs form a small core subset. The core subset may be
duplicated in relevant packages; disc duplication is safer than permanent RAM use.

### 3.4 Handling Slot 01 and Slot 16

Both slots must remain at or below 96 sectors. Apply, in order:

1. exact-string deduplication;
2. suffix sharing;
3. local glyph subsets;
4. compact tokens for repeated markup and Korean phrases;
5. translation length/line-break audit.

The build must fail if a package still exceeds 96 sectors. The LBA 9178 sidecar is a
last resort for scene-load-time transient data only; it must never become a permanent
resident pool.

### 3.5 Module-local hooks

Install separate fetch/GETFNT hook copies in the field engine, menu/battle engine,
boot renderer, and event-scene program copies. Each hook must live in verified padding
inside the same module that calls it. Before patching, validate the original signature
and padding; after patching, validate branch targets and non-overlap.

If a hook temporarily changes an MPR, save the live value with TMA and restore it on
every return path. Never hard-code an assumed previous mapping.

## 4. New build pipeline

1. Verify the original ISO/hash.
2. Classify translations by slot/module.
3. Build deduplicated strings and local glyph subsets.
4. Emit and size-check each package (`<= 96 * 2048`).
5. Locate verified module padding and inject local hooks.
6. Write fixed-size redirects and patched call sites.
7. Assert that no live range was unintentionally modified or overlapped.
8. Build BIN/CUE and verify xdelta reconstruction.
9. Run the mandatory emulator regression suite.

`build_patch.py` should not produce a release xdelta when any size, signature, overlap,
or regression prerequisite fails.

## 5. Regression checklist

- Pass the System Card `JUST A MOMENT...` screen and reach the title.
- Enter a new game with intact background, sprites, and palette.
- Test the beginning, middle, and end of Slot 01 and Slot 16.
- Test menus, item names, battle text, card minigame, and late event scenes.
- Perform at least 20 scene transitions.
- Confirm no `EXEC BRK`, unsupported-sector read, or emulator exception.
- Compare screenshots against the original; only intended text pixels may differ.

## 6. Status

- Analysis and redesign: complete.
- Step 1, per-slot capacity auditor: complete (`tools/analyze_slot_packages.py`).
- Step 2 prototype, dry-run KSP1 string package builder: superseded by topology audit.
- Cross-region aliases: 6,041; these must be duplicated because slots are loaded independently.
- Actual string-package overflow slots after 8 KiB boundary alignment: 01, 11, 16, 28, 40, 41, 53.
- The 47 files in `translation/slot_packages/` are deprecated research artifacts;
  logical table indices were incorrectly treated as physical grid indices.
- Simple string+local-font placement overflows 24 slots, so font storage needs a separate strategy.
- Step 3, `$54A5` logical-to-physical topology audit: complete (`tools/analyze_slot_topology.py`).
- Actual area-loader topology: 55 logical entries share 31 physical grids; 30 mapped grids contain translations.
- 24 translated physical grids are not referenced by the area table and require scene/system loader reclassification.
- Step 4, mapped-area capacity audit: complete (`tools/analyze_mapped_area_packages.py`).
- Actual mapped-area string overflow grids: 15, 28, 40, 41; the other 26 fit.
- Actual mapped-area string+glyph overflow grids: 04, 08, 10, 15, 27, 28, 31, 34, 35, 36, 40, 41.
- Step 5, topology-aware KAP1 string package builder: complete
  (`tools/build_mapped_area_string_packages.py`).
- Emitted and verified 26 packages in `translation/mapped_area_packages/`.
- Rejected grids: 15 (103 sectors), 28 (101), 40 (101), and 41 (97).
- Grids 10, 31, and 36 reach exactly 96 sectors with strings and have no room for glyph data.
- Step 6, reclaimed-hole allocator: implemented (`tools/pack_overflow_area_holes.py`).
- Grid41 now fits without compression and its 105 placements / 223 redirects were verified.
- Grid28 and Grid40 have enough total free bytes but fail due to fragmented holes.
- Grid15 remains short by at least 715 bytes even before fragmentation overhead.
- Step 7, KAC1 continuation-chain allocator: implemented
  (`tools/pack_fragmented_area_chains.py`).
- Grid28 succeeds with 21 continuation markers and 2,099 bytes free.
- Grid40 succeeds with 18 continuation markers and 7,906 bytes free.
- Grid15 still fails after chain allocation: 1,465 bytes remain unplaced with only 48 bytes free.
- Step 8, Grid15 single-glyph token dictionary: complete
  (`tools/build_grid15_token_layout.py`).
- 25 tokens avoid native controls 0B..0E and save 2,580 bytes.
- Grid15 now fits with 61 continuation markers and 1,621 bytes remaining.
- Capacity phase for all 30 mapped area grids: complete.
- Step 9, unified KAPLAN1 area patch plan: complete
  (`tools/normalize_area_patch_plan.py`).
- `translation/area_patch_plan.json` covers all 30 areas exactly once: 26 contiguous,
  one hole layout, two continuation layouts, and one token+continuation layout.
- Plan totals: 617 writes, 5,828 redirects, 100 continuations, and 25 tokens.
- Redirect and continuation targets intentionally remain symbolic until the fetch ABI is finalized.
- Step 10, fetch-record materialization: complete
  (`tools/materialize_area_fetch_records.py`).
- `translation/area_patch_plan_materialized.json` contains 30 area writes, 5,828 concrete
  redirect records, 100 concrete continuation records, and 52 logical load-count updates.
- Runtime targets use physical bank `[$22D0] + bank_index` and MPR3 address
  `$6000 + (area_offset % $2000)`; no fixed resident bank is assumed.
- Independent verification (`tools/verify_materialized_area_plan.py`) checks record shape,
  bank/address bounds, inverse target mapping, and duplicate sources/markers.
- Step 11, fetch-hook reference model: complete (`tools/model_area_fetch_hook.py`).
- Redirect bank bit 7 enables Grid15 token expansion; the physical bank remains in bits 0..6.
- All 5,828 redirects / 3,467 unique streams execute successfully through 100 continuation
  links; 2,580 token instances expand and the maximum output is 1,162 bytes including NUL.
- Step 12, field MPR2 padding audit: complete (`tools/audit_field_hook_padding.py`).
- No safe cave exists in `$4000..$5FFF`; the largest zero/FF run is only 11 bytes.
- Hook bytecode injection is therefore gated on an API call-graph/liveness audit. No ISO
  mutation was performed in this step.
- Step 13, field API static liveness audit: complete
  (`tools/analyze_field_api_liveness.py`).
- 18 of 24 entries have opcode-pattern or engine-internal references. Six entries are
  raw-only dynamic-validation candidates: 400C, 4015, 4018, 401B, 402A, and 4036.
- Entry 400C shares live implementation 4526. The remaining five nominal target spans total
  only 38 bytes and are discontiguous; zero bytes are reclaimable without runtime proof.
- The fragmented-API-cave design is rejected. The next feasibility target is an in-place
  replacement of original fetch body 4111..4159 (73 bytes), with Grid15's 50-byte dictionary
  stored inside its remaining 1,621-byte area capacity.
- Step 14, alternate resident-bank cave audit: complete
  (`tools/audit_field_resident_hook_bank.py`).
- A 7,367-byte FF run exists at ISO 47339, corresponding to `$83:$A339` under the observed
  initial MPR2..MPR6 mapping 80..84.
- Revised prototype: a 13-byte interrupt-safe trampoline at 4111 maps physical bank 83 into
  MPR5, while the hook body at A339 uses only MPR3 as its temporary data window.
- Every exit must restore the actual prior MPR5 and processor flags. The candidate remains
  gated on loader-signature and control-flow verification; the ISO is still untouched.
- Step 15, HuC6280 fetch-hook dry-run prototype: complete
  (`tools/build_field_fetch_hook_prototype.py`).
- Emitted a 73-byte trampoline image and a 395-byte resident hook containing 337 bytes of
  code, a 50-byte Grid15 token table, and eight bytes of module-local state.
- The hook preserves the three native stream priorities and implements redirect, continuation,
  token pending, single-window MPR3 reads, and common MPR5/X/P restoration.
- Independent structural verification (`tools/verify_field_fetch_hook_prototype.py`) validated
  37 control transfers, instruction boundaries, source/cave signatures, and the epilogue.
- These files are dry-run artifacts only. No bytes have been written to the ISO/BIN.
- Step 16, loaded-range correction and guarded fetch diagnostic build: complete.
- The first build guard found 765 package/redirect overlaps. Every overlap was beyond that
  area's `$54A5` CD_READ range, so it was removed from the mapped-area plan. Runtime evidence
  later proved that some such tail strings are live through separate scene/system loaders.
- All mapped-area tools now require `source < area_base + original_load_sectors*2048`.
- Corrected totals: 27 translated mapped areas, 23 contiguous packages, 2,724 redirects,
  98 continuations, and 49 logical load-count updates.
- `tools/build_redesign_diagnostic.py` emitted a separate fetch-only diagnostic BIN/CUE after
  3,484 non-overlapping spans and 257,784 patched bytes passed signature/readback checks.
- Source SHA-256: `d16d29eb80b1b74a2ec929924349256b50b8f9f5c9a3fa37b6fcc08b059b22c5`.
- Diagnostic SHA-256: `827bce3769d20a5e996c4022a809f98918ce0c4f610c421f7499e9faf23c9f69`.
- This diagnostic is not release-safe because the redesigned module-local glyph hook is absent.
- Step 17, first-dialogue runtime validation: passed.
- The diagnostic reached boot, title, gameplay, and `フェイト： よう、シオン` with intact graphics.
- Debugger evidence: PC=53AF and MPR2..MPR6=80,81,82,83,84, confirming MPR5 restoration.
- Source 010B9E8 is unchanged and has no mapped-area redirect. Its live appearance proves it
  belongs to a separate scene/system loader, not that the fetch hook failed.
- Evidence: `translation/runtime_validation_first_dialogue.json`.
- Step 18, runtime CD_READ trace and second-engine overlay topology: complete.
- Frame 1269 loads LBA 482..577 (96 sectors) to bank 68 in mode 06, covering first-dialogue
  sector 535. Descriptor 0001E260 is overlay logical entry 2 at table offset 83531.
- `tools/analyze_overlay_topology.py` classifies 6,980 translation rows as overlay-only,
  2,559 as shared, 165 as primary-only, and 451 as still unclassified.
- Overlay translations occupy 54 physical grids. Bank 68 is confirmed live overlay storage.
- Step 19, cross-loader conflict audit: failed safely as designed.
- `tools/audit_cross_loader_conflicts.py` found 481 primary package writes overlapping overlay
  live ranges across all 27 primary grids.
- The existing diagnostic SHA 827bce...9f69 is valid only as first-dialogue fetch/MPR evidence;
  it must not be used for further gameplay. Its manifest is marked accordingly.
- Future diagnostic builds now fail on the first overlay collision. No replacement build was emitted.
- Step 20, unified interval topology: complete
  (`tools/build_unified_interval_topology.py`).
- Primary, overlay, and observed runtime CD_READ intervals merge into 14 live ranges.
- Thirteen table gaps remain (202 sectors), but only two whole sectors are 00/FF; both sit in
  gaps containing 107 and 152 unclassified live translation sources respectively.
- Runtime tracing also proved the apparent 258..289 gap is a 32-sector second-engine load.
- No payload-range hole is currently safe. The only verified storage remains sidecar
  LBA 9178..9327: 150 sectors / 307,200 bytes.
- Step 21, global sidecar capacity audit: complete (`tools/analyze_sidecar_capacity.py`).
- 10,155 translated rows deduplicate to 2,883 strings. Bank-safe strings plus the full 32-KiB
  font occupy 286,770 bytes / 141 sectors, leaving 20,430 bytes in the sidecar.
- Disk capacity therefore fits, but loading it resident would require 38 banks and is forbidden.
- Step 22, per-scene shard RAM audit: complete (`tools/analyze_scene_shard_capacity.py`).
- Only 25 of 81 contexts fit a shard in whole banks left after the original load: primary 15/27,
  overlay 10/54. Fifty-six fail and 36 have no free bank at all.
- The append-after-load shard strategy is rejected. Next, both fetch engines need one ABI and a
  cross-loader-aware allocator must reclaim only verified original-string bodies inside each window.
- Existing resident implementation: deprecated and not release-safe.
- Per-slot packer, local glyph encoder, and module-local hooks: not yet implemented.
- Current generated patched BIN/xdelta: diagnostic only; do not distribute.

The topology report is `translation/slot_topology.json`. No package has been written
to the ISO. The corrected capacity report is
`translation/mapped_area_package_report.tsv`. The next step is to emit dry-run string
packages for the 26 fitting mapped grids while explicitly rejecting 15/28/40/41.
This step is now complete. Next, reclaim original-string holes for the four rejected
grids and measure whether they fit without token compression. This measurement is now
complete. Next, add a continuation-chain string format for Grid28/40 and measure a
small token dictionary for Grid15. The chain format is now validated; only the Grid15
token dictionary remains in this capacity phase. This is now complete. Next, normalize
all area layouts into one patch-plan format and implement the module-local fetch hook.
Normalization, record materialization, fetch behavior modeling, padding audit, and API
Liveness audits, the hook prototype, loaded-range correction, and guarded fetch diagnostic build
are complete, and runtime validation passes through the first dialogue. The overlay loader is
now traced. Global sidecar disk capacity fits, but per-scene free-bank capacity fails for most
contexts. The next step is a cross-loader-aware in-place source-hole allocator and overlay fetch hook.
- Step 23, per-context source-hole reclamation audit: complete
  (`tools/analyze_context_source_holes.py`).
- Reclaiming original string bodies alone fits 0/81 contexts. Combining those holes with
  whole banks left after each load fits 45/81: primary 24/27 and overlay 21/54.
- The remaining 36 failures exactly match contexts with no whole free bank and leave 165,083
  string bytes unplaced. Source-hole reclamation is necessary but cannot solve full-window overlays.
- Next, measure one fixed global 25-glyph token dictionary against the same allocator before
  considering runtime streaming. This remains a read-only capacity audit.
- Step 24, fixed global 25-glyph token capacity audit: complete
  (`tools/analyze_global_token_source_holes.py`).
- The fixed dictionary round-trips every compressed stream and saves 155,334 bytes across
  per-context unique-string sets. Missing bytes fall from 165,083 to 69,859.
- The fit count remains 45/81: primary 24/27 and overlay 21/54. All 36 full-window failures remain;
  the largest individual deficit is now 3,940 bytes.
- Token compression is retained as part of the design, but it is not sufficient alone. The next
  audit must identify a loader-safe reusable scratch/stream window of roughly 4 KiB and prove its lifetime.
- Step 25, fixed global tokens plus continuation-chain capacity audit: complete
  (`tools/analyze_global_token_continuation_capacity.py`).
- Bank-safe four-byte continuation records raise the fit count from 45/81 to 63/81 without
  allocating any scratch RAM: primary 25/27 and overlay 38/54.
- The layouts use 2,176 continuation markers. Fourteen of the remaining 18 failures have a raw
  compressed-byte deficit; primary 28 and overlay 4/5/38 fail only from marker cost/fragmentation.
- Scratch-RAM work is deferred until a per-context 50-byte glyph dictionary audit determines how
  many of these 18 contexts can be solved entirely inside their existing load windows.
- Step 26, per-context 25-glyph dictionary audit: complete
  (`tools/analyze_context_token_continuation_capacity.py`).
- Every dictionary is charged as a contiguous 50-byte in-window allocation; small dictionaries
  are safely padded, and all compressed streams pass round-trip verification.
- Context-specific selection saves only 1,028 bytes more than the global table while adding 4,050
  bytes of dictionary storage. Fit remains 63/81 with the exact same 18 failures.
- Per-context dictionaries are rejected. Keep the fixed global table and restrict the next
  scratch/stronger-compression investigation to the remaining 18 contexts.
- Step 27, exact minimum single-bank scratch capacity audit: complete.
- Extending `tools/analyze_global_token_continuation_capacity.py` with a byte-wise search proves
  all 18 remaining contexts fit with at most 2,974 contiguous scratch bytes.
- Scratch requirements range from 69 to 2,974 bytes with a 1,268-byte median; 12/18 fit within
  2 KiB and all fit within 3 KiB.
- This is capacity evidence only. The next step must runtime-trace a 3-KiB Work RAM or Super CD RAM
  candidate from scene load through final text fetch and define an external-scratch marker ABI.
- Step 28, Work RAM byte-liveness tracer: tooling verified and hardened; runtime evidence still pending
  (`tools/trace_work_ram_liveness.lua`, `tools/analyze_work_ram_liveness.py`).
- It records every read/write to System Bus 2000..3FFF and emits per-byte statistics plus untouched
  runs; the analyzer ranks untouched/no-write runs and checks them against the 18 failing contexts'
  scratch requirements (max 2,974 B; source `global_token_continuation_capacity.json`).
- Source verification (BizHawk PCEHawk core): the CPU wrapper `HuC6280.ReadMemory/WriteMemory(16-bit)`
  fires `System Bus` read/write callbacks (HuC6280.cs:334,352); the opcode fetch goes through
  `ReadMemory(PC++)` so read+write coverage already includes code execution. `MemoryMap.cs`'s own
  CallRead/CallWrite are commented out but are a different (21-bit delegate) path, not the CPU path.
- Callback matching is a linear scan (`MemoryCallbackSystem.Call` foreach), so a single whole-bus
  callback + Lua-side range filter is optimal; per-address registration would be catastrophic.
- **CRITICAL: the trace must run on the PCEHawk core.** `TurboNyma` (Mednafen waterbox, the value
  currently in `output/config.ini` `"PCECD"`) has no `MemoryCallbacks`/`IDebuggable` wiring, so the
  tracer silently produces no data. Set Config→Cores→PCE-CD = PCEHawk before loading. The prior
  CD_READ trace (Step 18) and the VDC crash were both on PCEHawk, confirming that is the debug core.
- Flush is now wall-clock based (every 15 s) so partial evidence survives even at the low fps caused
  by whole-bus Lua callbacks; reports also written on normal exit.
- An unattended background launch was attempted for pipeline validation but produced no TSV, because
  the default core was TurboNyma and a fresh launch cannot dismiss the core/firmware dialogs. The
  interactive playthrough on PCEHawk remains the required evidence step; the tooling itself is ready.
- A fast frame-diff write-liveness variant was added (`tools/trace_work_ram_writes_fast.lua`) because
  the whole-bus callback tracer runs at unusably low fps. `tools/run_liveness_trace.ps1` launches
  either mode against H:\BizHawk (PCEHawk core, Super System Card 3.0(J) firmware present) with
  correctly quoted arguments; the analyzer reads both formats.
- **Step 28 runtime result (fast write-liveness, one representative playthrough): Work RAM has no
  usable scratch window.** 6,705 / 8,192 bytes were written; only 1,487 were never written, and the
  largest contiguous never-written run is just **124 bytes** ($3ED7..$3F52). Against the 2,974-byte
  contiguous requirement this covers 1/18 contexts; even the 512-byte minimum is unmet. Free space is
  fragmented into tiny pockets (mostly < 60 B). Because this is write-only and from a single run, more
  coverage can only shrink the free set further, so 124 B is an optimistic upper bound.
- **Conclusion: a single fixed Work-RAM scratch region for overflow string storage is not viable
  under GLOBAL liveness.** Verdict data: `translation/work_ram_scratch_verdict.json`.
- Step 29, scope correction + per-scene scratch instrument: complete
  (`tools/trace_scene_scratch.lua`, `tools/analyze_scene_scratch.py`).
- Clarification from re-reading `model_area_fetch_hook.py`: the fetch hook is ALREADY a byte-at-a-time
  stream (token second byte held in a 1-byte `pending`, continuation just repoints), so hook decode
  state is ~8 bytes and was never the problem. The "scratch" of Steps 25-27 is OVERFLOW STRING
  STORAGE for the 18 contexts that do not fit their compressed Korean in reclaimed in-area holes.
- The 18 overflow contexts need per-scene contiguous storage of 69..2,974 B (max 2,974). This scratch
  is REUSED per scene, so the requirement is one region ≥ the worst single scene, free DURING that
  scene — not across the whole game. Step 28's global 124 B is therefore over-pessimistic: a byte used
  in scene B may be free in scene A. Six contexts need >1,487 B, so even all fragmented global free is
  insufficient; only per-scene measurement can decide them.
- `trace_scene_scratch.lua` windows the Work RAM write-liveness by CD_READ: when a target overflow
  area LBA (290,386,482,674,770,866,962,1154,1250,1346,1602,1634,1826,1922,2306,2690,2850,3938) is
  loaded (count ≥ 80), it opens a fresh window until the next scene load and records that scene's free
  contiguous runs. `analyze_scene_scratch.py` compares each scene's largest free run to its need.
  Run with `run_liveness_trace.ps1 -Scene` on PCEHawk; prioritise the six largest needs
  (LBA 866, 2306, 962, 482, 1346, 1826). Runtime evidence pending user playthrough of those scenes.
- If a scene's largest per-scene free run still falls short, fall back options in order: (1) split
  overflow across that scene's fragmented free pockets via 4-byte continuation links; (2) deeper
  in-area original-data reclamation; (3) partial (Japanese-retained) translation for the few worst
  text-heavy overlay scenes.
- Step 30, System Card font-slot + fixed-length translation diagnostic: **runtime failed**.
- The corrected v3.0(J) EX_GETFNT model exposes 3,461 unique compact glyph indices. Protecting 1,612
  indices used by extracted source/translation text leaves 1,849 candidates, enough for all 896 Hangul glyphs.
- Fixed-length in-place encoding fits 309/10,155 translations unchanged and truncates 9,846 at safe
  character/control boundaries because compressed Japanese kana are one byte while Hangul SJIS is two.
- Separate diagnostic BIOS/BIN/CUE images passed only checks based on the assumed slot model. Runtime produced
  severe System Card startup tile corruption. A second probe changed only one 72-byte game string and reproduced
  the identical corruption, so broad game replacement is rejected as the cause; the custom BIOS itself is invalid.
- Do not use the diagnostic BIOS, full diagnostic disc, or one-string probe. The one-string probe still paired
  the same 896-slot BIOS, so it rejects broad game replacement but does not by itself reject
  `0x10000 + compact_index * 32`; unsafe System Card-owned slot overlap remains the leading cause.
- Step 31 first runtime result: graphics stayed normal but `出` was unchanged. This disproved the selected
  source slot, not BIOS modification itself. The field renderer at ISO `0x45850` executes
  `LDA #$01 / STA $FF / JSR $E060`, so it uses EX_GETFNT mode 1: the 18-byte packed 12x12 font at
  `0x30000 + glyph_index * 18`, not the mode-0 32-byte font at `0x10000 + glyph_index * 32`.
- The SJIS model also inverted the BIOS `$F203..$F20A` lower-trail adjustment. `出` (`8F6F`) therefore
  mapped to adjacent index 1721 instead of the BIOS-correct index 1722. The original mode-1 slot at
  `0x37914` decodes to the visible `出` bitmap, directly confirming both corrections.
- Step 32 corrected true-minimum gate rebuilt: `SystemCard3_one_glyph_probe.pce` now changes only the
  mode-1 index-1722 slot at BIOS `0x37914` to packed 12x12 `가`. Static verification found 17 changed
  bytes, all inside that one 18-byte slot; the original game disc remains unchanged.
- Step 32 runtime result: **PASS**. System Card/game graphics remained normal and only the first-dialogue
  `出` position changed to the generated Hangul glyph. The glyph is structurally `가` but visually resembles
  `기` because its right horizontal stroke is weak at 12x12; this is a font raster-quality issue, not an
  address, encoding, decompression, or BIOS-loading failure.
- The corrected full slot audit was regenerated: 3,461 reachable indices, 1,612 protected indices, and
  1,849 unused candidates. The next gate is a small multi-glyph readability sample before replacing all
  896 selected slots.
- `trace_ex_getfnt_source.lua` remains a supporting runtime tracer for `$F124`/`$F1B9` and MPR/file matching.

- Step 33, full text catalogue v1: complete (`tools/extract_all_text.py`).
- The legacy dialogue-only heuristic was retained as evidence but expanded with a broad ISO scan,
  external translation-asset matching, packed-table clustering, and explicit forensic queues.
- A legacy boundary bug was corrected: strings beginning with `%s`, `#n`, `~`, or line/page controls
  previously started at the second byte, so ASCII `s` was decoded as compressed kana `れ`. The new
  catalogue starts at the actual control byte while preserving the linked legacy translation.
- Translation-ready output contains 18,817 physical ISO records in 38 UTF-8 BOM CSV files: 37 files
  of 500 rows and one file of 317 rows. It includes dialogue, menu data, commands, battle/card text,
  names, items, equipment, monsters, locations, and visual-event text.
- All 18,817 rows were verified byte-for-byte against the original Track02 ISO; IDs are unique,
  duplicate references point to earlier catalogue rows, and the 500-row files reassemble exactly to
  `master_text.csv` (`tools/verify_full_extraction.py`, `verification_report.json`: PASS).
- Coverage is deliberately not yet labelled “zero omissions”: 17 short exact matches need review,
  345 external rows are not yet tied to physical ISO text, and raw/graphics candidates remain in
  `forensic_candidates.csv`. Modern collection UI/game-selector rows are explicitly out of PCE scope.

- Step 34, current-translation multi-glyph probe: static build complete; runtime result pending.
- `tools/build_current_translation_probe.py` reads the corrected first-dialogue record
  `iso:010B9E7` directly from `translation/full_extraction/master_text.csv`. It does not use the
  invalid legacy 32-byte mode-0 diagnostic or its off-by-one `0x010B9E8` source boundary.
- The probe preserves all original speaker-name bytes, `#` controls, line breaks, page breaks, and
  the terminating NUL. Only the three dialogue-body runs are replaced from the current translation,
  truncated at character boundaries and padded inside their original fixed capacities.
- Eighteen Hangul characters are assigned to compact indices 3443..3460 and written only to the
  validated mode-1 range `0x30000 + index * 18`. The protected set is regenerated from all
  `master_text.csv` raw records before allocation.
- Expected Write verification passed: 18 non-overlapping BIOS writes / 324 changed bytes and three
  game writes / 39 changed bytes. Full-file diff auditing found no undeclared changes; the original
  BIN, CUE, and System Card remain untouched.
- Runtime pair: `SystemCard3_KoreanFont_current_translation_probe.pce` plus
  `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_current_translation_probe.cue`. The paired BizHawk
  configuration is `translation/current_translation_probe_bizhawk_config.ini`; detailed hashes,
  mappings, capacities, and diff ranges are in `translation/current_translation_probe_manifest.json`.
- Step 34 runtime result: **FAIL**. The 18-glyph build reproduced the System Card startup/global
  tile corruption before gameplay. Its compact indices 3443..3460 point to `0x3F216..0x3F348`;
  this tail cannot be treated as replaceable font-only storage merely because EX_GETFNT can compute
  those indices. The manifest is marked FAIL and the build must not be used.
- Step 35 two-glyph discriminator: static build complete; runtime result pending.
  `tools/build_current_translation_two_glyph_probe.py` maps `여` to the already runtime-proven
  index 1722 (`8F6F`, BIOS `0x37914`) and `어` to the nearest unreferenced adjacent ordinary-kanji
  index 1720 (`8F6D`, BIOS `0x378F0`). Only the first dialogue body is changed to `여어`.
- Expected Write verification passed for two 18-byte BIOS slots (35 actual diff bytes) and one
  seven-byte game body run (7 diff bytes). The runtime pair is
  `SystemCard3_KoreanFont_two_glyph_probe.pce` plus
  `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_two_glyph_probe.cue`.
- Step 35 runtime result: **FAIL**. The two-glyph build reproduced the same startup/global tile
  corruption. Relative to the exact passing one-glyph baseline it changed two BIOS variables at
  once: index 1722 contained `여` instead of the proven `가`, and index 1720 was newly changed to
  `어`. The result rejects that combined BIOS but does not yet assign causality to one slot.
- Step 36 exact-baseline one-glyph E2E: static build complete; runtime result pending.
  `tools/build_one_glyph_e2e_probe.py` reuses the byte-identical, runtime-passed
  `SystemCard3_one_glyph_probe.pce` (SHA-256
  `212f3c96a4010bf06a13ceffd8dec92c00639188287f18376006cba67ebb8198`) without any new BIOS
  write. It changes only the first dialogue body from seven original bytes to `8F6F` plus five
  spaces, which should display the already proven `가` glyph.
- The paired disc is `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_one_glyph_e2e_probe.cue` and uses
  `translation/one_glyph_bizhawk_config.ini`. Full-file diff verification passed with exactly one
  seven-byte game Expected Write and no speaker/control changes.
- Step 36 runtime result: **PARTIAL PASS**. Global graphics and Hangul rendering were normal, and
  both the injected `8F6F` and the original `出` displayed the replacement `가`. However, filling
  the remaining five bytes of the first body with ASCII `0x20` caused dialogue rows to remain or
  combine across the page transition. This renderer's ASCII-space padding policy is rejected.
- Step 37 exact two-byte substitution: static build complete; runtime result pending.
  `tools/build_exact_two_byte_substitution_probe.py` uses the exact passed BIOS and replaces only
  original `よう` bytes `6F 2D` with `8F 6F`. The remaining `、シオン`, page control, speaker,
  following bodies, and NUL are byte-identical; no padding is added. The expected first body is
  `가、シオン`.
- Full-file diff verification passed with exactly two changed game bytes and zero new BIOS writes.
  Runtime CUE: `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_exact_substitution_probe.cue`.
- Step 37 runtime result: **PASS**. The game booted with normal graphics, the first page displayed
  `가、シオン`, and the next page cleared and rendered normally. The original `出` in `出来` also
  displayed the same replacement glyph, confirming consistent `8F6F` -> mode-1 index 1722 use.
- Confirmed scope: exact equal-byte substitution into the single proven slot is valid. Rejected
  scope: ASCII `0x20` padding and all multi-slot BIOS expansion attempted so far. Additional Hangul
  slots require an independently proven storage/allocation design before translation scale-up.

- Step 38, Task 1 renderer/EX_GETFNT catalogue: complete.
- A fresh scan of the original Track02 ISO found 22 raw `20 60 E0` patterns. Eighteen are confirmed
  executable calls; four (`CA59C6`, `DA615A`, `ED3080`, `10A1CAA`) have no verified instruction
  boundary or runtime hit and remain explicit `unknown` entries rather than patch targets.
- Thirteen calls share an identical 99-byte context and are one `renderer.standard_overlay` binary
  copied into independently loaded overlays. Unique confirmed families are boot, standard overlay,
  field, menu/battle common, and two card paths.
- Static System Card 3.0(J) analysis corrected the former ABI note: `$E060->$F124` writes the glyph
  into the `$FA/$FB` destination. Mode 1 expansion belongs to `$F2CC`; it emits 24 bitmap bytes plus
  eight zero bytes and leaves `$FA/$FB` advanced by 24, not 32.
- `renderer.field_main` is the first implementation target: Track02 LBA 130, 20 sectors, physical
  banks 80..84, MPR2..6=80..84, call PC 8855, destination 3328..3347, downstream VDC routine 890A.
- Task 1 passes only for the field implementation gate. Runtime loader/MPR coverage for menu,
  battle, name/item, card, and late overlays remains `unknown`; no hook was implemented.
- Evidence: `Task1_GETFNT_카탈로그.md` and `translation/getfnt_renderer_catalog.json`.

- Step 39, retroactive Task 0 baseline lock: complete.
- The original BIN, CUE, extracted Track02 ISO, and System Card 3.0(J) are locked by byte size and
  SHA-256. The original System Card also retains its SHA-1 identity for firmware comparison.
- The accepted field-dialogue visibility baseline is the exact `6F 2D -> 8F 6F` substitution paired
  with the byte-identical one-glyph diagnostic BIOS. It remains a narrow diagnostic PASS, not a
  release architecture or approval for additional BIOS slots.
- The 896-, 18-, and 2-glyph BIOS diagnostics are locked as rejected evidence and prohibited as
  build inputs. The ASCII `0x20` padding probe is locked as a partial runtime result but a policy
  FAIL because it mixed dialogue rows/pages.
- BizHawk `2.11.2+4d63f303a1e74dcb7680fbb3b327a13cf9963362`, `PCEHawk`, the one-glyph firmware override,
  exact-substitution CUE, and clean SaveRAM state form the executable reproduction contract.
- `tools/verify_task0_baseline.py` is a read-only, fail-closed preflight. It hashes all 27 locked
  files, checks CUE targets and BizHawk settings, confirms PASS/FAIL manifest semantics, and rejects
  matching stale SaveRAM before any later Task starts.
- The already completed Task 1 catalogue was checked retroactively against this baseline and is
  recorded as PASS. No game image, BIOS, firmware, emulator source, or translation CSV was modified
  while performing Task 0.
- Evidence: `Task0_기준선.md` and `translation/task0_baseline_manifest.json`.

- Step 40, Task 2 custom-code-space gate: **PASS for `renderer.field_main` only**.
- A field-boundary model scanned all 18,817 protected raw records. `EB..EF` leads occur 1,509 times
  at arbitrary adjacent positions, but zero times at actual field character boundaries; the boundary
  model reported zero errors. The conservative trail rule is `40..7E` or `80..FC`.
- Capacity is 940 pairs by parser semantics and 844 pairs when every raw-substring collision is also
  excluded. The current translation needs 904 unique Hangul glyphs globally, while the largest
  scene-local active set is 571. Global mapping therefore depends on parser-boundary semantics;
  scene-local remapping fits the conservative pool with a margin of 273 and is the preferred design.
- The legacy 896-entry `translation/char_map.json` is rejected for new builds: 144 entries use unsafe
  trails and eight currently translated Hangul glyphs are absent.
- `EF41` was selected because it uses a safe trail, is absent at every adjacent position in the
  protected raw corpus, and is not allocated by the legacy map. The diagnostic disc changed exactly
  `6F2D -> EF41` in the first body, with no padding, control, terminator, or other byte change.
- Runtime visual evidence passed the parser-boundary criterion. The `EF41` position was blank as
  expected without a custom glyph hook, while the unchanged following punctuation/name remained
  aligned and the second page cleared and rendered normally. Field graphics and MPR2..7
  (`80 81 82 83 84 00`) were normal.
- The debugger image was captured at PC `53AF`, not directly at EX_GETFNT, so it does not photograph
  F9/F8. The exact two-byte diff plus preserved following text/page boundary is accepted as equivalent
  parser-consumption evidence, not as glyph-rendering evidence. Lua tracing was abandoned because
  enabling it prevented BIOS-screen progression.
- Task 3 may use only `EF41` for its one-glyph field PoC. Bulk `EB..EF` allocation, the legacy map,
  ASCII-space padding, and all non-field renderers remain unapproved.
- Evidence: `Task2_커스텀코드공간.md`, `translation/task2_custom_code_audit.json`,
  `translation/task2_custom_code_runtime.json`, and `translation/task2_custom_code_probe_manifest.json`.

- Step 41, Task 3 field-local GETFNT hook design: **PASS; dry run only**.
- The design replaces the first-dialogue call at runtime `$8855` / ISO `0x45855` from
  `JSR $E060` (`20 60 E0`) to `JSR $BB20` (`20 20 BB`). No game image or BIOS was modified.
- The hook resides in physical bank `0x83`, already visible through MPR5 during both captured
  dialogue pages. Its selected `$BB20..$BB9F` window is 128 original `FF` bytes; the 45-byte hook
  and 32-byte expanded `가` glyph use 77 bytes and do not cross the bank boundary.
- The originally considered `$BF80` window was rejected because seven unaligned raw words pointed
  into its proposed used range. The selected `$BB20..$BB6C` used range has zero raw-word and zero
  JSR/JMP references in the original 40 KiB field module.
- For `F9:F8 != EF:41`, the hook tail-jumps to `$E060`. The patched JSR creates one caller frame and
  the fallback JMP creates none, so the BIOS RTS still returns directly to `$8858`. A/P are not BIOS
  live-ins and all effective EX_GETFNT inputs remain unchanged before the tail jump.
- For `F9:F8 == EF:41`, the hook copies the 32-byte expanded glyph to the original FA/FB destination,
  then returns A=00, X=00, Y=FF, FA/FB+24, with FF preserved. The glyph is rendered from the locked
  `font/Galmuri8x8.ttf` SHA-256 and centred as native 8x8 ink at `(2,2)` inside the 12x12 PCE cell.
- Code and glyph share the already mapped bank, so the hook contains no TMA/TAM, uses no stack-page
  scratch, and stores no state in BIOS variables or shared Work RAM. The existing dry-run fetch-hook
  area at `$A339` is untouched.
- Task 4 must enforce exactly the two hook Expected Writes recorded in
  `translation/task3_field_getfnt_hook_design.json`, then separately apply the Task 2 exact
  `6F2D -> EF41` dialogue substitution for runtime validation.
- Evidence: `Task3_필드_GETFNT_훅설계.md`, `translation/task3_field_getfnt_hook_design.json`,
  `translation/task3_field_getfnt_hook.bin`, and `tools/verify_task3_field_getfnt_hook.py`.

- Font policy update: all newly created builds from Task 3 onward must use only
  `font/Galmuri8x8.ttf` (SHA-256 `97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05`).
  The bitmap font's native 8x8 ink is centred at `(2,2)` in the 12x12 field cell, producing a
  16x16/32-byte MSB-first glyph. Older Galmuri11-based scripts and locked diagnostics remain solely
  as historical reproduction evidence and are prohibited as inputs to new builds.

- Step 42, Task 4 original-BIOS one-glyph field hook PoC: **static PASS; runtime pending**.
- The PoC uses the original, unmodified System Card 3.0(J) from
  `H:/BizHawk/Firmware/PCECD_3.0-(J).pce`; its locked SHA-256 is
  `E11527B3B96CE112A037138988CA72FD117A6B0779C2480D9E03EAEBECE3D9CE`.
- Exactly three declared spans were written: field call `0x45855` changes `JSR E060` to
  `JSR BB20`; field padding `0x48B20` receives the 77-byte Task 3 hook plus one `가` glyph;
  and first-dialogue bytes `0x10B9F2` change exactly from `6F2D` to `EF41`.
- The glyph comes only from locked `font/Galmuri8x8.ttf`. No BIOS font, legacy mapping,
  padding, speaker name, page control, terminator, MPR state, or shared Work RAM is changed.
- Full-BIN audit passed: size remains 523,184,384 bytes, 80 bytes actually differ, and no
  changed byte lies outside the three Expected Write spans. Output BIN SHA-256 is
  `09539211F77291760E84151703647969BA180AFF4A94CE75C69CB7F140776957`.
- Runtime image: `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_task4_field_hook_poc.cue`.
  Launch configuration: `translation/task4_field_hook_poc_bizhawk_config.ini`; no Lua.
- Step 42 runtime result: **FAIL**. A fresh run kept boot, field graphics, the later original `出`,
  and the first three page transitions normal, but the `EF41` position did not display `가` and
  resembled the Task 2 no-hook blank/stale mark. Task 4 is not approved.
- Task 2 proved equal-byte parser alignment visually, but its failed Lua run never directly captured
  live F8/F9 at EX_GETFNT. A separate unconditional one-glyph reachability build is therefore the
  next discriminator: if all field double-byte glyphs become Galmuri8x8 `가`, the call/cave/glyph
  path is alive and conditional dispatch is at fault; if Japanese remains, the selected callsite is
  not the live path. Evidence: `translation/task4_field_hook_poc_runtime.json`.

- Step 43, Task 4 callsite correction: the unconditional probe left all Japanese unchanged, proving
  ISO `0x45855` / runtime `$8855` was not the first-field renderer path.
- Root cause: `translation/cd_read_trace.tsv` LBA 258 was already Track02-relative. Task 1 had
  incorrectly subtracted a 128-sector bias, selecting module `0x41000` instead of the live module
  loaded from Track02 ISO `0x81000` at frame 1237.
- The corrected live call is ISO `0x8667E`, runtime `$967E`. The corrected local cave begins at
  ISO `0x89737`, runtime `$C737`, immediately after an RTS and before the `0x89900` pointer table.
  Its 457 FF bytes have zero original JSR/JMP references; six unaligned raw-word overlaps are retained
  in the audit rather than misreported as executable references.
- Task 3 was regenerated for `JSR $C737`; its 77-byte hook/glyph uses MPR6 physical bank `0x84` and
  still performs no MPR change or stack/shared-RAM scratch access.
- Corrected Task 4 v2 static build passed with 80 changed bytes, zero undeclared changes, preserved
  523,184,384-byte size, and BIN SHA-256
  `4DA30EA2002BC1CAA7E1207FFFA0C2A2B45893D600433494E2A2DF2EA664189B`.
- Runtime CUE: `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_task4_field_hook_poc_v2.cue`.
  At the Step 43 static-build checkpoint, Task 4 v2 was runtime pending; Step 44 records its final result.

- Step 44, corrected Task 4 v2 runtime verification: **PASS**.
- A fresh Lua-free run of the v2 CUE displayed the Galmuri8x8 `가` only at the first-dialogue
  `EF41` substitution. This proves the corrected runtime `$967E` callsite, `$C737` local hook,
  and MPR6 bank `0x84` glyph path are live on the observed field renderer path.
- The next original page rendered `支度は出来たのかフェイト` with its Japanese `出` unchanged,
  proving the non-custom path still falls back to the original BIOS renderer.
- Field background, sprites, dialogue window, page clearing and progression remained normal.
- Task 4 is approved only for one custom glyph on `renderer.field_main`'s first-dialogue path.
  Multi-glyph mapping, other renderers, relocated strings and full-game coverage remain unproved.
- Evidence: `translation/task4_field_hook_poc_v2_runtime.json` and
  `translation/task4_field_hook_poc_v2_manifest.json`.

- Step 45, Task 5 field multi-glyph PoC static build: **PASS; runtime pending**.
- The representative second body `支度は出来たのかフェイト` occupies exactly 16 bytes because
  four kanji are two-byte codes and the remaining source glyphs are single-byte. The current
  translation was cut only at a complete glyph boundary to `준비는다됐나페이`, exactly eight
  two-byte codes and the same 16-byte budget. No ASCII space, padding, terminator or source tail
  is present in the replacement.
- The local map uses protected-raw-absent consecutive pairs `EF58..EF5F`. Its eight Galmuri8x8
  glyphs occupy the aligned `$C800..$C8FF` page in the already resident MPR6 physical bank `0x84`.
- The `$C737` hook subtracts `0x58`, rejects indices outside 0..7, multiplies the accepted index
  by 32 and copies from the aligned glyph page. It changes no MPR, uses no stack/shared-RAM scratch,
  and sends every non-custom code to the original BIOS with `JMP $E060`.
- The build starts from the locked original BIN, declares three Expected Writes, preserves the
  523,184,384-byte size, and reports 328 actually changed bytes with zero undeclared changes.
- Evidence: `Task5_필드_다글자_PoC.md`, `translation/task5_field_multiglyph_map.json`,
  `translation/task5_field_multiglyph_poc_manifest.json`, and
  `tools/verify_task5_field_multiglyph_poc.py`.

- Step 46, Task 5 runtime display gate: **PASS; extended stability pending**.
- The first captured page remained Japanese with normal field graphics. The following page rendered
  `준비는다됐나페이` as eight distinct Galmuri8x8 glyphs in the declared `EF58..EF5F` order.
  Representative final-consonant and complex-vowel shapes (`준`, `됐`) remained distinguishable.
- The observed page transition was normal, so the eight-code parser/map/pool/display chain and the
  same-session BIOS fallback are approved for this field event.
- Field exit/re-entry, twenty scene transitions and the absence of `EXEC BRK` during that extended
  run were not observed. Task 5 therefore remains `DISPLAY PASS / STABILITY PENDING` rather than
  final PASS.
- Evidence: `translation/task5_field_multiglyph_poc_runtime.json`.

- Step 47, Task 5 extended stability result: **FAIL at Memo entry**.
- The eight-glyph dialogue display and first-field progression remained normal, and the field menu
  itself rendered normally. Selecting `メモ` then made EmuHawk unresponsive.
- This invalidates Task 5 as a stable implementation even though its display gate passed.
- The first discriminator keeps the exact live call, 55-byte hook and eight `EF58..EF5F` codes,
  while leaving runtime `$C800..$C8FF` at the original `FF` bytes. If Memo becomes responsive, the
  256-byte expanded glyph page is the causal collision; if it still hangs, the page-only hypothesis
  is rejected and the repeated custom path/ABI becomes the next target.
- Evidence: `translation/task5_field_multiglyph_poc_runtime.json` and
  `translation/task5_c800_isolation_probe_manifest.json`.

- Step 48, C800 isolation runtime: **FAIL; glyph-page collision hypothesis rejected**.
- Restoring runtime `$C800..$C8FF` to all-original `FF` did not change the Memo hang.
- The attached 10,002-line trace contains no `$C737` field-hook execution. It runs in the Memo
  overlay with MPR5=`96`, MPR6=`7F` and repeatedly visits `$4E6C..$4EB9`.
- At `$4E0F`, `LDA ($D8)` returns `00`, `TAX` makes X=`00`, and `$4E6B` enters a copy routine that
  performs `DEX` before testing zero. X therefore underflows to `FF`, producing a 256-iteration
  copy instead of an empty operation and making EmuHawk appear hung.
- This is a downstream failure state, not yet the first corrupting writer. The next discriminator
  removes the hook and glyph pool while retaining only the 16-byte `EF58..EF5F` dialogue body.
- Evidence: `translation/task5_c800_isolation_probe_runtime.json` and the attached BizHawk trace.

- Step 49, custom-text-only runtime: **PASS; text bytes alone are not causal**.
- With only the 16-byte `EF58..EF5F` dialogue replacement and no `$C737` hook or `$C800`
  glyph page, Memo opened normally and remained responsive.
- Together with Step 48, this isolates the failure to execution of the custom hook path. The next
  implementation no longer bypasses System Card EX_GETFNT: custom codes first call `$E060` with
  untouched inputs, then the hook restores its saved destination and overwrites only the 32-byte
  glyph output. This preserves BIOS-owned scratch and hidden state before returning the documented
  mode-1 visible ABI.
- Evidence: `translation/task5_custom_text_only_probe_runtime.json`.

- Step 50, BIOS-shadow multi-glyph runtime: **FAIL**.
- Calling the original `$E060` for every custom code before restoring the destination and
  overwriting the glyph did not prevent the Memo hang. The hidden-BIOS-side-effect hypothesis is
  therefore rejected.
- The new trace again reaches the Memo overlay with MPR5=`96`, MPR6=`7F`; `$C737` does not execute
  inside the captured Memo interval. `$4E0F` supplies X=`00` to `$4E6B`, whose decrement-before-zero
  loop underflows and repeats.
- The next probe preserves the call redirection and exact 55-byte dispatcher but restores the
  original Japanese dialogue and leaves `$C800..$C8FF` untouched. It distinguishes hook
  installation/fallback from any execution of the custom branch.
- Evidence: `translation/task5_bios_shadow_multiglyph_poc_runtime.json`.

- Step 51, fallback-only hook runtime: **FAIL; custom branch is not required**.
- Original Japanese dialogue, an untouched `$C800..$C8FF` page, and a dispatcher run that never
  matched the custom branch still produced the same Memo hang. This removes the custom codes,
  glyph pool, glyph copy and BIOS-shadow behavior from the causal set.
- The 55-byte fallback dispatcher nevertheless executes `LDA/CMP` classification before
  `JMP $E060`, changing A and processor flags P. Task 1 did not classify A/P as live BIOS inputs,
  but the runtime isolation result requires that assumption to be tested directly.
- The next probe changes only five actual bytes: the live call still redirects to `$C737`, while
  `$C737` contains only `JMP $E060`. It preserves A/X/Y/P, stack, zero-page parameters and all
  RAM exactly, apart from the extra JMP timing. Original Japanese output is expected.
- Evidence: `translation/task5_fallback_only_probe_runtime.json` and
  `translation/task5_transparent_trampoline_probe_manifest.json`.

- Step 52, transparent `$C737 -> $E060` trampoline runtime: **FAIL; A/P clobber rejected**.
- The original Japanese path still hung on Memo even though `$C737` contained only `JMP $E060`.
  No classification or custom instruction changed A, X, Y, P, stack, zero-page parameters, RAM or
  glyph output before BIOS entry.
- The remaining difference from the original is the two-byte call redirection plus three occupied
  bytes at `$C737`, and execution of one additional JMP. The next probe restores the live call to
  its exact original `JSR $E060` and leaves only the inert three-byte `$C737` marker. A responsive
  Memo proves cave occupancy is safe and isolates redirected execution/timing; another hang proves
  `$C737` is not actually free over the later overlay lifecycle.
- Evidence: `translation/task5_transparent_trampoline_probe_runtime.json` and
  `translation/task5_cave_occupancy_probe_manifest.json`.

- Step 53, inert `$C737` cave-occupancy runtime: **PASS**.
- With the live renderer call restored byte-for-byte to `JSR $E060`, changing only the three bytes
  at `$C737` did not affect field rendering or Memo entry. The cave is safe to occupy; cave content
  alone is not causal.
- System Card ROM offset `0x0060` is `4C 24 F1`, so `$E060` is itself only `JMP $F124`.
  The failed transparent probe executed two JMPs (`C737 -> E060 -> F124`) where the original executes
  one (`E060 -> F124`). The next probe uses `C737 -> F124` directly, restoring the exact original
  one-JSR/one-JMP instruction count, caller stack frame and BIOS implementation entry.
- Evidence: `translation/task5_cave_occupancy_probe_runtime.json` and
  `translation/task5_cycle_matched_trampoline_probe_manifest.json`.

- Step 54, cycle-matched `$C737 -> $F124` runtime: **FAIL**.
- Matching the original one-JSR/one-JMP instruction count, return frame and BIOS implementation
  entry did not prevent the Memo hang. The extra-JMP instruction-count hypothesis is rejected.
- A refreshed 10,002-line trace captures the first bad Memo sequence: `$4E01` selects object index
  `00`; pointer-table loads at `$4E05/$4E0A` produce `0000`; `$4E0F` reads length `00`; and X=0
  enters the decrement-before-zero `$4E6B` loop. The trace began earlier but its fixed retained
  window overwrote the field interval, so it contains no `$967E/$C737/$E060/$F124` entries.
- The next probe leaves `$C737` and its glyph page completely original and changes only the live
  call from `JSR $E060` to direct `JSR $F124`. This separates any execution/fetch through module
  RAM from the call-operand/timing change itself.
- Evidence: `translation/task5_cycle_matched_trampoline_probe_runtime.json` and
  `translation/task5_direct_bios_entry_probe_manifest.json`.

- Step 55, direct `JSR $F124` BIOS-entry runtime: **PASS**.
- Changing only the live call operand from `$E060` to the real BIOS implementation `$F124` kept
  original field output and allowed normal Memo entry. `$C737` and `$C800..$C8FF` remained original.
- Therefore a changed call operand and a four-cycle GETFNT timing reduction are both compatible with
  normal behavior. The failed controls specifically require executing/fetching through `$C737` in
  module RAM.
- The next probe moves the identical cycle-matched `JMP $F124` trampoline to `$C800` in the same
  MPR6 bank. It distinguishes a `$C737`-specific execution problem from module-RAM trampoline
  execution generally before the redirect architecture is retained or discarded.
- Evidence: `translation/task5_direct_bios_entry_probe_runtime.json` and
  `translation/task5_c800_trampoline_probe_manifest.json`.

- Step 56, relocated `$C800 -> $F124` trampoline runtime: **FAIL**.
- Moving the identical cycle-matched trampoline from `$C737` to `$C800` did not prevent the Memo
  hang. The failure is therefore not specific to `$C737`; both failed locations execute from MPR6
  physical bank `0x84`, whose large FF region had been selected as data-bank padding.
- A corrected physical-BIN scan found no usable long cave in the caller's packed MPR4 bank. It did
  find `$5230..$52AF`, a 128-byte zero run in MPR2 physical bank `0x80`, immediately after an RTS
  and before the next initialization routine. The entire module contains zero absolute references
  and zero raw-word overlaps into this run, and observed field execution already uses nearby `$53AF`.
- The next probe executes only `JMP $F124` at `$5230`. A responsive Memo approves this code-bank
  location and permits `$C800` to remain data-only; another hang rejects callsite RAM redirects.
- Evidence: `translation/task5_c800_trampoline_probe_runtime.json` and
  `translation/task5_5230_codebank_trampoline_probe_manifest.json`.

- Step 57, MPR2 `$5230 -> $F124` code-bank trampoline runtime: **PASS**.
- The redirected call preserved original field output and Memo opened normally when the trampoline
  executed from physical bank `0x80` at `$5230`. This proves callsite redirection and RAM execution
  are valid when code resides in an established executable bank.
- The Task 5 hang is therefore attributed to executing hook instructions from MPR6 physical bank
  `0x84`, which is retained only as a data bank. Call-operand changes, cave occupancy, custom text,
  C800 glyph bytes and BIOS ABI omission were independently rejected as sufficient causes.
- The revised multi-glyph architecture places its 55-byte EF58..EF5F dispatcher at `$5230`, keeps
  the eight Galmuri8x8 expanded glyphs at `$C800..$C8FF` as non-executable data, and sends fallback
  directly to BIOS `$F124`.
- Evidence: `translation/task5_5230_codebank_trampoline_probe_runtime.json` and
  `translation/task5_5230_codebank_multiglyph_poc_manifest.json`.

- Step 58, revised `$5230` code / `$C800` data eight-glyph runtime: **PASS for the observed gate**.
- The eight Galmuri8x8 Korean glyphs displayed normally and the field Memo menu opened normally in
  the same session. This closes the reproducible Task 5 Memo regression for the tested first-field
  event.
- The approved architecture is now split by ownership: executable dispatcher code lives only in
  MPR2 physical bank `0x80` at `$5230`, while MPR6 physical bank `0x84` contains only the expanded
  glyph data page at `$C800..$C8FF`. Non-custom codes fall through directly to BIOS `$F124`.
- This PASS covers the observed eight-glyph field display, BIOS fallback continuity and Memo entry.
  It does not yet prove all field scenes, twenty transitions, other renderers, full-text reinsertion
  or long-session absence of `EXEC BRK`.
- Evidence: `translation/task5_5230_codebank_multiglyph_poc_runtime.json` and
  `translation/task5_5230_codebank_multiglyph_poc_manifest.json`.

- Step 59, Task 6 full-translation module budget: **capacity gate PASS with 17 release-input blockers**.
- The completed `translation/full_extraction/master_text.csv` contains 18,817 rows, no empty
  translations, no control-token order mismatches and 1,053 unique Hangul glyphs. Its SHA-256 is
  `36AAE2700FB2639A29BBCC3770EFC203BF494997A722DD0C85B8F6026E560AC0`.
- The global repertoire exceeds the 940 custom-code candidates by 113, but the largest active
  loader set is 609 glyphs. This validates local remapping and rejects treating the global count as
  every scene's resident budget.
- Across 85 primary/overlay loader contexts, the proven 32-byte path has 28 direct fits, 14
  source-hole materialization branches and 43 scene-load sidecar branches. The 18-byte model has
  39 direct fit estimates, 4 source-hole branches and 42 sidecar/module-split branches; it remains
  unproven until a packed-glyph expander PoC passes.
- All 55 physical grids and 55 menu/battle renderer demand groups are classified as a fit or an
  explicit next branch. Seventeen `needs_review` entries are included in capacity totals but remain
  barred from release builds.
- Task 0 immutable BIN/CUE/Track02/System Card hashes still match. The legacy full preflight cannot
  finish because the archived accepted-probe CUE is absent from the project root; this does not
  change the Track02 capacity result but remains a release-build preflight blocker.
- Evidence: `Task6_모듈별_글리프_예산.md`,
  `translation/task6_module_glyph_budget.json`, and
  `outputs/019f55dd-966e-7f81-aed7-0f92ef88e1c9/Task6_module_glyph_budget.xlsx`.

- Step 60, Task 7 packed 18-byte glyph expander gate: **runtime PASS for the observed field gate**.
- The first overflow-supply experiment preserves the approved Task 5 ownership split: executable
  HuC6280 code occupies the exact 128-byte MPR2 `$5230..$52AF` cave, while eight Galmuri8x8 glyphs
  remain non-executable MPR6 data at `$C800..$C88F`.
- Each 12x12 glyph is stored as the System Card mode-1 18-byte row-pair format and expanded by the
  hook into the caller's existing 16x16/32-byte destination. All eight records round-trip exactly,
  reducing the probe pool from 256 to 144 bytes (43.75%). Non-custom codes still jump directly to
  BIOS `$F124`, and the hook changes no MPR.
- Expected Write and full-BIN diff audits pass. The generated 128-byte image disassembles through
  the complete BizHawk HuC6280 disassembler as 71 instructions ending exactly at `$52B0`; every
  relative branch and internal JSR target stays inside the hook and the sole external JMP is the
  reviewed BIOS fallback `$F124`.
- EmuHawk was launched without Lua using
  `Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_task7_packed18_expander_poc.cue`. The user confirmed the
  second Korean dialogue, the following original Japanese BIOS-fallback dialogue, and normal Memo
  entry in the same session. This promotes the packed-18 field expansion gate to PASS, without
  generalizing it to other renderers or sidecar loading.
- Evidence: `translation/task7_packed18_expander_poc_manifest.json`,
  `translation/task7_packed18_glyph_map.json`,
  `tools/verify_task7_packed18_expander_poc.py`, and
  `tools/huc6280_disasm_verifier/`.

- Step 61, Task 7 packed-18 loader branch plan: **disk-capacity PASS; sidecar RAM reachability pending**.
- Recomputing glyph supply separately from Task 8 string relocation classifies all 85 loader
  contexts: 42 fit in existing whole-bank capacity, 26 fit only after source-hole materialization,
  and 17 require a scene-load sidecar shard. Branch B is a package policy rather than a permanent
  resident pool: globally frequent core glyphs are replicated into each module's own lifetime.
- The 17 independently aligned sidecar shards occupy only 22 of the verified 150 sectors starting
  at LBA 9178. The largest scene needs 4,140 transient bytes, so disk storage is no longer the
  blocker. No RAM address is approved yet: one representative loader must prove that its sidecar
  shard is read during scene load, remains intact through final glyph consumption, and is released
  on scene exit without a global pointer.
- Evidence: `translation/task7_packed18_expander_poc_runtime.json`,
  `translation/task7_overflow_supply_plan.json`, and
  `tools/verify_task7_overflow_supply.py`.

- Step 62, Task 7 battle regression isolation: **MPR2 `$5230` execution approval revoked**.
- The packed-18 field gate remained valid only for the first dialogue, Japanese fallback and Memo.
  In the first battle, selecting Attack corrupted the scene/overlay state and prevented progress.
- The unmodified game returned from the same battle normally, and a text-only custom-code control
  also returned normally. A `$5230` cave-occupancy-only control passed, while the original-Japanese
  `JSR $5230 / JMP $F124` redirect-only control failed. Direct `JSR $F124` returned normally.
- These controls reject custom text bytes, `$5230` disk occupancy and the BIOS implementation as
  sufficient causes. They identify execution through logical `$5230` as the failed assumption:
  MPR2=`$80` was observed in the first field but was not proved invariant across battle overlays.
- The former Step 57/58 approval is therefore limited to the first-field/Memo gate and must not be
  used as a release architecture.
- Evidence: `translation/task7_5230_cave_only_control_manifest.json`,
  `translation/task7_bios_fallback_control_manifest.json`, and the direct-BIOS Task 5 controls.

- Step 63, fixed-MPR7 System Card hook experiment: **rejected**.
- BizHawk initially appeared to accept modified BIOS controls, but it was actually selecting the
  original SHA-1-recognised `.bak` file from the recursive Firmware scan. After moving that backup
  outside the Firmware directory and setting `FirmwareUserSpecifications["PCECD+Bios"]`, modified
  BIOS images were genuinely loaded.
- The apparent 280-byte `$FEC4..$FFDB` FF run is not an approved code cave. A control that left the
  game and `$E060 -> $F124` entry original and changed only three bytes at `$FEC4` still corrupted
  the initial display. Global `$E060 -> $FEC4 -> $F124`, BIOS-local glyph data, and a game-only
  `JSR $FEC4` dispatcher all failed for the same reason.
- The System Card was restored to SHA-256
  `E11527B3B96CE112A037138988CA72FD117A6B0779C2480D9E03EAEBECE3D9CE`, the firmware override was
  removed by restoring the original BizHawk config, and the unmodified game was relaunched.
- Future hook placement must use a runtime-lifetime-proved fixed Work RAM allocation or relocate
  code within the caller's own physical bank. Repeated `00`/`FF` bytes, static reference counts and
  a stable logical address observed in one scene are not sufficient approval gates.
- Evidence: `translation/task7_bios_cave_occupancy_control_manifest.json`,
  `translation/task7_fixed_bios_callsite_poc_manifest.json`, and
  `tools/build_task7_bios_cave_occupancy_control.py`.

- Step 64, fixed Work RAM lifetime trace and collision audit: **post-load neutral-PoC eligible**.
- A core-level trace started after the first LBA 482/count 96 field load and covered 3,122 frames:
  first dialogue, Memo, LBA 290 battle overlay, Attack, and LBA 482 field return. Work RAM
  `$2AFF..$2C8E` (physical bank `$F8`, 400 bytes) had zero reads and zero writes throughout that
  window. It was the only non-direct-page run of at least 160 contiguous bytes.
- MPR1 remained `$F8` at all three observed CD boundaries. The span does not overlap `$2000..$20FF`
  direct page, `$2100..$21FF` stack, `$2200..$22FF` BIOS/shared variables, or the rejected
  `$3C00..$3CFF` experiment.
- This is not a boot-resident allocation: the earlier global trace wrote 379 of its 400 bytes at
  frames 121, 135 or 502. Any probe must install code only after the field load completes.
- The 400-byte span can hold the prior 128-byte packed-18 hook, but cannot hold the largest 4,140-byte
  sidecar shard. Approval is limited to the next neutral `JMP $F124` trampoline test and must not be
  generalized to unplayed routes.
- The temporary diagnostic core was removed after capture and `H:\BizHawk\dll\BizHawk.Emulation.Cores.dll`
  was restored to SHA-256 `36D755B904E747E7705778787B7A2BD06502E72589C7F2F6E5CE203233EAF53B`.
- Evidence: `translation/task7_work_ram_long_trace.tsv`,
  `translation/task7_work_ram_lifetime_verdict.json`,
  `translation/task7_work_ram_candidate_audit.json`,
  `tools/analyze_task7_work_ram_lifetime.py`, and
  `tools/audit_task7_work_ram_candidate.py`.

- Step 65, Work RAM `$2AFF` neutral trampoline: **runtime PASS**.
- The disk call initially uses `JSR $5230`. The 28-byte one-shot loader writes `JMP $F124` to fixed
  Work RAM `$2AFF`, rewrites the already loaded call operand at `$967F/$9680` from `$5230` to
  `$2AFF`, and tail-jumps to `$F124` for the first call. Every later call is therefore
  `JSR $2AFF -> JMP $F124` and no longer depends on MPR2 mapping.
- The probe changed no dialogue or glyph data and changed no MPR. The user confirmed original
  dialogue, responsive Memo, normal battle Attack, and correct field return in one session.
- This approves `$2AFF` as executable post-load storage for this representative route. It does not
  approve the remaining 397 bytes for arbitrary data or establish whole-game lifetime.
- Evidence: `translation/task7_workram_trampoline_poc_manifest.json`,
  `tools/build_task7_work_ram_trampoline_poc.py`, and
  `tools/verify_task7_work_ram_trampoline_poc.py`.

- Step 66, tower-extended Work RAM trace: **former `$2AFF` approval revoked; `$2B0F` neutral test pending**.
- The original game was traced for 2,552 frames from the first LBA 482 field load through LBA 290
  battle and the later LBA 2882 tower load. Unlike the shorter route, the tower route's untouched
  run begins at `$2B0F`, proving that at least one address in `$2AFF..$2B0E` is used. The relocated
  packed-18 hook occupied `$2AFF..$2B7D`, so tower activity overlapped its first 16-byte window and
  explains the observed freeze.
- Intersecting both route verdicts rejects the tower-only `$3141` run and leaves exactly one common
  candidate: physical `$F8`, logical `$2B0F..$2C8E`, 384 bytes. This is enough for the 127-byte hook
  but is not approved until a neutral `JMP $F124` probe passes through the tower.
- The diagnostic core was again restored to SHA-256
  `36D755B904E747E7705778787B7A2BD06502E72589C7F2F6E5CE203233EAF53B` after capture.
- Evidence: `translation/task7_work_ram_tower_trace.tsv`,
  `translation/task7_work_ram_tower_verdict.json`,
  `translation/task7_work_ram_common_verdict.json`, and
  `tools/analyze_task7_work_ram_trace_intersection.py`.

- Step 67, common-route Work RAM `$2B0F` neutral trampoline: **runtime PASS through tower**.
- The neutral probe installs only `JMP $F124` at `$2B0F` and self-modifies the live call to
  `JSR $2B0F`. It contains no Korean text, custom glyph data or MPR changes.
- The user confirmed dialogue, Memo, battle Attack, field return, tower entry, and progression past
  the former freeze point. This approves executable post-load use of the three bytes at `$2B0F`
  across both observed routes; the remaining common span still requires payload-specific testing.
- Evidence: `translation/task7_tower_workram_trampoline_poc_manifest.json`,
  `tools/build_task7_tower_work_ram_trampoline_poc.py`, and
  `tools/verify_task7_tower_work_ram_trampoline_poc.py`.

- Step 68, tower-safe packed-18 hook at `$2B0F`: **runtime PASS**.
- The 127-byte hook was reassembled for `$2B0F..$2B8D`; all internal JSR and branch targets were
  recalculated and the complete 73-instruction image disassembled to the exact end `$2B8E`.
- The first call's 24-byte `$5230` loader preserves A/P, copies the non-executable source image with
  `TII $C737,$2B0F,$007F`, rewrites the live call to `JSR $2B0F`, restores A/P, and enters the copied
  hook. Later calls do not depend on MPR2. No MPR is changed by the loader or hook.
- The user confirmed eight Korean glyphs, the following Japanese BIOS fallback, responsive Memo,
  normal battle Attack and field return, tower entry, and progression past the former freeze point.
- This build supersedes the failed `$2AFF` packed-18 placement and is the only approved execution
  baseline for module expansion. Approval still covers the observed routes, not the whole game.
- Evidence: `translation/task7_tower_workram_packed18_poc_manifest.json`,
  `translation/task7_tower_workram_packed18_glyph_map.json`,
  `tools/build_task7_tower_work_ram_packed18_poc.py`, and
  `tools/verify_task7_tower_work_ram_packed18_poc.py`.

- Step 69, cross-loader tail-capacity correction: **static PASS; prior internal-fit counts superseded**.
- The Task 6 whole-bank figure measured only the unused part of each loader's 96-sector RAM window.
  It did not prove that the corresponding disc sectors were free, because primary and overlay
  records intentionally share physical sectors. Every candidate bank is now rejected when it
  intersects any other live primary/overlay loader range.
- Of 1,499,136 nominal tail bytes, only 385,024 bytes are collision-safe. Forty-eight modules had
  a nominal tail, but only thirteen retain any collision-safe tail and only eleven can hold their
  complete packed-18 supply there. The corrected branches are 11 collision-safe internal, 31
  Task-8 source-hole dependent, and 43 scene-load sidecar.
- In particular, `loader.primary.g27.lba2754` has 16,384 nominal bytes in relative banks 22..23,
  but both banks overlap the live overlay beginning at LBA 2786. Its collision-safe capacity is
  zero; no package or sentinel may be written there.
- This audit changes no BIN/ISO. The next runtime gate must use the verified LBA 9178 sidecar area
  and separately prove a transient RAM destination/lifetime; it must not extend a primary loader
  into overlapping overlay data.
- Evidence: `translation/task7_cross_loader_capacity_audit.json`,
  `tools/audit_task7_cross_loader_capacity.py`, and
  `tools/verify_task7_cross_loader_capacity.py`.

- Step 70, LBA 482 sidecar-to-transient-bank consumption gate: **extended-route FAIL; bank `$6C` approval revoked**.
- The original LBA 482/count 96 scene read at `$66FC` now calls a 39-byte module-local wrapper at
  `$5250`. The wrapper first performs the original `JSR $E009`; only when that read succeeds does
  it issue a second mode-06 read for one sector at LBA 9185 into physical Super RAM bank `$6C`.
  An original-read failure returns immediately with its original A result.
- LBA 9185 contains eight Galmuri packed-18 glyphs (144 bytes) followed by 1,904 zero bytes. The
  tower-safe Work RAM hook remains at `$2B0F`, but its custom path now maps MPR6 to `$6C` and reads
  `$C000..$C08F`. `TMA #$40 / PHA` and `PLA / TAM #$40` balance the mapping on the custom return;
  the Japanese BIOS fallback never changes an MPR. No glyph bytes are installed at the former
  field-local `$C800` pool, so successful Korean output proves real sidecar consumption.
- The builder starts from the locked original BIN, guards every original span, preserves file
  size, and the verifier audits the full BIN diff, wrapper branch target, sidecar sector layout,
  packed-glyph expansion, and the MPR6 map/restore sequences.
- On 2026-07-18 the user initially confirmed normal progression through the tower with this exact build.
  Because the build contains no fallback copy at `$C800`, the observed Korean rendering proves
  that the LBA 9185 sector was loaded into bank `$6C` and consumed through the temporary MPR6 map.
  A later dialogue on the same continued route displayed a black rectangle instead of the character
  portrait. The original-disc control, replayed from the pre-run SaveRAM, displayed the portrait
  normally. The original LBA 482/count 96 read fills banks `$68..$7F`; the PoC's second read into
  `$6C` therefore overwrote the fifth bank of the live scene module. The earlier trace had ended
  before that bank was consumed. The sidecar disk-sector proof remains useful, but the complete
  load/consume approval and destination bank `$6C` are revoked.
- Evidence: `translation/task7_lba482_sidecar_consume_poc_manifest.json`,
  `translation/task7_lba482_sidecar_glyph_map.json`,
  `tools/build_task7_lba482_sidecar_consume_poc.py`, and
  `tools/verify_task7_lba482_sidecar_consume_poc.py`.

- Step 71, corrected 43-shard sidecar repack: **static capacity PASS; zero runtime-approved destinations**.
- The obsolete 17-shard Step 61 layout was discarded after the cross-loader collision audit.
  Each corrected sidecar module now keeps as much fixed metadata and packed glyph data as its
  collision-safe tail plus Task-8 source holes can hold; only the exact remainder is assigned to
  an independently sector-aligned sidecar shard with a reserved 64-byte header.
- All 43 shards occupy 76 of the verified 150 sectors at LBA 9178..9327, leaving 74 sectors.
  Total transient content is 110,152 bytes before headers. The largest single requirement is
  5,564 bytes / 3 sectors for `loader.primary.g33.lba3330`.
- The former representative `loader.overlay.g02.lba482` remains pinned to LBA 9185 only to preserve
  deterministic disk layout. Its runtime status is now `REJECTED_EXTENDED_ROUTE_BANK_6C_COLLISION`;
  no module has an approved transient destination and all 43 lifetimes remain pending. Disk capacity
  is still approved globally, while RAM destination and preservation remain per-loader gates.
- This step changes no BIN/ISO. The next implementation gate must select another representative
  loader from a different owner/size class and prove its scene-local read and transient lifetime.
- Evidence: `translation/task7_corrected_sidecar_layout.json`,
  `tools/plan_task7_corrected_sidecar_layout.py`, and
  `tools/verify_task7_corrected_sidecar_layout.py`.

- Step 72, LBA 3330 maximum-representative RAM lifetime gate: **first trace incomplete; owner-discovery control in progress**.
- The selected context is `loader.primary.g33.lba3330`, the largest corrected sidecar owner:
  5,564 transient bytes in three sectors planned at LBA 9232..9234. Static disassembly confirms
  that logical loader index `$3FFF` is multiplied by four, read from table `$54A5`, and issued
  through the common mode-06 `$E009` CD_READ path with LBA 3330/count 83 and destination bank
  from `$22D0`.
- The temporary PCEHawk core starts its access window only after that exact CD_READ returns. It
  records Work RAM, CD RAM and Super RAM reads/writes until the next large scene load, and never
  changes emulation state. The analyzer excludes fixed Work RAM from candidate ranking and requires
  one contiguous CD/Super RAM run of at least 5,564 bytes.
- BizHawk must be built with assembly/file version `2.11.2.0` and product version
  `2.11.2+4d63f303a1e74dcb7680fbb3b327a13cf9963362`; the default development version `1.0.0.0`
  is rejected by the installed `H:\BizHawk` frontend. The corrected diagnostic build is running
  without Lua and currently reports `WAITING_FOR_TARGET_LOAD`.
- The first 12,133-frame run ended without any LBA 3330/count 83 read. Its verdict is
  `TRACE_INCOMPLETE_TARGET_WINDOW_NOT_OBSERVED`; therefore its untouched runs are not candidates
  and no RAM bank was approved. During that run the user observed a missing character portrait,
  while dialogue and progression otherwise remained normal. This visual regression is tracked
  separately and cannot be waived by the lifetime result.
- A new original-disc control was created with the pre-run sidecar SaveRAM backup under an isolated
  game name. Its diagnostic core logs every `$E009` CD_READ (LBA, count, destination bank, mode and
  MPRs) while still waiting for the exact LBA 3330 target. Replaying the same segment will both
  identify the real loader owner of the portrait scene and show whether the portrait loss exists
  in the unmodified disc.
- Evidence: `translation/task7_lba3330_ram_lifetime_trace.tsv`,
  `translation/task7_lba3330_ram_lifetime_verdict.json`, and
  `tools/analyze_task7_lba3330_ram_lifetime.py`. Pending control evidence:
  `translation/task7_portrait_original_control_cd_trace.tsv`.

- Step 73, LBA 482 extended-route RAM re-audit: **portrait window captured; full scene lifetime pending**.
- The original-disc portrait control proved that the black rectangle is introduced by the sidecar
  PoC, not by the diagnostic core or SaveRAM. The first all-CD trace identifies the owning scene
  load as LBA 482/count 96 into bank `$68`; therefore the sidecar destination `$6C` lies inside the
  primary module's live `$68..$7F` range.
- The original control has been restarted from the same pre-run SaveRAM with an exact LBA 482
  lifetime window. It records all reads/writes after that load through the portrait dialogue so a
  replacement destination can be ranked from the extended route. Pending evidence:
  `translation/task7_lba482_extended_route_trace.tsv`.
- The portrait trace observed the exact target and covered 1,673 post-load frames, but ended by
  emulator exit rather than the next large CD load. It therefore remains
  `TRACE_INCOMPLETE_SCENE_LIFETIME_NOT_CLOSED_BY_NEXT_LOAD` even though it exposes 60 provisional
  sector-aligned windows. A new strict analyzer requires the next large load to close the window
  and requires a full 2,048-byte aligned destination, not merely the 306-byte packed payload.
- Evidence: `translation/task7_lba482_extended_route_verdict.json` and
  `tools/analyze_task7_lba482_extended_route.py`. The next run must continue past the portrait until
  the following map/overlay load before any replacement bank is selected.

- Step 74, LBA 482 bank-`$6D` unconditional sidecar PoC: **visible route PASS; architecture rejected**.
- The full-scene trace opened after LBA 482 returned and closed at the following LBA 290/count 96
  load. This proves the complete field lifetime through the portrait. Bank `$6D` was untouched for
  all 8,192 bytes during that window and is overwritten naturally by the next large load. Candidate
  selection additionally requires a full 2,048-byte sector-aligned window; the 306-byte corrected
  payload size alone is not treated as sufficient.
- A new build preserves the failed bank-`$6C` artifacts and changes only the sidecar destination and
  temporary MPR6 mapping to `$6D`. It retains LBA 9185, the `$2B0F` Work RAM hook, balanced MPR6
  save/restore, original Japanese BIOS fallback, expected-write guards and full-BIN diff audit.
- Static verification passed for the 24-byte loader, 39-byte scene wrapper, 137-byte hook, packed
  glyph expansion, bank-`$6D` map/restore sequence, one-sector sidecar and all declared changes.
  Runtime reproduced Korean text and preserved the portrait, Memo, battle return and tower progress.
  However, the CD trace proved that the wrapper is attached to a common overlay loader: it reloaded
  LBA 9185 into bank `$6D` not only after target LBA 482, but also after later LBA 290 and LBA 2882
  reads. The visible route therefore passes, but the unconditional design is not safe enough to
  approve because later overlays can silently lose their original bank-`$6D` contents.
- Evidence: `translation/task7_lba482_full_scene_trace.tsv`,
  `translation/task7_lba482_full_scene_verdict.json`,
  `translation/task7_lba482_sidecar_bank6d_poc_manifest.json`,
  `tools/build_task7_lba482_sidecar_bank6d_poc.py`, and
  `tools/verify_task7_lba482_sidecar_bank6d_poc.py`.

- Step 75, LBA 482 bank-`$6D` exact-LBA conditional sidecar PoC: **runtime FAIL**.
- The replacement wrapper checks the requested CD LBA before loading the sidecar. Only LBA 482
  performs the original read followed by LBA 9185 into bank `$6D`; every non-target request
  tail-jumps directly to the original BIOS CD_READ entry. This removes the repeated sidecar loads
  observed after LBA 290 and LBA 2882 while retaining the already validated glyph hook and payload.
- Static verification passed for the 54-byte conditional wrapper, its exact LBA discriminator and
  branch targets, the 24-byte loader, 137-byte hook, bank-`$6D` mapping, expected-write guards and
  full-BIN diff audit. Runtime confirmed the intended single `482 -> 9185` route and a normal first
  battle return, but tower entry became a black screen. The following LBA 290/count 96 load replaces
  bank `$6D`; because the Work RAM hook remains installed, its later custom path reads overwritten
  glyph data. Exact-LBA routing therefore does not satisfy the payload lifetime contract.
- Evidence: `translation/task7_lba482_sidecar_bank6d_conditional_poc_manifest.json`,
  `translation/task7_lba482_sidecar_bank6d_conditional_glyph_map.json`,
  `tools/build_task7_lba482_sidecar_bank6d_conditional_poc.py`, and
  `tools/verify_task7_lba482_sidecar_bank6d_conditional_poc.py`.

- Step 76, bank-`$6D` 16-bit 96-sector-overlay refresh PoC: **runtime FAIL**.
- The wrapper now gates on the exact sector-count word `$F9:$F8 == $0060`. Every reviewed 96-sector
  overlay first completes its original read and then refreshes LBA 9185 into bank `$6D`; all other
  CD reads tail-call the original BIOS routine without a sidecar read. This preserves the glyph
  shard across the observed LBA 482, 290 and 2882 overlay sequence without intercepting small reads.
- Static verification passed for the 54-byte count discriminator, both CD_READ paths, the 24-byte
  loader, 137-byte hook, expected-write guards, packed glyph sector and full-BIN diff audit. Runtime
  passed tower entry without battle, but battle followed by tower still produced a black screen.
  The trace recorded LBA 290/count 96 without the required following LBA 9185 refresh. The wrapper
  incorrectly treated adjacent scratch byte `$F9` as a count high byte; BIOS CD_READ exposes its
  sector count in `$F8`, so stale `$F9` state made the gate reject a valid 96-sector load.
- Evidence: `translation/task7_lba482_sidecar_bank6d_overlay96_poc_manifest.json`,
  `translation/task7_lba482_sidecar_bank6d_overlay96_glyph_map.json`,
  `translation/task7_lba482_bank6d_conditional_runtime_trace.tsv`,
  `tools/build_task7_lba482_sidecar_bank6d_overlay96_poc.py`, and
  `tools/verify_task7_lba482_sidecar_bank6d_overlay96_poc.py`.

- Step 77, bank-`$6D` 8-bit count refresh PoC: **runtime FAIL**.
- The replacement gate checks only the BIOS sector-count byte `$F8 == $60`; `$F9` is explicitly
  excluded from the discriminator. The target path retains original-read success handling and
  reloads LBA 9185 into bank `$6D`, while non-96-sector calls still tail-call the original BIOS.
- Static verification passed for the 48-byte wrapper, computed branch destination, both CD_READ
  paths, 24-byte loader, 137-byte hook, packed glyph sector, expected writes and full-BIN diff.
  Runtime still produced a black screen on the battle-then-tower route. Unlike Step 76, the trace
  now proves `290/count96 -> 9185/count1`, so routing and sidecar refresh timing are correct but not
  sufficient. The next diagnostic hashes the persistent Work RAM hook and bank-`$6D` glyph sector
  every frame to identify which owner battle mutates first; no further routing variant is approved
  until that evidence exists.
- Evidence: `translation/task7_lba482_sidecar_bank6d_count8_poc_manifest.json`,
  `translation/task7_lba482_sidecar_bank6d_count8_glyph_map.json`,
  `tools/build_task7_lba482_sidecar_bank6d_count8_poc.py`, and
  `tools/verify_task7_lba482_sidecar_bank6d_count8_poc.py`.

- Step 78, battle-to-tower state-hash diagnosis: **root cause confirmed**.
- The diagnostic trace shows the bank-`$6D` glyph sector returning to and retaining FNV `6BD7B053`
  after the LBA 290 refresh. The Work RAM hook is installed at frame 1583 with FNV `A64191DA`, then
  battle clears it at frame 3765 to the all-zero FNV `2F3FAFFF` while the glyph hash remains stable.
  The one-shot loader had permanently redirected the font call to `$2B0F`, so tower entry executes
  cleared RAM. This proves the black screen is caused by hook lifetime, not CD routing or glyph
  lifetime. The replacement must copy the 137-byte hook before every font call and must not leave
  the callsite permanently pointing at unverified Work RAM.
- Evidence: `translation/task7_lba482_bank6d_count8_statehash_trace.tsv` and
  `BizHawk-master/src/BizHawk.Emulation.Cores/Consoles/PC Engine/PCEngine.Task7Diagnostic.cs`.

- Step 79, unpinned per-call Work RAM hook self-refresh PoC: **runtime FAIL**.
- The patched font call remains permanently routed to the 14-byte loader at `$5230`. On every call,
  the loader uses TII to restore all 137 hook bytes from `$C737` to `$2B0F`, restores P/A, and jumps
  into the fresh hook. It no longer rewrites the call operand to point directly at volatile Work RAM.
  Thus battle may clear `$2B0F`, but the next text call repairs it before execution.
- Static verification passed the exact loader bytes, absence of the old `$967F/$9680` direct-call
  writes, count-8 sidecar routing, hook/MPR balance, packed glyph sector, expected-write guards and
  full-BIN diff. Memo entry nevertheless corrupts the screen. The state trace shows MPR6=`$7F` and
  the hook changing to FNV `357BA76A` with head `8366A8DD93B45229`, while the glyph sector remains
  stable. The loader copied logical `$C737` without pinning its physical source bank, so Memo's MPR6
  mapping supplied unrelated bytes instead of the hook stored in bank `$84`.
- Evidence: `translation/task7_lba482_sidecar_bank6d_selfrefresh_poc_manifest.json`,
  `translation/task7_lba482_sidecar_bank6d_selfrefresh_glyph_map.json`,
  `tools/build_task7_lba482_sidecar_bank6d_selfrefresh_poc.py`, and
  `tools/verify_task7_lba482_sidecar_bank6d_selfrefresh_poc.py`.

- Step 80, MPR6-pinned ungated per-call self-refresh PoC: **runtime FAIL**.
- The loader must save MPR6, map physical bank `$84`, copy `$C737..C7BF` to Work RAM `$2B0F`, restore
  the caller's MPR6, then enter the fresh hook. The hook's own custom-path `$6D` mapping remains
  separately balanced. Runtime must cover Memo before the battle-to-tower route.
- The implemented loader is 24 bytes and performs exactly that balanced sequence. Static verification
  passed its exact bytes, one source-bank save/map/restore pair, absence of volatile direct-call
  writes, sidecar count routing, hook MPR balance, packed glyph sector and full-BIN diff.
- Memo now passes, confirming the source-bank diagnosis, but battle enters a black screen. The loader
  still copies into `$2B0F` for every ordinary Japanese BIOS character, so battle font activity
  overwrites a Work RAM region owned by the battle engine. The next loader must test the custom code
  range before any Work RAM write and send all non-custom characters directly to BIOS `$F124`.
- Evidence: `translation/task7_lba482_sidecar_bank6d_selfrefresh_mpr6_poc_manifest.json`,
  `translation/task7_lba482_sidecar_bank6d_selfrefresh_mpr6_glyph_map.json`,
  `tools/build_task7_lba482_sidecar_bank6d_selfrefresh_mpr6_poc.py`, and
  `tools/verify_task7_lba482_sidecar_bank6d_selfrefresh_mpr6_poc.py`.

- Step 81, custom-code-gated self-refresh PoC: **runtime FAIL; cause trace in progress**.
- The loader must require `$F9 == $EF` and `$F8 in $58..$5F` before installing the hook. Custom calls
  use the MPR6-pinned bank-`$84` copy; every other call restores P/A and jumps directly to `$F124`
  without touching Work RAM. Because loader plus routing wrapper exceed the original split, both
  routines are repacked inside the reviewed `$5230..$52AF` 0x80-byte (128-byte) zero cave.
- The 44-byte loader occupies `$5230..$525B` and rejects non-custom calls before its only TII. The
  48-byte count-8 scene wrapper occupies `$525C..$528B`; both leave `$528C..$52AF` untouched.
  Static verification passed computed branch targets, balanced source-bank MPR6 mapping, the direct
  non-custom BIOS fallback, absence of live-call operand rewrites, packed-glyph expansion, Expected
  Writes and the complete BIN diff. Runtime must now cover Memo, battle Attack/field return, and
  battle followed by tower entry before this architecture can be approved.
- Runtime again enters a black screen during battle. This rejects the hypothesis that ungated
  ordinary BIOS font calls were the sole corruption source. The first attempted trace did not
  observe LBA482 because the SaveRAM begins after that load, so it contained no battle state hashes.
  The diagnostic core now has an unconditional state mode that records every custom-eligible `$5230`
  call, `$2B0F` entry, CD read, and per-frame hook/glyph hash change without an LBA prerequisite.
  The next reproduction is diagnostic-only; no replacement patch is approved until the first
  divergent state transition is captured.
- Evidence: `translation/task7_lba482_sidecar_bank6d_customgate_poc_manifest.json`,
  `tools/build_task7_lba482_sidecar_bank6d_customgate_poc.py`, and
  `tools/verify_task7_lba482_sidecar_bank6d_customgate_poc.py`.

- Step 82, custom-gated LBA482-only battle isolation PoC: **static PASS; runtime pending**.
- The unconditional state trace disproves the loader-gate hypothesis as the battle failure's direct
  cause. Only the expected eight custom calls occurred at frames 1277..1284; no custom call or
  `$2B0F` entry occurred during battle. The causal sequence instead begins with LBA290/count96 into
  bank `$68`, followed by the count wrapper's LBA9185 read into bank `$6D`. The battle then clears
  `$2B0F` normally and stalls without another custom call. Thus the sidecar refresh overwrites a live
  bank of the LBA290 battle overlay before Attack executes.
- The isolation build retains the 44-byte custom-gated loader but replaces the count-8 wrapper with
  a 54-byte exact-LBA482 wrapper. Non-LBA482 requests tail-jump to BIOS `$E009` and never touch bank
  `$6D`. Loader `$5230..$525B` and wrapper `$525C..$5291` remain inside the reviewed 0x80-byte cave.
  Static verification passed exact branch discriminators, non-target tail-call behavior, Expected
  Writes, packed glyph expansion and the complete BIN diff. Runtime must first confirm battle Attack
  and field return; post-battle Korean/tower behavior is a separate lifetime gate and is not yet
  approved.
- Evidence: `translation/task7_lba482_bank6d_customgate_battle_state_trace.tsv`,
  `translation/task7_lba482_sidecar_bank6d_customgate_lba482only_poc_manifest.json`,
  `tools/build_task7_lba482_sidecar_bank6d_customgate_lba482only_poc.py`, and
  `tools/verify_task7_lba482_sidecar_bank6d_customgate_lba482only_poc.py`.

- Step 83, compact custom-only hook: **static PASS; runtime pending**.
- The LBA482-only isolation trace confirms no LBA9185 read follows LBA290, yet battle still enters
  the black-screen loop. The remaining structural difference from the Task68 runtime PASS is Work
  RAM extent: Task68 used 127 bytes at `$2B0F..$2B8D`, while the sidecar hook grew to 137 bytes and
  reached `$2B97`. Those ten bytes were never approved by the Work RAM lifetime gate.
- Because the `$5230` loader now rejects every non-custom call, the hook no longer needs its duplicate
  F9/F8 discriminator or BIOS fallback. Removing those 20 bytes while retaining the ten-byte balanced
  MPR6 map/restore produces a 117-byte custom-only hook at `$2B0F..$2B83`. The loader remains the sole
  non-custom fallback owner. Static verification confirms the compact TII length, absence of the
  redundant hook gate, balanced MPR6 mapping, exact LBA482 wrapper, Expected Writes, glyph expansion
  and complete BIN diff.
- Evidence: `translation/task7_lba482_bank6d_customgate_lba482only_battle_trace.tsv`,
  `translation/task7_lba482_sidecar_bank6d_compacthook_poc_manifest.json`,
  `tools/build_task7_lba482_sidecar_bank6d_compacthook_poc.py`, and
  `tools/verify_task7_lba482_sidecar_bank6d_compacthook_poc.py`.

- Step 84, no-sidecar bank-`$84` compact-hook isolation: **static PASS; runtime pending**.
- Step 83 reproduced the battle Attack black screen even though the compact hook fits entirely
  inside the Task68-approved Work RAM span. The trace confirms no custom loader/hook entry during
  battle, so hook length alone is rejected. This isolation removes the LBA 9185 sidecar sector and
  every CD-read wrapper, while retaining the same custom-gated per-call loader and 117-byte hook.
  Its eight packed glyphs reside in the previously proven bank-`$84` `$C800` pool. A runtime PASS
  assigns the fault to the sidecar/storage layer; a runtime FAIL assigns it to the loader/Work RAM
  lifetime layer.
- Static verification passed the 44-byte custom gate, 117-byte compact hook, balanced bank-`$84`
  mapping, local 144-byte packed pool, Expected Writes, packed-glyph expansion, and complete BIN
  diff. Runtime must check Korean output, Memo, and battle Attack/field return in that order.

- Step 85, bank-`$84` one-shot dispatcher isolation: **static PASS; runtime pending**.
- Step 84 displayed the same second packed glyph eight times and still corrupted the battle Attack
  transition. The repeated glyph is a separate compact-hook bug: the loader restored caller A, but
  the hook incorrectly treated A as the already-normalized glyph index. The trace also proves eight
  custom calls caused eight TII copies before battle. Step 85 recomputes the index from `$F8`, keeps
  the permanent Japanese/custom gate at `$5230`, installs the Work RAM hook only on the first custom
  call, and self-patches the custom dispatch target to `$2B0F`. Post-battle hook rearming is deferred
  until this one-shot lifetime test passes battle Attack and field return.
- Static verification passed the 61-byte gate/installer, 122-byte index-corrected hook, one-shot TII
  length, self-patch target, balanced MPR6 mapping, Expected Writes, and complete BIN diff.

- Step 86, bank-`$84` one-shot no-MPR isolation: **static PASS; runtime pending**.
- Step 85 fixed all eight glyph indices but battle Attack still transitioned to the corrupt field.
  This excludes repeated TII refresh and leaves hook-side MPR6 remapping as the next single variable.
  Step 86 retains the gate, one-shot installer, self-patched custom dispatch and local `$C800` pool,
  but removes all TMA/TAM instructions from the hook and relies on the observed field MPR6=`$84`.
- Static verification passed the 61-byte one-shot dispatcher, 112-byte no-MPR hook, exact TII
  length, absence of hook-side MPR opcodes, Expected Writes, and complete BIN diff.

## 2026-07-18 — 기존 Task 7 구현 전략 폐기 및 모듈 재링크로 전환

- bank `$6D/$84`, sidecar 유무, 단발 설치, 훅 축소, MPR6 제거를 바꿔도 전투 공격 후
  잘못된 필드 전환 또는 검은 화면이 반복됐다.
- 따라서 공용 Work RAM `$2B0F` 훅과 `$5230` 전역 디스패처가 오버레이 수명 밖에
  존속하는 구조를 폐기한다. 이후에는 이 계열의 파생 PoC를 만들지 않는다.
- 루트의 파생 전체 디스크 CUE/BIN 9쌍을 삭제했고 원본 한 쌍만 보존했다.
- 새 활성 기준은 `Task_Ziria_Module_Relink.md`다. 《천외마경 ZIRIA》 번역 빌드처럼
  field, battle, menu, event, dungeon 모듈을 각각 추출·재링크하고 코드·문자열·글리프를
  해당 모듈의 소유 영역에 편입한다.
- 다음 단계 Z1은 읽기 전용 loader graph 조사다. identity rebuild가 통과하기 전에는
  새 패치 BIN/CUE를 만들지 않는다.

## 2026-07-18 — 천외마경식 재설계 Z1 완료

원본 BIN은 수정하지 않고 Track02의 로더 표와 기존 BizHawk CD_READ 추적을 다시
통합했다. 필드 엔진은 LBA 258/20이며 내부 `$6531`에 55개 장면 디렉터리,
`$66FC`에 BIOS `CD_READ($E009)` 호출을 가진다.

기준 경로는 시작 필드 LBA 482(항목 2) → 첫 전투 LBA 290(항목 0) → 필드 복귀
LBA 482 또는 탑 LBA 2882(항목 27)로 확정됐다. 세 패키지는 모두 bank `$68`부터
96섹터를 mode `$06`으로 읽어 `$68-$7F` 전체를 교체한다. 따라서 이 영역을 공용
한글 훅이나 영속 글리프 저장소로 사용하던 기존 설계는 구조적으로 유지될 수 없다.

Memo와 초상화는 해당 경로에서 별도 CD_READ를 발생시키지 않았다. 초상화는 LBA482의
bank `$6C` 데이터에 의존하지만 LBA3330을 읽는다는 증거는 없으므로, 둘 다 우선
상주 하위 렌더러로 분류했다.

`translation/ziria_module_catalog.json`, `translation/ziria_loader_graph.json`과
`Z1_모듈_로더_카탈로그.md`를 생성했으며 검증기는 원본 SHA-256, 핵심 LBA/sector,
디렉터리 항목과 전이 간선을 fail-closed 방식으로 검사한다. 다음 단계는 Z2 무수정
모듈 추출·재조립 및 원본과 동일한 identity rebuild 검증이다.

## 2026-07-18 — 천외마경식 재설계 Z2 완료

혼합 모드 CUE의 34개 트랙 경계를 계산하고 Track 02 전체를 152개의 비중첩
세그먼트로 분해했다. primary/overlay 로더 표의 논리 모듈 110개와 Z1 의미 모듈
10개도 별도 binary view로 추출했다.

조립은 152개 세그먼트만으로 Track 02를 먼저 복원하고, 원본의 raw audio 구간을
앞뒤로 그대로 스트리밍하는 방식이다. 재조립 Track 02 SHA-256은
`7566073A...2632AF9`, 전체 BIN은 `D16D29EB...B22C5`, CUE는
`C491342E...CC6B`로 각각 원본과 완전히 동일했다.

`module_relink/linker_layout.json`에는 실행 엔진과 opaque scene/resource를 구분하고,
장면 교체 구간 `$68-$7F`에 cross-family persistent section을 배치하지 못하도록
계약을 기록했다. 다음은 Z3의 original/extension/text/glyph/relocation section 분리다.

## 2026-07-18 — 천외마경식 재설계 Z3 완료

천외마경 빌드의 모듈별 WLA patch, consolidated intermediate, 2-pass link 구조를
확인하고 동일한 소유권 원칙의 fail-closed section linker를 구성했다. 각 모듈은
`original`, `extension_code`, `text`, `glyph`, `relocation` section을 가지며 Z3에서는
original만 비영이다.

12개 spec과 10개 identity-linked binary를 만들었고 모든 출력 해시가 Z2 입력과
같았다. 확장 registry는 sector allocation과 owning-loader table patch/load condition을
하나의 승인 단위로 요구한다. Work RAM, fill run, implicit gap, auto sidecar,
shared `$68-$7F` bank, 미등록 allocation, cross-family lifetime 요청 7종은 모두
의도대로 거부됐다.

현재 승인된 non-zero extension은 0개다. 다음 Z4 field 한 글자 PoC에서 최초로
field 전용 allocation과 loader registration을 동시에 등록한다.

## 2026-07-19 — 천외마경식 재설계 Z4 완료

- Z4 v1은 bank `$84`/MPR6의 `$C737`에서 한글 훅을 실행했다. `가`, 전투 복귀와 탑
  진입은 통과했지만 Memo 진입이 크래시하여, 이전 Task 5에서 확정한 MPR6 실행 금지를
  다시 확인했다.
- Z4 v2는 실행 코드를 bank `$81/$82/$83`의 반복 `00` 구간 네 곳에 분할했다. Memo,
  전투, 탑은 통과했으나 캐릭터 그래픽이 손상됐다. `$9187`의 `00`은 빈 cave가 아니라
  원본 `$8754` 32바이트 글리프 레코드 내부였다. 반복 fill은 allocation 증거가 아님을
  fail-closed 규약에 추가했다.
- Z4 v3는 원본 `$966A..$9697` 코드가 `$8754/$8755`를 `$9172`의 두 로컬 글리프로
  처리한다는 사실을 이용했다. 첫 번째 32바이트 슬롯만 Galmuri8x8 `가`로 교체하고
  시작 대사의 한 코드만 `$8754`로 바꿨다.
- 실행 코드, GETFNT callsite, BIOS, MPR, Work RAM, loader table, sector 수, audio는 모두
  변경 0이다. field 모듈 18바이트와 시작 장면 2바이트, 총 20바이트만 달라진다.
- 사용자 런타임 확인에서 `가`, 캐릭터 그래픽, Memo 진입/복귀, 첫 전투 공격과 필드
  복귀, 전투 후 탑 진입이 모두 정상으로 확인됐다. **Z4 v3 RUNTIME PASS**.
- 근거: `Z4_필드_1글자_로컬슬롯_PoC.md`,
  `translation/ziria_z4_field_oneglyph_v3_manifest.json`,
  `tools/build_ziria_z4_field_oneglyph.py`, `tools/verify_ziria_z4_field_oneglyph.py`.

## 2026-07-19 — 천외마경식 재설계 Z5 완료

- 첫 전투에서 GETFNT를 추적한 결과 364회 모두 상주 `field.main_engine`의 `$967E`,
  MPR4=`$82`를 통과했다. 초기의 “LBA 290 전용 battle renderer” 가정은 폐기했다.
- `$4036` 스트림 리더의 실제 read 지점 `$42AB/$42BA`를 추가 추적했다. 전투 원문은
  MPR6=`$84`, physical `$108ADA-$109F67`에서 읽혔고 LBA 290 bank `$68-$7F`의
  문자 read는 0회였다. LBA 290은 전투 리소스·상태 패키지이지 문자 소유자가 아니다.
- 공용 renderer의 두 원본 로컬 슬롯을 family별로 분리했다. field는 Z4의
  `$8754/$9172`, battle은 `$8755/$9192`를 사용한다.
- 공격 메시지 `%sの攻撃！`의 한 글자 `8D55`를 `8755`로 바꾸고 두 번째 32바이트
  record에 Galmuri8x8 `가`를 넣었다. Z5 증분은 실제 14바이트, Z4 포함 총 34바이트다.
- 실행 코드, GETFNT callsite, BIOS, MPR, Work RAM, loader table, sector 수, LBA 290,
  audio는 변경하지 않았다.
- 사용자 확인에서 필드 `가`, 캐릭터 그래픽, Memo, 전투 `가`, 공격 후 필드 복귀,
  전투 후 탑 진입이 모두 정상으로 확인됐다. **Z5 RUNTIME PASS**.
- 근거: `Z5_전투_1글자_공용렌더러_PoC.md`,
  `translation/ziria_z5_battle_oneglyph_v1_manifest.json`,
  `tools/build_ziria_z5_battle_oneglyph.py`.

## 2026-07-19 — 천외마경식 재설계 Z6 정밀 추적 및 정적 빌드

- 첫 대사, Memo, 첫 전투, 필드 복귀, 전투 후 탑, 초상화 이벤트를 연속 추적했다.
  1,602회의 GETFNT가 모두 `$967E`/MPR4=`$82`를 사용하여 모든 family가 하나의
  상주 renderer를 공유함을 확정했다.
- 실제 스트림 read `$4293/$42DE/$42AB/$42BA`를 마지막 mode-06 CD LBA와 결합했다.
  필드 대사는 LBA 482, 탑 대사는 LBA 2882의 `$68-$7F` 장면 창에서 읽힌다.
- 교체 대상은 필드 Memo `0x011FA17`, 탑 일반 대사 `0x05BA0EC`, 초상화 이벤트
  `0x05BA1AF`, 탑 Memo 복제본 `0x05BDA17`의 각 **화자명** 2바이트다. 대사 본문
  첫 글자는 수정하지 않았다. 모두 원본 두 토큰을
  같은 길이의 `$8754` raw 코드로 바꾸며 Z4의 `가` 글리프를 재사용한다.
- Z6 증분은 정확히 8바이트, Z4+Z5+Z6 전체 Track02 변경은 42바이트다. 독립 diff
  검사에서 선언한 8개 바이트 오프셋 외 변경은 없었다.
- 코드, 글리프 레코드, battle module, BIOS, MPR, Work RAM, loader table, audio,
  CUE track layout 변경은 0이다. **STATIC PASS / RUNTIME PASS**.
- 사용자 확인에서 네 화자명 표본과 전환 경로가 정상 출력됐다. **Z6 RUNTIME PASS**.
  첫 필드 대사 본문의 `가`도 PASS로 재확인됐다. 다만 Memo 본문 첫 글자와 탑 진입
  직후 대사 본문 첫 글자는 확인하지 않아 `NOT_CHECKED`로 남겼다.
- 근거: `Z6_전환_family_통합_게이트.md`,
  `translation/ziria_z6_family_integration_v1_manifest.json`,
  `tools/build_ziria_z6_family_integration.py`.
## 2026-07-24 — Z6.1 Memo·탑 실제 본문 consumer 게이트

- Z6에서 검증한 네 위치는 실제 대사 본문이 아니라 화자명이었다.
- 첫 필드 Memo는 `0x011FA1F`의 `95 95`, 탑 진입 초상화 대사는
  `0x05BA1B7`의 `81 45`가 각각 `#1` 뒤 첫 실제 본문 구간임을 원본 추출
  레코드와 Z5/Z6 Track02 바이트로 교차 확인했다.
- 두 구간만 기존 공용 raw 코드 `87 54`로 고정 길이 교체했다.
- Z6 대비 변경은 4바이트이고 identity 대비 누적 변경은 46바이트다.
- 실행 코드, 글리프 레코드, 화자명, 포인터, 제어코드, 종료자, 전투 모듈,
  BIOS, MPR, Work RAM, loader 및 CUE 구조는 변경하지 않았다.
- 출력 BIN SHA-256은
  `5EAE6EF658CF8B41188478E29A30B37F85AC8D28AB81EFAC85F3FC5F48C57FB5`다.
- 정적 검증은 PASS이며 Memo 본문과 탑 진입 대사 본문의 런타임 확인을 기다린다.

### Z6.1 v1 런타임 판정과 v2 교정

- 첫 필드 Memo 본문 `가`, Memo 복귀, 첫 전투, 필드 복귀, 전투 후 탑 진입,
  캐릭터·초상화 그래픽은 모두 PASS였다.
- 탑 진입 후 첫 대사에서는 화자명만 `가`로 시작하고 본문은 원문으로 출력됐다.
- v1에서 선택한 `0x05BA1B7`은 실제 첫 탑 대사가 아니라 뒤쪽 초상화 이벤트
  `0x05BA1AD`의 본문임이 확인됐다.
- 화면에 출력된 원문과 `master_text.csv`를 대조해 실행된 레코드를
  `iso:05BA0EA`로 식별했다. 이 레코드의 `#1`은 `0x05BA0F3`, 실제 본문은
  `0x05BA0F5`에서 시작한다.
- v2는 Z6 기준선에서 다시 빌드해 v1 오표본을 제거하고, Memo 본문
  `0x011FA1F`와 실제 탑 본문 `0x05BA0F5`만 `87 54`로 교체했다.
- v2의 Z6 대비 변경은 4바이트이고 누적 변경은 46바이트다.
- v2 BIN SHA-256:
  `5F76640EC67713BFBF42F42D9B3C4E468DB537D5A3923FD27C87F6BF861C7C46`.
- 사용자 런타임 확인에서 탑 진입 후 첫 대사의 화자명과 실제 본문 첫 글자가 모두
  `가`로 출력됐고, 후속 본문도 정상 출력됐다.
- 앞서 확인한 Memo 본문·복귀, 전투·필드 복귀, 전투 후 탑 진입 및 그래픽 상태까지
  회귀가 없으므로 **Z6.1 v2 RUNTIME PASS**로 확정한다.





## Z7 모듈별 폰트·글리프 패키지

- `master_text.csv`의 18,817행을 storage module과 renderer family의 두 축으로
  분리했다. 정적 CSV만으로 field/tower 런타임 소유권을 과장하지 않도록
  `slotNN` 기반 storage와 category 기반 consumer family를 독립적으로 유지한다.
- `font/Galmuri8x8.ttf` SHA-256
  `97BA3DCC2CD5E5B2927E4E6BA9558A48A2A194A852C420DF160654D66BBF2A05`를
  강제 검증하고, 전체 고유 한글 1,053자를 12×12 셀의 32-byte expanded 및
  BIOS mode-1 호환 18-byte packed 형식으로 생성했다.
- 99개 모듈/family 패키지에 package-local EB..EF 코드 맵, width/advance=12,
  미매핑 한글 build error, 비한글 `EX_GETFNT` fallback 정책을 기록했다.
- 최대 패키지는 563자, packed package 추정 13,576바이트이며 940-code 한도를
  넘는 패키지는 없다. 공통 글리프도 전역 상주시키지 않고 필요한 패키지에
  복제한다.
- 독립 검증은 99개 패키지의 해시, 코드 범위/유일성, 맵 순번, 18→32바이트
  round-trip, 크기, CUE/BIN 비변경을 확인했다.
- 동일 입력으로 두 번 생성한 manifest 해시는
  `2318290A79E0B68F9F4199AED89E88F090A721EC5C6CBCCFD54D358B6297367C`로
  동일하다.
- 산출물은 `Z7_모듈별_글리프_패키지.md`,
  `translation/ziria_z7_glyph_packages_manifest.json`,
  `translation/ziria_z7_module_glyph_packages.csv`,
  `translation/ziria_z7_glyph_membership.csv`,
  `module_relink/z7_glyph_packages/packages/`에 있다.
- `needs_review` 17행은 용량 집계에는 포함됐지만 릴리스 입력으로 승인되지
  않았다. 다음 단계 Z8에서 loader-owned extension과 텍스트 컨테이너를
  결합한다.

## 2026-07-26 — Z8 v1 텍스트 컨테이너 구조화

- `master_text.csv`의 물리 레코드 18,817개를 Z7의 storage module과 renderer
  family 기준으로 103개 분석 컨테이너에 배치했다.
- 원본 Track02와 raw 바이트 일치, `00` 종료, 원문/번역 제어 토큰
  (`0B`, `0C`, `0D`, `0E`, `#x`, `%x`, `7E`) 순서를 전수 검증했다.
- 각 문자열은 8 KiB 경계를 넘지 않으며, 동일 패키지 안에서 최종 인코딩
  바이트가 완전히 같은 경우만 중복 제거한다.
- category/subcategory 조합 25개를 별도 의미 테이블로 생성했다. 따라서
  이름·메뉴·전투 command·아이템·시스템 자료를 한 테이블로 섞지 않는다.
- 번역에 사용된 `U+00B7` 중점 12행/24회는 `master_text.csv`를 바꾸지 않고
  게임 기본 중점 코드 `A5`로 인코딩했다. 매니페스트와 각 엔트리에 사용
  횟수를 기록했다.
- 독립 검증 결과 18,817행, 103개 컨테이너, 25개 의미 테이블이 모두 PASS했다.
  동일 입력 재빌드 전후 매니페스트 SHA-256은
  `38AF4D5E8C9ABFE8F61A46FA8949092D2E0C9E597DD61C01B2983FA63323FF03`로
  일치했다.
- 이번 단계는 CUE/BIN을 생성하거나 수정하지 않았다. 출력은 runtime
  pointer/index가 아닌 분석 컨테이너이며, 상태는
  `STRUCTURE_PASS_RELOCATION_BLOCKED`다.
- 다음 게이트는 renderer family 하나를 고른 뒤 모든 참조 분모와
  loader-owned redirect/index 바이트 형식을 증명하는 것이다. 폐기된 상주
  훅의 `01/02` redirect/continuation 규약은 사용하지 않는다.

## 2026-07-26 — Z8.2 field dialogue 참조 분모

- 첫 적용 범위를 `scene.field_start`의 field dialogue로 제한했다.
- overlay directory 55개를 전수 검사해 logical entry 2, Track02
  `0x83539`, raw `0001E260`이 LBA 482×96 sectors를 적재하는 유일한
  로더 참조임을 확인했다. 적재 대상은 physical bank `$68-$7F` 전체다.
- scene extent `0x0F1000..0x121000`에 포함된 dialogue 레코드는 236개다.
  각 레코드의 원본 위치, scene-relative offset, physical bank, bank offset,
  24-bit source key, Z8 컨테이너 연결을 카탈로그로 만들었다.
- source key는 logical pointer의 page를 현재 MPR로 역변환해 계산한다.
  이 방식은 scene이 resident인 동안 page remap과 독립적이며 236개 전부
  왕복 검증을 통과했다.
- Z6 장기 trace와 대조한 결과 실제 stream 소비가 확인된 레코드는 9개,
  전체 raw가 관측된 레코드는 8개다. 227개는 runtime 미관측 상태다.
- 16-bit logical literal 검색은 우연 일치를 구분할 수 없어 reference
  증거로 사용하지 않았다. loader 참조만 PASS이며 text reference 분모는
  아직 OPEN이다.
- 상태:
  `LOADER_REFERENCE_PASS_TEXT_REFERENCE_DENOMINATOR_OPEN`.
  redirect/index 및 CUE/BIN/ISO 변경은 수행하지 않았다.
- 독립 검증과 재생성 결정성 검증을 통과했다. 매니페스트 SHA-256은
  `18E994C1D2DD7FCE38294C201AC32E150B839BF7830A84DA5998DEC360DEA506`다.
- 다음 단계는 stream reader `$4293/$42DE/$42AB/$42BA`에서 source key를
  계산하는 read-only probe를 만들고, 관측된 9개 시작점과 카탈로그의
  일치를 확인하는 것이다.

## 2026-07-26 — Z8.3 field source-key read-only probe

- `translation/ziria_z8_field_source_key_lookup.tsv`에 field dialogue source
  key 236개를 고정했다.
- `tools/trace_ziria_z8_field_source_keys.lua`는 stream reader 네 곳과
  mode-06 CD read만 관측하며 host 로그 외에는 쓰지 않는다.
- BIOS 화면에서 Lua를 열면 진행이 멈추는 기존 제약 때문에 첫 필드가
  보인 뒤 수동으로 probe를 여는 계약을 명시했다. 시작 시 field scene을
  가정하되 다음 mode-06 CD read부터 실제 LBA/count로 identity를 갱신한다.
- 기존 Z6 trace의 field stream read 828회를 오프라인 재생한 결과 key/
  overlay/ISO 좌표 불일치는 0건이었다.
- 정확한 레코드 시작 hit는 8개, 내부 접근까지 포함한 레코드는 9개다.
- Lua의 memory/controller/register/savestate/disc write 가능 API는 정적
  검사에서 0건이다.
- 독립 검증 및 결정성 검증 PASS. 매니페스트 SHA-256:
  `42A0A0C84E6EE5C8CDEFF3BDFF5F1448D4A953C56C8FF23BA519B8AC18E64EB6`.
- 현재 상태는 `OFFLINE_REPLAY_PASS_RUNTIME_CAPTURE_PENDING`이다. 새 runtime
  로그가 생성되기 전에는 redirect/index 및 패치 쓰기를 진행하지 않는다.

## 2026-07-26 — Z8.4 field source-key runtime gate

- 첫 대사 → Memo 진입·복귀 → 첫 전투·필드 복귀 → 탑 진입 경로에서
  `translation/ziria_z8_field_source_key_runtime_trace.tsv` 852행을 수집했다.
- field scene stream은 783회이며 `START_HIT`는 9회, 고유 catalogue ID는
  8개다. 이 8개는 Z8.3 오프라인 재생의 정확 시작 ID 집합과 일치한다.
- 모든 hit의 source key를
  `(MPR[logical>>13]-$68)*$2000 + (logical&$1FFF)`로 다시 계산했다.
  수식, lookup ID, ISO 위치, 관측 scene identity 불일치는 모두 0건이다.
- mode-06 scene identity는 LBA 482에서 290, 2882로 전환됐다. 이 전환 뒤에도
  사용자가 지정 경로를 완료했으며 probe로 인한 emulator failure는 없었다.
- `tools/analyze_ziria_z8_field_source_key_runtime.py`와
  `tools/verify_ziria_z8_field_source_key_runtime.py`를 추가했고 독립 검증 및
  Python 구문 검사를 통과했다.
- 결과물은 `Z8_4_field_source_key_runtime_result.md`와
  `translation/ziria_z8_field_source_key_runtime_manifest.json`이다.
  매니페스트 SHA-256은
  `F7ABA6B1DAD050175BC14D7BE92D3081D5F72F1C5F5028A58256A5B89421FDC9`다.
- 판정은 `RUNTIME_SOURCE_KEY_PASS_DENOMINATOR_OPEN`이다. 관측된 소비자에
  대한 key 산식은 확정했지만 236개 전체의 정적 event-bytecode 참조 분모는
  아직 열려 있다. 따라서 redirect/index와 CUE/BIN/ISO는 만들지 않았다.

## 2026-07-26 — Z8.5 field event-bytecode 정적 분모

- 기존 236행을 원본 scene package의 명령/포인터 구조로 다시 분류했다.
- 실제 text consumer는 235개다: opcode `02` 인라인 217개, opcode `03`
  인라인 10개, opcode `14` 인라인 1개, Memo 포인터 테이블 7개다.
- `iso:010F080`은 `3F..57` 순차 가나 lookup table의 일부로, 대사가 아니므로
  false positive로 제외했다.
- `iso:010CAE1`, `iso:010D080`은 opcode `02` payload의 앞부분을 master가
  누락했고, `iso:011F011`은 첫 Memo 문자열 앞의 포인터 13바이트를 잘못
  포함했다.
- 안전한 원본 경계를 가진 행은 232개다. 실제 참조 분모는 모두 열거했지만
  위 3개 경계를 고치기 전에는 redirect/index를 만들지 않는다.
- 분석기와 독립 검증기는 각각
  `tools/analyze_ziria_z8_field_event_bytecode.py`,
  `tools/verify_ziria_z8_field_event_bytecode.py`이며 검증 결과는
  `Z8.5 FIELD EVENT BYTECODE: PASS (235 consumers, 232 exact, 3 repairs, 1 excluded)`다.
- 결과 manifest SHA-256은
  `ABA6DB87C1B9DD7AFA70B83B7B289D13D6126A91CBAB5E01BC4D0A092A28ED25`다.
- 이 단계에서는 CUE/BIN/ISO를 수정하지 않았다.

## 2026-07-26 — Z8.6 field 경계 보정과 정규 source-key index

- opcode와 Memo 포인터로 확정한 실제 시작점을 기준으로 경계 오류 3건을
  보정했다.
- `iso:010CAE1`은 `iso:010CABD`로 이동해 길을 막는 NPC 통과 안내 전체
  원문을 복원했다.
- `iso:010D080`은 `iso:010D036`으로 이동해 오토 배틀 안내 2페이지 전체와
  `\p` 제어를 복원했다.
- `iso:011F011`은 포인터 테이블 13바이트를 제거하고 실제 첫 Memo 문자열
  `iso:011F01E` / `次の目的のこと` / `다음 목적지에 대해`로 고쳤다.
- `iso:010F080`은 순차 가나 lookup table이므로 정규 field 대사 인덱스에서
  제외했다.
- 기존 매니페스트의 기준 해시를 깨지 않도록 `master_text.csv`는 수정하지
  않았다. 변경은 `ziria_z8_field_boundary_repairs.csv` overlay에 기록했다.
- 최종 `ziria_z8_field_source_key_index.tsv`는 실제 consumer 235행이며,
  corrected ID 235개와 24-bit little-endian source key 235개가 모두
  유일하다. 232행은 기존 경계 그대로이고 3행은 보정 경계다.
- 모든 raw record의 NUL 경계와 원본 ISO 바이트 일치를 독립 검증했고,
  빌더 재실행 결과가 동일한 결정성 검증도 통과했다.
- 판정은 `BOUNDARY_REPAIR_PASS_SOURCE_INDEX_CLOSED`다. 매니페스트 SHA-256은
  `24E0C26AE6FB13AB2C9EFCBA39BF72BB3FED94E79980C599FE49C5B9570CC47C`다.
- CUE/BIN/ISO는 수정하지 않았다. 다음 단계는 renderer family 하나를
  선택하고 235개 전 소비자를 다루는 loader-owned redirect/index 바이트
  형식을 증명하는 것이다.

## 2026-07-26 — Z8.7 field redirect wire format

- Z8.6 정규 인덱스의 corrected consumer 235개를 source key 오름차순으로
  직렬화했다.
- 32바이트 헤더와 12바이트 고정 레코드를 채택했다. 각 레코드는 24-bit
  source key, 24-bit text target, 원문/번역 길이, consumer kind,
  continuation flags를 가진다.
- inline opcode `02/03/14`는 번역 NUL 뒤
  `source_key + original_length`에서 원문 event stream을 재개하고,
  Memo pointer 7개는 native pointer-string return을 사용하도록 분리했다.
- lookup miss는 원문을 그대로 사용한다. 원문 byte stream에는 redirect
  marker를 기록하지 않는다.
- 235개 번역에 필요한 한글은 520개다. Galmuri8x8 기반 단일 field-local
  EB..EF 코드표와 9,360바이트 packed18 glyph pool을 생성했다.
- 인덱스는 2,852바이트, 문자열 blob은 14,640바이트다. 동일 문자열은 최종
  encoded byte identity로만 중복 제거했으며 8 KiB 경계 교차는 0건이다.
- 독립 검증은 235개 source denominator, 원본 ISO raw, 제어 토큰, NUL,
  continuation, kind/flags, glyph code 유일성, 출력 해시를 재검사했다.
- 동일 입력 재생성 결과 index/text/glyph/manifest 해시가 모두 동일했다.
  매니페스트 SHA-256은
  `85E8356E9934B37C17D43E29D77FC75B3FB0A5E38633C868CEA09E26A3D64C57`다.
- 원본 Track02 ISO SHA-256은 계속
  `7566073A2AA1F48E7B39ED2B34277D9935FADE8A3FAD7DCC72C21276E2632AF9`다.
- 판정은 `WIRE_FORMAT_PASS_LOADER_ALLOCATION_AND_ABI_OPEN`이다.
  loader-owned LBA/sector 배치, field renderer hook/cursor ABI, packed18
  적재 목적지, relocation은 아직 증명하지 않았으므로 CUE/BIN/ISO 생성과
  수정은 계속 차단한다.

## 2026-07-26 — Z8.8 loader allocation / reader ABI

`tools/build_ziria_z8_8_loader_allocation_abi.py`와 독립 검증기를 실행했다.

- `$4036` 공용 reader ABI 및 네 cursor 경로: PASS
- `$54/$55` 종료 후 기본 stream continuation: PASS
- `$68-$87` resident bank 소유권: 빈 persistent bank 없음
- 235개 원문 회수 총량: 14,816 bytes
- 최대 연속 회수 구간: 344 bytes
- Z8.7 index/text/glyph 총량: 26,852 bytes
- Z8.7 unchanged-wire allocation: FAIL

따라서 ABI 문제는 닫혔지만 저장 공간 문제는 닫히지 않았다. 기존 wire format을
억지로 삽입하면 이전과 같은 scene/battle/tower 자산 훼손이 재발하므로 디스크는
수정하지 않았다. 다음 단계는 Z8.9 저장 표현 재설계다.
