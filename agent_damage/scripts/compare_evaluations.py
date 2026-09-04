#!/usr/bin/env python3
"""Compare split-model evaluation between two evaluation json files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

OLD = Path("agent_damage/output/dir1_full38/split_model_evaluation.json")
NEW = Path("agent_damage/output/split_model_evaluation.json")


def _index(path: Path) -> dict:
    with path.open() as fh:
        data = json.load(fh)
    by_name: dict[str, dict] = {}
    for entry in data["models"]:
        name = entry["facility_name"].lower()
        row = {
            "cv": entry.get("cv_grade_accuracy"),
            "hold": entry.get("holdout_grade_accuracy"),
            "n": entry.get("case_count"),
        }
        for st in entry.get("subtarget_holdout_accuracy") or []:
            row["st_" + st["subtarget"]] = st["accuracy"]
        by_name[name] = row
    return by_name


def main() -> int:
    old = _index(OLD)
    new = _index(NEW)
    names = sorted(set(old) | set(new))
    print(f"{'facility':<32}{'old_cv':>8}{'old_hold':>9}{'n':>5} | "
          f"{'new_cv':>8}{'new_hold':>9}{'n':>5}  delta_hold")
    for name in names:
        o_row = old.get(name, {})
        n_row = new.get(name, {})
        ocv = o_row.get("cv", "-")
        oho = o_row.get("hold", "-")
        onn = o_row.get("n", "-")
        ncv = n_row.get("cv", "-")
        nho = n_row.get("hold", "-")
        nnn = n_row.get("n", "-")
        delta = ""
        if isinstance(oho, (int, float)) and isinstance(nho, (int, float)):
            d = nho - oho
            delta = f"{d:+.3f}" + (" ^" if d > 0.02 else " v" if d < -0.02 else "")
        print(f"{name:<28}{str(ocv):>8}{str(oho):>9}{str(onn):>5} | "
              f"{str(ncv):>8}{str(nho):>9}{str(nnn):>5}  {delta}")

    def _counter(rows: dict) -> tuple[int, int]:
        met = sum(1 for r in rows.values()
                  if (r.get("hold") or 0) >= 0.95 and (r.get("cv") or 0) >= 0.95)
        below = sum(1 for r in rows.values()
                    if (r.get("hold") or 0) < 0.95 and (r.get("cv") or 0) < 0.95)
        return met, below

    m_o, b_o = _counter(old)
    m_n, b_n = _counter(new)
    print(f"\nOLD: both>=0.95 = {m_o}/{len(old)}, both<0.95 = {b_o}")
    print(f"NEW: both>=0.95 = {m_n}/{len(new)}, both<0.95 = {b_n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())