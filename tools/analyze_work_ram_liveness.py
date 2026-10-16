# -*- coding: utf-8 -*-
r"""Step 28 판정기 — Work RAM 생존성 트레이스를 스크래치 창 결정으로 변환.

입력:
  translation/work_ram_liveness.tsv          (trace_work_ram_liveness.lua 산출, 바이트별 read/write)
  translation/work_ram_untouched_runs.tsv     (연속 미접근 구간)
  translation/global_token_continuation_capacity.json  (Step 25/27, 18개 실패 컨텍스트의 스크래치 요구량)

출력(콘솔 + translation/work_ram_scratch_verdict.json):
  * 연속 미접근 구간 순위
  * '읽기만 됨'(write=0, read>0) 구간 = 로드 데이터일 수 있어 준위험
  * 18개 컨텍스트 요구량(69..2974B) 대비 커버 판정 및 권장 스크래치 창

트레이스 TSV가 아직 없으면 실행 명령을 안내하고 종료.
"""
import os, json, sys

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR = os.path.join(GAME, "translation")
LIVE = os.path.join(TR, "work_ram_liveness.tsv")          # 콜백 모드(read+write)
FAST = os.path.join(TR, "work_ram_writes_fast.tsv")       # 고속 모드(write only)
RUNS = os.path.join(TR, "work_ram_untouched_runs.tsv")
CAP  = os.path.join(TR, "global_token_continuation_capacity.json")
OUT  = os.path.join(TR, "work_ram_scratch_verdict.json")
CUE  = os.path.join(GAME, "Tenshi_no_Uta_II-Datenshi_no_Sentaku_JAP.cue")
EMU  = os.path.join(GAME, "BizHawk-master", "output", "EmuHawk.exe")
LUA  = os.path.join(GAME, "tools", "trace_work_ram_liveness.lua")

BASE, SIZE = 0x2000, 0x2000
# 알려진 상시 사용 영역(제로페이지+스택)은 스크래치 후보에서 원천 제외
RESERVED_END = 0x2200   # $2000..$21FF (zero page + hw stack page)


def need_run_hint():
    print("트레이스 TSV가 없습니다. 먼저 EmuHawk로 원본을 실행해 증거를 수집하세요:\n")
    print("  ★ 반드시 코어를 PCEHawk 로 설정: Config→Cores→PCE-CD = PCEHawk")
    print("    (TurboNyma는 read/write 메모리 콜백을 지원하지 않아 트레이서가 조용히 실패합니다)\n")
    print(f'  & "{EMU}" `\n    --lua="{LUA}" `\n    "{CUE}"\n')
    print("타이틀→뉴게임→마을→대사 여러 개→메뉴→전투→씬전환 20회 이상을 플레이한 뒤")
    print("EmuHawk를 정상 종료하면 translation/work_ram_*.tsv 가 생성됩니다(15초마다 중간 저장).")
    print("그 후 이 스크립트를 재실행하세요.")


def load_scratch_requirements():
    """18개 실패 컨텍스트의 minimum_single_bank_scratch_bytes 목록."""
    if not os.path.exists(CAP):
        return []
    d = json.load(open(CAP, encoding="utf-8"))
    reqs = []
    for c in d.get("contexts", []):
        if not c.get("fits_token_continuation", True):
            need = c.get("minimum_single_bank_scratch_bytes")
            if need:
                reqs.append((f"{c.get('owner')}#{c.get('physical_grid')}", int(need)))
    reqs.sort(key=lambda x: x[1])
    return reqs


def parse_liveness():
    """(rows, mode) 반환. rows: addr -> (reads, writes). 고속모드는 reads=0 고정."""
    if os.path.exists(LIVE):
        rows = {}
        with open(LIVE, encoding="utf-8") as f:
            next(f)
            for line in f:
                a, r, w, ff, lf = line.rstrip("\n").split("\t")
                rows[int(a, 16)] = (int(r), int(w))
        return rows, "callback(read+write)"
    # 고속 write-diff 모드
    rows = {}
    with open(FAST, encoding="utf-8") as f:
        next(f)
        for line in f:
            a, w, fw = line.rstrip("\n").split("\t")
            rows[int(a, 16)] = (0, int(w))
    return rows, "fast(write-only)"


def contiguous_runs(rows, predicate):
    """predicate(addr,reads,writes)->bool 인 바이트의 연속 구간 [(start,end)]."""
    runs = []
    cur = None
    for addr in range(BASE, BASE + SIZE):
        r, w = rows.get(addr, (0, 0))
        ok = predicate(addr, r, w)
        if ok and cur is None:
            cur = [addr, addr + 1]
        elif ok and cur:
            cur[1] = addr + 1
        elif not ok and cur:
            runs.append(tuple(cur)); cur = None
    if cur:
        runs.append(tuple(cur))
    return runs


