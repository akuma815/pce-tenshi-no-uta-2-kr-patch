# -*- coding: utf-8 -*-
"""카드 미니게임 UI 그래픽 한글화 — BG 타일 제자리 교체 (2026-10-10)

근거: PCEHawk 세이브 스테이트(원본 디스크)의 VRAM/BAT 덤프(translation/cardgame/vram/s{2..7}_*)에서
화면 셀(64x32 BAT) → VRAM 타일 → ISO 섹터 6000~6300 의 동일 32B 타일로 100% 대응됨(동적 말풍선 제외).
따라서 디스크의 해당 타일 32B 를 한글 렌더로 바꾸면 BAT 는 그대로 쓰인다.

두 가지 교체:
  ① 사각형 요소(rect): 화면 셀 영역에 한글 문자열을 렌더(16px 줄 = 2셀 높이, 8px 줄 = 1셀), 셀별 ISO 타일에 기록.
  ② 글리프 교체(glyph): 한 화면에서 기준 셀(2x2)의 16x16 한자 이미지를 뽑아 ISO 전 범위에서 같은 '잉크 마스크'
     (색 인덱스 무관)를 가진 2x2 타일 그룹을 찾아 모두 한글 한 글자로 교체(点→점 등, 밝기 변형까지 포함).
출력: translation/btrack_b29_cardgame_tiles.json (iso_off/old_hex/new_hex 목록) + 미리보기 PNG.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import Counter, defaultdict
from PIL import Image, ImageFont, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")); sys.argv = ["x"]
from build_btrack_b7_hook_build import T2  # noqa: E402

VRAM_DIR = ROOT / "translation" / "cardgame" / "vram"
OUT_JSON = ROOT / "translation" / "btrack_b29_cardgame_tiles.json"
PREVIEW_DIR = ROOT / "translation" / "cardgame" / "preview"
FONT16 = r"G:\Downloads\Korean Traslate Project\Font\Galmuri14.ttf"
FONT8 = r"G:\Downloads\Korean Traslate Project\Font\Galmuri7.ttf"
ISO_LO, ISO_HI = 6000 * 2048, 6300 * 2048
TILE_BASE = 0xBE3000  # VRAM 타일 0 에 대응하는 ISO 오프셋 (선형)
W, H = 64, 32

disc = open(ROOT / "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.bin", "rb").read()
iso = disc[T2:T2 + ISO_HI]
iso_index = {}
for off in range(ISO_LO, ISO_HI, 32):
    iso_index.setdefault(iso[off:off + 32], off)


def tile_decode(b):
    px = [[0] * 8 for _ in range(8)]
    for r in range(8):
        b0, b1, b2, b3 = b[r * 2], b[r * 2 + 1], b[16 + r * 2], b[16 + r * 2 + 1]
        for x in range(8):
            px[r][x] = ((b0 >> (7 - x)) & 1) | (((b1 >> (7 - x)) & 1) << 1) | (((b2 >> (7 - x)) & 1) << 2) | (((b3 >> (7 - x)) & 1) << 3)
    return px


def tile_encode(px):
    out = bytearray(32)
    for r in range(8):
        b0 = b1 = b2 = b3 = 0
        for x in range(8):
            v = px[r][x] & 0xF; bit = 7 - x
            b0 |= ((v >> 0) & 1) << bit; b1 |= ((v >> 1) & 1) << bit; b2 |= ((v >> 2) & 1) << bit; b3 |= ((v >> 3) & 1) << bit
        out[r * 2] = b0; out[r * 2 + 1] = b1; out[16 + r * 2] = b2; out[16 + r * 2 + 1] = b3
    return bytes(out)


class Screen:
    def __init__(self, slot):
        self.slot = slot
        self.vram = open(VRAM_DIR / f"s{slot}_VRAM1.bin", "rb").read()
        self.cells = {}
        for y in range(H):
            for x in range(W):
                w = self.vram[(y * W + x) * 2] | (self.vram[(y * W + x) * 2 + 1] << 8)
                ti = w & 0xFFF
                tb = self.vram[ti * 32:ti * 32 + 32]
                # 타일 시트는 ISO 0xBE3000 + ti*32 에 선형 적재(중복 타일 존재) → 내용 검색이 아니라 선형 주소를 쓴다
                lin = TILE_BASE + ti * 32
                off = lin if (ISO_LO <= lin < ISO_HI and iso[lin:lin + 32] == tb) else iso_index.get(tb)
                self.cells[(x, y)] = (ti, tb, off)
        self.uses = defaultdict(list)
        for (x, y), (ti, tb, off) in self.cells.items():
            if off is not None:
                self.uses[off].append((x, y))

    def rect_pixels(self, x0, y0, w, h):
        img = [[0] * (w * 8) for _ in range(h * 8)]
        for cy in range(h):
            for cx in range(w):
                px = tile_decode(self.cells[(x0 + cx, y0 + cy)][1])
                for yy in range(8):
                    for xx in range(8):
                        img[cy * 8 + yy][cx * 8 + xx] = px[yy][xx]
        return img


def ink_stats(img):
    cnt = Counter(v for row in img for v in row if v)
    return cnt


def render_text(text, width_px, height_px, size, fill, outline=None, pitch=None, align="left", x_pad=0, bold=False):
    """1bpp 렌더 → 색 인덱스 이미지(list of rows). pitch=None 이면 폰트 폭 그대로."""
    font = ImageFont.truetype(FONT16 if size >= 12 else FONT8, size)
    im = Image.new("L", (width_px, height_px), 0); dr = ImageDraw.Draw(im)
    # 글자별 배치 (pitch 지정 시 고정 피치)
    chars = list(text)
    widths = []
    for ch in chars:
        bb = font.getbbox(ch) if ch != " " else (0, 0, max(4, size // 2), 1)
        widths.append((pitch if (pitch and ch != " ") else (bb[2] - bb[0] + (1 if ch != " " else 0)), bb))
    total = sum(w for w, _ in widths)
    x = x_pad if align == "left" else max(0, (width_px - total) // 2)
    asc = font.getbbox("한")[3]
    y = (height_px - asc) // 2 - font.getbbox("한")[1] if size >= 12 else (height_px - (font.getbbox("한")[3] - font.getbbox("한")[1])) // 2 - font.getbbox("한")[1]
    for ch, (wd, bb) in zip(chars, widths):
        if ch != " ":
            dr.text((x - bb[0], y), ch, font=font, fill=255)
            if bold:
                dr.text((x - bb[0] + 1, y), ch, font=font, fill=255)
        x += wd
    px = im.load()
    out = [[0] * width_px for _ in range(height_px)]
    for yy in range(height_px):
        for xx in range(width_px):
            if px[xx, yy] > 128:
                out[yy][xx] = fill
    if outline is not None:
        src = [row[:] for row in out]
        for yy in range(height_px):
            for xx in range(width_px):
                if src[yy][xx] == 0:
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = yy + dy, xx + dx
                            if 0 <= ny < height_px and 0 <= nx < width_px and src[ny][nx] == fill:
                                out[yy][xx] = outline
    return out, total


class Patcher:
    def __init__(self, screens):
        self.patches = {}   # iso_off -> new32
        self.conflicts = []
        self.screens = screens
        self.rects = {s: set() for s in screens}     # 요소 셀 집합 (1차 등록)
        self.uses = defaultdict(list)                # iso_off -> [(slot,x,y)]
        for s, scr in screens.items():
            for (x, y), (ti, tb, off) in scr.cells.items():
                if off is not None: self.uses[off].append((s, x, y))

    def register(self, slot, x0, y0, w, h):
        for cy in range(h):
            for cx in range(w): self.rects[slot].add((x0 + cx, y0 + cy))

    def protected(self, off):
        """요소 사각형 밖에서도 쓰이는 타일 중, 원본이 잉크 없는(균일) 타일만 보호. 글리프 조각 타일은 전역 교체 허용
        (같은 한자 타일은 어디서든 같은 한글로 바뀌어야 하므로)."""
        outside = [(s, x, y) for s, x, y in self.uses[off] if (x, y) not in self.rects[s]]
        if not outside: return False
        tb = iso[off:off + 32]; px = tile_decode(tb)
        vals = {v for row in px for v in row}
        return len(vals) <= 1

    def put(self, off, new, tag):
        old = self.patches.get(off)
        if old is not None and old != new:
            self.conflicts.append(("diff", hex(off), tag)); return
        self.patches[off] = new

    def write_rect(self, scr, x0, y0, w, h, img, tag):
        for cy in range(h):
            for cx in range(w):
                ti, tb, off = scr.cells[(x0 + cx, y0 + cy)]
                px = [[img[cy * 8 + yy][cx * 8 + xx] for xx in range(8)] for yy in range(8)]
                new = tile_encode(px)
                if new == tb: continue                      # 변경 없음
                if off is None:
                    self.conflicts.append(("dyn", (x0 + cx, y0 + cy), tag)); continue
                if self.protected(off):
                    self.conflicts.append(("protected", hex(off), (x0 + cx, y0 + cy), tag)); continue
                self.put(off, new, tag)


def glyph_mask(img):
    return tuple(tuple(1 if v else 0 for v in row) for row in img)


def find_glyph_groups(ref_mask):
    """ISO 범위에서 2x2 타일(연속 4타일이 아니라 BAT 상 2x2) 과 같은 마스크를 가진 타일 쌍을 찾는 건 BAT 없이는 불가.
    대신 각 8x8 사분면 마스크를 독립으로 매칭: 4개 사분면이 ISO 에 모두 존재하는 (오프셋 집합) 을 반환."""
    quads = {}
    for name, (qy, qx) in {"TL": (0, 0), "TR": (0, 8), "BL": (8, 0), "BR": (8, 8)}.items():
        quads[name] = tuple(tuple(ref_mask[qy + yy][qx + xx] for xx in range(8)) for yy in range(8))
    hits = {name: [] for name in quads}
    for off in range(ISO_LO, ISO_HI, 32):
        m = glyph_mask(tile_decode(iso[off:off + 32]))
        for name, qm in quads.items():
            if m == qm and any(any(r) for r in qm):
                hits[name].append(off)
    return hits


FONT11 = r"G:\Downloads\Korean Traslate Project\Font\Galmuri11.ttf"
FONT11C = r"G:\Downloads\Korean Traslate Project\Font\Galmuri11-Condensed.ttf"


def draw_segments(img, bg, segs):
    """img: 색 인덱스 2차원(list). segs: (px, text, pitch, style). style: shadow(13/11), outline(14/11), small(1), plain(13)."""
    h = len(img); w = len(img[0])
    for px0, text, pitch, style in segs:
        # 폰트 크기: Galmuri11/Condensed 는 PIL size 12 에서 비로소 온전한 11px 비트맵이 나온다(size 11 은 획 손실), Galmuri7 은 size 8
        size = 8 if style == "small" else 12
        font = ImageFont.truetype(FONT8 if style == "small" else (FONT11C if style.startswith("c") else FONT11), size)
        if text == "":                                   # 빈 세그먼트 = px0 부터 pitch 픽셀만 배경으로 지움
            for y in range(h):
                for x in range(px0, min(w, px0 + pitch)): img[y][x] = bg
            continue
        if style.startswith("c"): style = style[1:]       # cshadow/coutline/cplain → 폰트만 condensed
        noclear = style.endswith("+"); style = style.rstrip("+")   # '+' = 앞 세그먼트 위에 겹쳐 그리기(지우기 생략)
        # 세그먼트 범위 지우기: px0 .. px0 + 글자폭 합
        chars = list(text); widths = []
        for ch in chars:
            if ch == " ": widths.append(4 if style != "small" else 3); continue
            bb = font.getbbox(ch); widths.append(pitch if pitch else bb[2] - bb[0] + 1)
        total = sum(widths); end = min(w, px0 + total + (2 if style in ("shadow", "outline") else 1))
        if not noclear:
            for y in range(h):
                for x in range(px0, end): img[y][x] = bg
        fill = {"shadow": 13, "outline": 14, "small": 1, "plain": 13}[style]
        im = Image.new("L", (w, h), 0); dr = ImageDraw.Draw(im); x = px0
        ref = font.getbbox("한"); gh = ref[3] - ref[1]
        y0 = (h - gh) // 2 - ref[1] if style != "small" else (h - gh) // 2 - ref[1]
        for ch, wd in zip(chars, widths):
            if ch != " ":
                bb = font.getbbox(ch); dr.text((x - bb[0], y0), ch, font=font, fill=255)
            x += wd
        pxm = im.load(); mask = [[pxm[xx, yy] > 128 for xx in range(w)] for yy in range(h)]
        if style == "shadow":
            for yy in range(h):
                for xx in range(w):
                    if mask[yy][xx] and yy + 1 < h and xx + 1 < w and not mask[yy + 1][xx + 1]: img[yy + 1][xx + 1] = 11
        if style == "outline":
            for yy in range(h):
                for xx in range(w):
                    if not mask[yy][xx]:
                        for dy in (-1, 0, 1):
                            for dx in (-1, 0, 1):
                                ny, nx = yy + dy, xx + dx
                                if 0 <= ny < h and 0 <= nx < w and mask[ny][nx]: img[yy][xx] = 11
        for yy in range(h):
            for xx in range(w):
                if mask[yy][xx]: img[yy][xx] = fill
    return img


def main():
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    S = {s: Screen(s) for s in (3, 4, 5, 6, 7, 8)}   # s8 = 카드 보기(II) 화면 — 요소 없음, 공유 타일 확인·미리보기용
    P = Patcher(S)
    ELEMS = []

    def elem(slot, x0, y0, w, h, segs, tag=None):
        ELEMS.append((slot, x0, y0, w, h, segs, tag)); P.register(slot, x0, y0, w, h)

    def _render(slot, x0, y0, w, h, segs, tag=None):
        scr = S[slot]; img = scr.rect_pixels(x0, y0, w, h)
        bg = Counter(v for row in img for v in row).most_common(1)[0][0]
        draw_segments(img, bg, segs)
        P.write_rect(scr, x0, y0, w, h, img, tag or f"s{slot}:{segs[0][1]}")

    SH, OL, SM = "shadow", "outline", "small"
    # s3 카드판
    elem(3, 43, 4, 10, 2, [(0, "", 80, SH), (5, "선공 정하기", 12, SH)])
    elem(3, 21, 12, 9, 2, [(0, "", 72, SH), (0, "카드를", 12, SH)])
    elem(3, 21, 14, 9, 2, [(0, "", 72, SH), (0, "내 주세요", 12, SH)])
    elem(3, 21, 18, 9, 1, [(32, "", 40, SM), (32, "설명", 8, SM)])
    elem(3, 21, 19, 9, 1, [(22, "", 50, SM), (22, "카드 보기", 8, SM)])
    # s4 상대 차례 / 득점 계산
    elem(4, 21, 13, 9, 2, [(0, "", 72, SH), (1, "상대 차례", 12, SH)])
    TITLE_P = [(2, "플레이어", 13, SH), (58, "득", 12, SH), (73, "점", 12, SH), (90, "계", 12, SH), (106, "산", 12, SH)]
    elem(4, 48, 3, 15, 2, TITLE_P)
    ROW2 = [(21, "점", 12, SH), (34, "패", 12, SH), (96, "장", 12, SH), (177, "점", 12, SH)]
    ROW1 = [(17, "점", 12, SH), (34, "패", 12, SH), (96, "장", 12, SH), (177, "점", 12, SH)]
    for slot, x0 in ((4, 35), (5, 3)):
        elem(slot, x0, 6, 25, 2, ROW2); elem(slot, x0, 8, 25, 2, ROW2); elem(slot, x0, 10, 25, 2, ROW1); elem(slot, x0, 12, 25, 2, ROW1)
    for slot, x0 in ((4, 33), (5, 1)):
        elem(slot, x0, 14, 6, 2, [(0, "", 48, SH), (2, "족보", 12, SH)])   # 完成役 → 족보 (사용자: 완성역 어색, 2026-10-10)
    for slot, x0 in ((4, 51), (5, 19)):
        elem(slot, x0, 22, 2, 2, [(2, "계", 12, SH)])
    # 역 이름 (외곽선): s4/s5 dim 표, s6 bright — 타일 공유 → 같은 픽셀 위상으로
    # 역 이름 셀(선형 매핑 기준 모두 고유 타일): r16 c34-40 ビーナス | c42-47 公爵 | c50-53 人物, r18 c34-38 スター | c42-47 偉人 | c49-54 アイテム, r20 c34-37 エド | c42-47 世界 | c49-54 建物
    R1 = [(0, "", 192, OL), (3, "비너스", 14, OL), (73, "공작", 13, OL), (129, "인물", 13, OL)]
    R2 = [(0, "", 192, OL), (4, "별", 14, OL), (73, "위인", 13, OL), (129, "아이템", 13, OL)]
    R3 = [(0, "", 192, OL), (5, "에드", 14, OL), (73, "세계", 13, OL), (129, "건물", 13, OL)]
    for slot, x0 in ((4, 34), (5, 2)):
        elem(slot, x0, 16, 24, 2, R1, f"s{slot}:roles1"); elem(slot, x0, 18, 24, 2, R2, f"s{slot}:roles2"); elem(slot, x0, 20, 24, 2, R3, f"s{slot}:roles3")
    elem(6, 39, 3, 7, 2, [(0, "", 56, OL), (3, "비너스", 14, OL)], "s6:비너스")
    elem(6, 54, 5, 5, 2, [(0, "", 40, OL), (4, "별", 14, OL)], "s6:별")
    elem(6, 37, 7, 6, 2, [(0, "", 48, OL), (9, "공작", 13, OL)], "s6:공작")   # 629-62E = s4 公爵 타일 공유 → 위상 2
    elem(6, 55, 9, 4, 2, [(0, "", 32, OL), (5, "에드", 14, OL)], "s6:에드")
    elem(6, 33, 13, 6, 2, [(0, "", 48, OL), (9, "세계", 13, OL)], "s6:세계")
    elem(6, 33, 15, 6, 2, [(0, "", 48, OL), (9, "위인", 13, OL)], "s6:위인")
    elem(6, 33, 17, 6, 2, [(0, "", 48, OL), (9, "인물", 13, OL)], "s6:인물")
    elem(6, 33, 19, 6, 2, [(0, "", 48, OL), (9, "아이템", 13, OL)], "s6:아이템")
    elem(6, 33, 21, 6, 2, [(0, "", 48, OL), (9, "건물", 13, OL)], "s6:건물")
    # s5 결과
    elem(5, 17, 3, 14, 2, [(0, "", 40, SH), (0, "마", 0, "shadow+"), (11, "스", 0, "cshadow+"), (20, "터", 0, "shadow+")] + [(50, "득", 12, SH), (65, "점", 12, SH), (82, "계", 12, SH), (98, "산", 12, SH)])
    elem(5, 34, 4, 11, 2, TITLE_P[:3])
    elem(5, 35, 7, 10, 2, [(0, "", 40, SH), (0, "마", 0, "shadow+"), (11, "스", 0, "cshadow+"), (20, "터", 0, "shadow+")] + [(50, "득", 12, SH), (65, "점", 12, SH)])
    elem(5, 34, 15, 11, 2, [(0, "", 88, SH), (12, "현재", 12, SH), (42, "획득", 12, SH), (73, "점", 12, SH)])   # 持ち 타일(6EC-6EF, c39-42 = px40-71)은 카드 보기 제목 「プレイヤー 持ち札」(s8)과 공유 → 「획득」만 (현재 획득 점 / 플레이어 획득 패, 사용자 결정 2026-10-10)
    elem(5, 43, 21, 12, 2, [(0, "", 96, SH), (0, "계속할까요?", 13, SH)])
    # s6 규칙
    elem(6, 55, 13, 9, 2, [(0, "", 72, SH), (3, "동색패 전부", 9, "cshadow")])
    RULE_T = [(21, "점", 12, SH), (34, "패", 12, SH), (64, "장", 12, SH), (77, "이", 12, SH), (90, "상", 12, SH)]
    elem(6, 50, 15, 14, 2, RULE_T, "s6:rule2")
    elem(6, 50, 17, 14, 2, [(0, "", 8, SH), (8, "인물", 12, SH)] + RULE_T[1:], "s6:rule3")
    elem(6, 50, 19, 14, 2, [(4, "물품", 12, SH)] + RULE_T[1:], "s6:rule4")
    elem(6, 50, 21, 14, 2, [(17, "점", 12, SH)] + RULE_T[1:], "s6:rule5")
    # s7 경품 교환
    elem(7, 2, 3, 8, 2, [(2, "경", 12, SH), (18, "품", 12, SH), (34, "교", 12, SH), (50, "환", 12, SH)])
    CS = "cshadow"
    # 경품명: 8px 반각 폰트 원본이라 열 폭이 좁다 → condensed. 5·6번은 첫 열 타일(7C8/7D8)을 공유하므로 둘 다 px9 부터 써서 첫 열을 비운다
    # 경품명: 5·6번 행은 첫 열 타일(7C8/7D8)을 공유하므로 모든 행을 px9(둘째 열)부터 써서 왼쪽 정렬을 맞춘다(사용자 요청 2026-10-10).
    #  1·7번 행은 고유 열이 6칸(48px)뿐이라 메뉴 표기와 같은 「기도방패」, 4번 행은 「신주리레이트」(공백 없음).
    items = [("기도방패", 9), ("달의 목걸이", 9), ("나무요정 장갑", 9), ("신주리레이트", 9), ("엘의 마법수", 9), ("에이놈 열매", 9), ("라이히풀", 9)]
    for i, (t, pt) in enumerate(items):
        elem(7, 7, 6 + i * 2, 11, 2, [(0, "", 88, CS), (9, t, pt, CS)], f"s7:{t}")
    # 같은 텍스트가 보이는 다른 화면의 셀도 등록(보호 판정용)
    for slot in (4, 6):
        P.register(slot, 21, 12, 9, 2); P.register(slot, 21, 14, 9, 2); P.register(slot, 21, 18, 9, 1); P.register(slot, 21, 19, 9, 1)
    P.register(7, 34, 4, 11, 2); P.register(7, 35, 7, 10, 2); P.register(7, 34, 15, 11, 2)
    for e in ELEMS: _render(*e)

    # ---------------- 출력 ----------------
    patches = [{"iso_off": off, "old_hex": iso[off:off + 32].hex().upper(), "new_hex": new.hex().upper(), "id": f"cardtile@{off:07X}", "mode": "bytes"} for off, new in sorted(P.patches.items())]
    json.dump({"format": "CARDGAME-TILES-B29", "patches": patches, "conflicts": P.conflicts}, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("tile patches:", len(patches), "conflicts:", len(P.conflicts))
    for c in P.conflicts[:40]: print("  !", c)
    # 미리보기: 패치 적용 ISO 타일로 각 화면 재구성
    newiso = bytearray(iso)
    for off, new in P.patches.items(): newiso[off:off + 32] = new
    def pal(vce):
        return [((((vce[i*2]|(vce[i*2+1]<<8))>>3)&7)*36, (((vce[i*2]|(vce[i*2+1]<<8))>>6)&7)*36, ((vce[i*2]|(vce[i*2+1]<<8))&7)*36) for i in range(512)]
    for slot, scr in S.items():
        cols = pal(open(VRAM_DIR / f"s{slot}_VCEPalette.bin", "rb").read())
        im = Image.new("RGB", (W * 8, H * 8)); Pm = im.load()
        for (x, y), (ti, tb, off) in scr.cells.items():
            w = scr.vram[(y * W + x) * 2] | (scr.vram[(y * W + x) * 2 + 1] << 8); p = (w >> 12) & 0xF
            px = tile_decode(newiso[off:off + 32] if off is not None else tb)
            for yy in range(8):
                for xx in range(8):
                    Pm[x * 8 + xx, y * 8 + yy] = cols[p * 16 + px[yy][xx]] if px[yy][xx] else cols[0]
        im = im.resize((im.width * 2, im.height * 2), Image.NEAREST); im.save(PREVIEW_DIR / f"s{slot}_kr.png")
    print("previews:", PREVIEW_DIR)


if __name__ == "__main__":
    main()
