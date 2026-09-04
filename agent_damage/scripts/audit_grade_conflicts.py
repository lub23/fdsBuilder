#!/usr/bin/env python3
"""Audit grade ambiguity: same-parameter cases with conflicting grades.

A conflicting pair is defined as two cases of the same facility whose physical
drivers (radiation heat flux q, azimuth a, elevation e, fire duration d,
simulation time t, parsed from the case name) are IDENTICAL, yet the recorded
Dk falls on different sides of a grade threshold.  Those are genuine data
inconsistencies worth checking in the raw FDS output.  Cases differing in the
raw parameters are physical differences, not conflicts, and are reported
separately as boundary-band observations.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.scripts.detect_target_type import classify_facilities  # noqa: E402
from agent_damage.src.data.experimental import (  # noqa: E402
    DK_GRADE_NAMES,
    load_experimental_dataset,
    dk_to_grade,
)

TH = (0.04, 0.10, 0.40)
FACILITIES = [
    "sspf", "ligen", "lcc", "MPPF", "factory", "boeing",
    "tesla", "maf", "SLC", "Hangar",
    "machinery manufacturing_small", "metallurgical_facilities_large",
    "aerospace_medium", "machinery_manufacturing_medium",
]
FACILITIES = [f.replace(" ", "_") for f in FACILITIES]

_CASE_RE = re.compile(
    r"^(?P<facility>.+?)_q(?P<q>-?\d+(?:\.\d+)?)"
    r"_a(?P<a>-?\d+(?:\.\d+)?)"
    r"_e(?P<e>-?\d+(?:\.\d+)?)"
    r"_d(?P<d>-?\d+(?:\.\d+)?)"
    r"_t(?P<t>-?\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)


def main() -> int:
    manifest, _ = classify_facilities(Path("agent_damage/cases"), Path("facilities"))
    df = load_experimental_dataset(Path("agent_damage/cases"), min_completion=0.0, min_simulation_time_s=0.0)
    lines: list[str] = []
    for fac in FACILITIES:
        sub = df[df["facility_name"].eq(fac)].reset_index(drop=True)
        if len(sub) < 10:
            continue
        groups: dict[tuple, list[int]] = defaultdict(list)
        parsed = []
        for idx, row in sub.iterrows():
            m = _CASE_RE.match(str(row["case_name"]))
            if not m:
                continue
            key = (m.group("q"), m.group("a"), m.group("e"), m.group("d"), m.group("t"))
            groups[key].append(idx)
            parsed.append((idx, key))
        conflicts: list[tuple[float, int, int]] = []
        for key, idxs in groups.items():
            if len(idxs) < 2:
                continue
            for i_i in range(len(idxs)):
                for j_i in range(i_i + 1, len(idxs)):
                    i, j = idxs[i_i], idxs[j_i]
                    gi = int(dk_to_grade(float(sub.loc[i, "Dk"])))
                    gj = int(dk_to_grade(float(sub.loc[j, "Dk"])))
                    if gi != gj:
                        conflicts.append((i, j))
        lines.append(f"\n===== {fac} (n={len(sub)}, same-param groups={len(dedup_counts(groups))}, conflicts={len(conflicts)}) =====")
        for i, j in conflicts[:8]:
            ri, rj = sub.loc[i], sub.loc[j]
            gi, gj = dk_to_grade(float(ri["Dk"])), dk_to_grade(float(rj["Dk"]))
            lines.append(
                f"  grade{gi}({DK_GRADE_NAMES[gi]}) vs grade{gj}({DK_GRADE_NAMES[gj]}):  "
                f"{ri['case_name']} Dk={ri['Dk']:.4f}  |  {rj['case_name']} Dk={rj['Dk']:.4f}"
            )
    report = "\n".join(lines)
    Path("agent_damage/output/grade_conflict_audit.txt").write_text(report, encoding="utf-8")
    print(report[:5000])
    return 0


def dedup_counts(groups):
    return groups


if __name__ == "__main__":
    raise SystemExit(main())