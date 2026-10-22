"""B트랙 B65 — b64 + **카드 미니게임 모듈 초기화 경합 수정**(2026-10-22 제보: 펨브로크 카지노 진입 검은 화면).

증상: 펨브로크 항구 카지노에서 도박사 소녀에게 「네」→「좋아、 간다！」 직후 검은 화면(타이밍에 따라 가끔 정상). 원본 디스크는 정상.
원인(RetroArch Beetle PCE 스테이트 1프레임 단위 비교·RAM 되돌리기 이분 탐색으로 확정):
  엔진은 모듈 적재를 워크 RAM $2300 루틴(SEI → JSR $E009 → JMP $4000)으로 한다. 카드 모듈(ISO 0xBD5000) 초기화는
  $5029 `STZ $F3`($F3 = 모듈의 VDC CR 섀도)로 $F3=0 을 만든 뒤 $8FD9 에서 `CLI` 한다. 모듈의 VBlank 핸들러($5093, $50C8)는
  CR 하위 바이트를 `$F3 & $26ED` 로 쓴다. SEI 구간(모듈 CD 읽기) 중 VBlank IRQ 가 걸려 있다가 CLI 직후 핸들러가 먼저 돌면
  CR=$00 → VBlank IRQ 자체가 꺼져 이후 vsync 대기($52EB, zp $38)가 영원히 끝나지 않는다. 원본의 잠재 경합이며, 한글판은
  디스패처 훅(TRAMP $66DF) 탓에 대화 종료→적재 타이밍이 몇 라인 어긋나 이 창에 걸린다(벡터 $4036 만 원본으로 되돌리면 정상 = 실측).
  정상 경로에서는 초기화 중 $F3 에 $08 이 들어간 뒤 첫 VBlank 가 와서 CR=$0800(화면 꺼짐·IRQ 켜짐)이 된다.
수정(모듈 제자리 2곳, 카드·엔진 무변경):
  · $5032 `JMP $8FD9` → `JMP $4FF0`
  · $4FF0(모듈 머리 FF 패딩 끝 16B, 참조 없음): `LDA #$08 / STA $F3 / JMP $8FD9` — CLI 전에 $F3 에 VBlank IRQ 비트를 넣어
    핸들러가 일찍 돌아도 CR=$0800 이 되게 한다(정상 경로의 첫 VBlank 결과와 동일).
  같은 모듈을 쓰는 씬 770(에스트 도박사)도 함께 보호된다. 다른 모듈(0xC05000 등)은 초기화 코드가 달라 손대지 않았다.
나머지 구성(텍스트·카드·엔진 훅·패치)은 b64 와 동일. 출력: *_btrack_b65.bin/.cue + probes/SystemCard3_btrack_b65.pce (카드 = b64 와 동일)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btrack_b64_hook_build as b64          # b64 구성(패치 JSON 생성·체인 설정)을 그대로 상속
from build_btrack_b64_hook_build import m, b37, b38, cr, T2, ORIG_ISO, MODE_P, n_rev

MODULE = 0xBD5000                       # 카드 미니게임 모듈 ISO 오프셋 (모듈 $4000 = 이 오프셋)
INIT_JMP = MODULE + 0x1032              # $5032: JMP $8FD9
STUB = MODULE + 0x0FF0                  # $4FF0: FF 패딩 16B
STUB_CODE = bytes((0xA9, 0x08, 0x85, 0xF3, 0x4C, 0xD9, 0x8F))   # LDA #$08 / STA $F3 / JMP $8FD9

m.OUT_BIN = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b65.bin"
m.OUT_CUE = ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP_btrack_b65.cue"
m.OUT_CARD = ROOT / "probes" / "SystemCard3_btrack_b65.pce"
m.OUT_LAYOUT = ROOT / "translation" / "btrack_b65_card_layout.json"
b37.OUT_BIN, b37.OUT_CUE, b37.OUT_CARD = m.OUT_BIN, m.OUT_CUE, m.OUT_CARD
b37.OUT_INFO = ROOT / "translation" / "btrack_b65_font_compact.json"
b38.OUT_SIG = ROOT / "translation" / "btrack_b65_rearm_signatures.json"


def patch_module(out: bytearray) -> None:
    j = T2 + INIT_JMP
    assert out[j:j + 3] == bytes((0x4C, 0xD9, 0x8F)), f"모듈 $5032 원본 불일치 {out[j:j+3].hex()}"
    s = T2 + STUB
    assert set(out[s:s + 16]) == {0xFF}, "모듈 $4FF0 패딩 비어 있지 않음"
    assert ORIG_ISO[STUB:STUB + 16] == b"\xFF" * 16 and ORIG_ISO[INIT_JMP:INIT_JMP + 3] == bytes((0x4C, 0xD9, 0x8F))
    out[j + 1:j + 3] = bytes((0xF0, 0x4F))
    out[s:s + len(STUB_CODE)] = STUB_CODE


if __name__ == "__main__":
    print(f"[b65] 크레딧 되돌린 바이트 {n_rev}, 크레딧 코드 {len(b37.CREDIT_CODES)}", flush=True)
    m.main()
    out = bytearray(m.OUT_BIN.read_bytes())
    patch_module(out)
    m.OUT_BIN.write_bytes(bytes(out))
    iso = bytes(out[T2:])
    flips = {p["iso_off"] for p in MODE_P}
    for lo, hi in cr.REVERT:
        bad = [i for i in range(lo, hi) if iso[i] != ORIG_ISO[i] and i not in flips]
        assert not bad, f"크레딧 구역 {lo:#x} 원본과 다름 {bad[:5]}"
    assert all(iso[i] == 0 for i in flips), "모드 바이트 미적용"
    print(json.dumps({"status": "B65_OK", "module_init_stub": hex(STUB), "credit_regions_original": len(cr.REGIONS)}))
