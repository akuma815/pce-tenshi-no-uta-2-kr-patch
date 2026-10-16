"""B트랙 B61 — b60 + 대사 4건 (2026-10-13 사용자 제보: 무기·도구점 「물욕가」 어색, 「정말이야、 리아」 의문형).
  ものずき = 「괴짜」(よかったら世話するぜ = 필요하면 내가 챙겨 주지) / 本当なのか、リア・いいのか、リア(사본 74)・情が移ったのか、リアーナ → 「？」.
  제자리 패치 = b59 와 같음(btrack_b59_full_menu_patches_src.json → 크레딧·오탐 되돌림). 나머지 구성은 b59 와 같음."""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b46_hook_build as m
import build_btrack_b38_hook_build as b38
import build_btrack_b37_hook_build as b37
import build_btrack_b28_hook_build as b28
import build_btrack_b9_hook_build as b9
import credits_original as cr
from build_btrack_b7_hook_build import T2
b9.EXT_SECTORS = 0   # 트랙 확장 없음(오디오 트랙 절대 위치 = 원본, b57)

SRC_PATCHES = ROOT / "translation" / "btrack_b59_full_menu_patches_src.json"
PATCHES = ROOT / "translation" / "btrack_b61_full_menu_patches.json"
ORIG_ISO = (ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin").read_bytes()[T2:]

d = json.loads(SRC_PATCHES.read_text(encoding="utf-8"))
d["patches"], n_rev = cr.revert_patches(d["patches"], ORIG_ISO)
MODE_P = cr.mode_patches(ORIG_ISO)   # 作画監督 → 16x16 모드(督 이 12x12 에선 한글 「뇨」와 겹침)
d["patches"] += MODE_P
PATCHES.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
b28.PATCHES = PATCHES
b37.CREDIT_CODES = cr.credit_codes(ORIG_ISO)

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b61.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b61.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b61.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b61_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b61_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b61_rearm_signatures.json"

if __name__ == "__main__":
    print(f"[b61] 크레딧 구역 되돌린 바이트 {n_rev}, 크레딧 코드 {len(b37.CREDIT_CODES)}", flush=True)
    m.main()
    iso = m.OUT_BIN.read_bytes()[T2:]
    flips = {p["iso_off"] for p in MODE_P}
    for lo, hi in cr.REVERT:
        bad = [i for i in range(lo, hi) if iso[i] != ORIG_ISO[i] and i not in flips]
        assert not bad, f"크레딧 구역 {lo:#x} 원본과 다름 {bad[:5]}"
    assert all(iso[i] == 0 for i in flips), "모드 바이트 미적용"
    print(json.dumps({"status": "B61_OK", "credit_regions_original": len(cr.REGIONS)}))
