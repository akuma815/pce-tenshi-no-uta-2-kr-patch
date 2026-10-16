#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""한자 음독 직역 감사 (2026-10-12): 원문 한자 연속(2자 이상)의 한국 한자음이 번역에 그대로 들어간 곳을 찾는다.
계기: 크레딧 이름 矢尾一樹 →「시미일수」, 若本規夫 →「약본규부」(일본 인명을 한자음으로 읽음). 게임 용어(天使→천사)는 정상이므로
후보를 모아 사람이 분류한다. 읽기표 = hanja 패키지 table.yml(유니코드 한자 → 대표음), 두음법칙 변이(ㄹ→ㄴ·ㅇ, ㄴ→ㅇ) 허용.
사용: python -X utf8 tools/audit_kanji_readings.py <hanja_reading.json> <출력 tsv>
"""
import csv, io, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "translation"
csv.field_size_limit(10 ** 7)
table = json.load(open(sys.argv[1], encoding="utf-8"))
out_path = Path(sys.argv[2])
KANJI = re.compile(r"[一-鿿々]{2,}")


def variants(syl: str) -> set[str]:
    """두음법칙: 첫소리 ㄹ→ㄴ/ㅇ, ㄴ→ㅇ."""
    o = ord(syl) - 0xAC00
    if not 0 <= o < 11172:
        return {syl}
    cho, rest = divmod(o, 588)
    out = {syl}
    for c in {5: (2, 11), 2: (11,)}.get(cho, ()):   # ㄹ(5)→ㄴ(2)·ㅇ(11), ㄴ(2)→ㅇ(11)
        out.add(chr(0xAC00 + c * 588 + rest))
    return out


def reading_hits(orig: str, ko: str):
    hits = []
    plain = re.sub(r"\s|\\[np]|\{[^}]*\}", "", ko)
    for m in KANJI.finditer(orig):
        run = m.group(0)
        syls = [table.get(c) for c in run]
        if None in syls:
            continue
        # 각 음절의 변이 조합으로 정규식
        pat = "".join("[" + "".join(sorted(variants(s))) + "]" for s in syls)
        if re.search(pat, plain):
            hits.append((run, "".join(syls)))
    return hits


rows = []
# 1) 제자리 색인(메뉴·이름·배너 등)
raw = (T / "ziria_z8_text_entry_index.csv").read_bytes().decode("utf-8-sig")
for r in csv.DictReader(io.StringIO(raw, newline="")):
    if r["translation"] and r["original"]:
        rows.append(("index", r["id"], r["subcategory"], r["original"], r["translation"]))
# 2) 대사 맵(b3)
for r in csv.reader(io.open(T / "btrack_b3_translation_map.tsv", encoding="utf-8", newline=""), delimiter="\t"):
    if len(r) > 5 and r[0].startswith("iso:"):
        rows.append(("b3", r[0], r[1], None, r[5]))
master = {r[0]: r for r in csv.reader(open(T / "full_extraction" / "master_text.csv", encoding="utf-8", newline=""))}
rows = [(s, i, c, o if o is not None else (master[i][11] if i in master else ""), k) for s, i, c, o, k in rows]
# 3) 보충·전투·메뉴 덮어쓰기 tsv
for name in ("b9_gap_supplement_source.tsv", "b10_menu_overrides.tsv", "b10_unindexed_battle.tsv"):
    p = T / name
    if not p.exists():
        continue
    for r in csv.DictReader(io.open(p, encoding="utf-8", newline=""), delimiter="\t"):
        o = r.get("original") or r.get("jp") or r.get("note") or ""
        k = r.get("translation") or r.get("ko") or ""
        if o and k:
            rows.append((name, r.get("id") or r.get("old_hex", "")[:16], "", o, k))

out = []
for src, rid, cat, o, k in rows:
    for run, rd in reading_hits(o, k):
        short = len(re.sub(r"\{[^}]*\}|[\s　]", "", o)) <= 10
        out.append((src, rid, cat, "short" if short else "long", run, rd, o.replace("\n", " ")[:80], k.replace("\n", " ")[:80]))
with out_path.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, delimiter="\t")
    w.writerow(["src", "id", "category", "len", "kanji", "reading", "original", "translation"])
    w.writerows(out)
print("pairs", len(rows), "hits", len(out), "distinct kanji runs", len({x[4] for x in out}))
