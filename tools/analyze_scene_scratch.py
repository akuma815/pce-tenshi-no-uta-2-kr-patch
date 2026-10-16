# -*- coding: utf-8 -*-
r"""Step 29 — 씬별 Work RAM 스크래치 측정 결과를 18개 오버플로 컨텍스트 판정으로.

입력:
  translation/scene_scratch.tsv                        (trace_scene_scratch.lua)
  translation/global_token_continuation_capacity.json  (씬별 필요량 need)

각 오버플로 씬(LBA)에서 측정된 '가장 큰 자유 연속구간'이 그 씬의 need 이상인지 판정.
같은 LBA가 여러 번 측정되면 보수적으로 최솟값 사용. 미측정 씬은 pending으로 표시.
"""
import os, json, collections

GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR = os.path.join(GAME, "translation")
SCENE = os.path.join(TR, "scene_scratch.tsv")
CAP = os.path.join(TR, "global_token_continuation_capacity.json")
OUT = os.path.join(TR, "scene_scratch_verdict.json")


def load_needs():
    """오버플로 컨텍스트의 LBA별 최대 need(minimum_single_bank_scratch_bytes)."""
    d = json.load(open(CAP, encoding="utf-8"))
    m = {}
    for c in d["contexts"]:
        if not c.get("fits_token_continuation", True):
            m[c["lba"]] = max(m.get(c["lba"], 0), c.get("minimum_single_bank_scratch_bytes", 0))
    return m


def load_scene():
    if not os.path.exists(SCENE):
        return {}
    measured = collections.defaultdict(list)  # lba -> [ (largest, total, runs_str) ]
    with open(SCENE, encoding="utf-8") as f:
        next(f, None)
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 6:
                continue
            lba, frames, largest, total, nruns, runs = p[:6]
            measured[int(lba)].append((int(largest), int(total), runs))
    return measured


def main():
    needs = load_needs()
    measured = load_scene()

    if not measured:
        print("scene_scratch.tsv 가 없습니다. 씬 트레이서를 먼저 실행하세요:")
        print("  powershell -ExecutionPolicy Bypass -File tools\\run_liveness_trace.ps1 -Scene")
        print("  (PCEHawk 코어로, 오버플로 씬들에 들어가 대사를 진행. 큰 6개 LBA 우선:")
        print("   866, 2306, 962, 482, 1346, 1826)")
        return

    print(f"{'LBA':>6} {'need':>6} {'measured_largest(min)':>22} {'verdict':>10}")
    ok = fail = pending = 0
    rows = []
    for lba in sorted(needs):
        need = needs[lba]
        if lba in measured:
            # 보수적: 여러 윈도우 중 largest_free 최솟값
            largest = min(m[0] for m in measured[lba])
            total = min(m[1] for m in measured[lba])
            verdict = "FIT" if largest >= need else ("FRAG?" if total >= need else "FAIL")
            if verdict == "FIT": ok += 1
            elif verdict == "FAIL": fail += 1
            else: fail += 1
            print(f"{lba:>6} {need:>6} {largest:>22} {verdict:>10}"
                  + (f"  (total_free={total})" if verdict != "FIT" else ""))
            rows.append({"lba": lba, "need": need, "largest_free": largest,
                         "total_free": total, "verdict": verdict})
        else:
            pending += 1
            print(f"{lba:>6} {need:>6} {'--미측정--':>22} {'PENDING':>10}")
            rows.append({"lba": lba, "need": need, "verdict": "PENDING"})

    print(f"\nFIT={ok}  FAIL/FRAG={fail}  PENDING={pending}  (총 {len(needs)})")
    if ok == len(needs):
        print("✅ 측정된 모든 오버플로 씬이 씬-로컬 연속 스크래치로 해결 가능")
    elif pending:
        print("⏳ 미측정 씬이 있습니다. 해당 씬들을 플레이해 데이터를 보강하세요.")
    json.dump({"format": "SCENE-SCRATCH-VERDICT", "rows": rows,
               "fit": ok, "fail": fail, "pending": pending},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