def main():
    if not ((os.path.exists(LIVE) or os.path.exists(FAST)) and os.path.exists(RUNS)):
        need_run_hint()
        return

    rows, mode = parse_liveness()
    print(f"[모드] {mode}")
    if mode.startswith("fast"):
        print("  (고속 모드: 읽기는 미측정. 'never_written'을 스크래치 후보로 봄 — 콜백 모드로 확정 권장)")
    total = len(rows)
    touched = sum(1 for r, w in rows.values() if r or w)
    written = sum(1 for r, w in rows.values() if w)
    read_only = sum(1 for r, w in rows.values() if r and not w)
    untouched = total - touched
    # 마지막 프레임(대략적 커버리지 규모)
    print(f"== Work RAM 생존성 요약 (총 {total}B) ==")
    print(f"  접근됨(read|write): {touched}  / 미접근: {untouched}")
    print(f"  쓰기 발생: {written}   읽기만(로드데이터 가능): {read_only}")

    # 완전 미접근 구간 (가장 안전한 스크래치)
    untouched_runs = contiguous_runs(rows, lambda a, r, w: r == 0 and w == 0 and a >= RESERVED_END)
    untouched_runs.sort(key=lambda t: -(t[1] - t[0]))
    # 쓰기만 없음(읽기 허용X는 아님) — 준위험: 게임이 안 쓰지만 읽을 수 있음
    nowrite_runs = contiguous_runs(rows, lambda a, r, w: w == 0 and a >= RESERVED_END)
    nowrite_runs.sort(key=lambda t: -(t[1] - t[0]))

    print(f"\n== 완전 미접근 연속 구간 (스크래치 최우선 후보, ${RESERVED_END:04X} 이상) ==")
    for s, e in untouched_runs[:15]:
        print(f"  ${s:04X}..${e-1:04X}  {e-s}B")
    biggest = (untouched_runs[0][1]-untouched_runs[0][0]) if untouched_runs else 0

    print(f"\n== 쓰기 없음(읽기는 될 수 있음) 연속 구간 (차선책) ==")
    for s, e in nowrite_runs[:8]:
        print(f"  ${s:04X}..${e-1:04X}  {e-s}B")
    biggest_nowrite = (nowrite_runs[0][1]-nowrite_runs[0][0]) if nowrite_runs else 0

    # 18개 컨텍스트 요구량 대비 판정
    reqs = load_scratch_requirements()
    print(f"\n== 18개 실패 컨텍스트 스크래치 요구량 대비 ==")
    if reqs:
        worst = max(n for _, n in reqs)
        covered = sum(1 for _, n in reqs if n <= biggest)
        print(f"  최대 요구: {worst}B (전부 해결하려면 이만큼의 단일 연속창 필요)")
        print(f"  가장 큰 완전-미접근 창: {biggest}B → {covered}/{len(reqs)} 컨텍스트 커버")
        if biggest >= worst:
            print(f"  ✅ 완전 미접근 창 하나로 18개 전부 해결 가능")
        else:
            print(f"  ⚠️  완전 미접근 창만으론 부족. 차선(쓰기없음) 최대 {biggest_nowrite}B "
                  f"→ {sum(1 for _,n in reqs if n<=biggest_nowrite)}/{len(reqs)}")
    else:
        # 요구량 JSON 없으면 문서화된 임계값 사용
        print("  (요구량 JSON 없음 — 문서 기준: 최대 2974B, 12/18 ≤2048B)")
        worst = 2974
        print(f"  가장 큰 완전-미접근 창: {biggest}B → {'✅ 2974 충족' if biggest>=2974 else '⚠️ 2974 미달'}")

    verdict = {
        "format": "WORK-RAM-SCRATCH-VERDICT",
        "total_bytes": total, "touched": touched, "untouched": untouched,
        "written": written, "read_only": read_only,
        "reserved_below": RESERVED_END,
        "largest_untouched_run_bytes": biggest,
        "largest_nowrite_run_bytes": biggest_nowrite,
        "untouched_runs": [{"start": s, "end": e, "len": e - s} for s, e in untouched_runs[:40]],
        "nowrite_runs": [{"start": s, "end": e, "len": e - s} for s, e in nowrite_runs[:40]],
        "context_scratch_requirements": [{"context": c, "bytes": n} for c, n in reqs],
        "recommended_scratch": (
            {"start": untouched_runs[0][0], "len": biggest} if untouched_runs else None
        ),
    }
    json.dump(verdict, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n-> {OUT}")
    if untouched_runs:
        s = untouched_runs[0][0]
        print(f"권장 스크래치 창: ${s:04X}..${s+biggest-1:04X} ({biggest}B, 완전 미접근)")


if __name__ == "__main__":
    main()
