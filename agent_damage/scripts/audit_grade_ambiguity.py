#!/usr/bin/env python3
"""List grade-ambiguous case pairs (feature-close, different grade) per facility."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.scripts.detect_target_type import classify_facilities  # noqa: E402
from agent_damage.src.data.experimental import (  # noqa: E402
    DK_GRADE_NAMES,
    load_experimental_dataset,
    select_per_model_feature_columns,
    dk_to_grade,
)

FACILITIES = [
    "sspf", "ligen", "lcc", "MPPF", "factory", "boeing",
    "tesla", "maf", "SLC", "Hangar",
    "machinery_manufacturing_small", "metallurgical_facilities_large",
    "aerospace_medium", "machinery_manufacturing_medium",
]

TH = np.array([0.04, 0.10, 0.40])


def main() -> int:
    manifest, _ = classify_facilities(Path("agent_damage/cases"), Path("facilities"))
    df = load_experimental_dataset(Path("agent_damage/cases"), min_completion=0.0, min_simulation_time_s=0.0)
    out_lines: list[str] = []
    for fac in FACILITIES:
        sub = df[df["facility_name"].eq(fac)].reset_index(drop=True)
        if len(sub) < 10:
            continue
        feats = select_per_model_feature_columns(sub)
        X = sub[feats].to_numpy(dtype=float)
        g = sub["Dk"].map(dk_to_grade).to_numpy()
        mu, sd = X.mean(0), X.std(0) + 1e-9
        Xn = (X - mu) / sd
        D = cdist(Xn, Xn)
        np.fill_diagonal(D, np.inf)
        pairs: list[tuple[float, int, int]] = []
        for i in range(len(sub)):
            order = np.argsort(D[i])
            for j in order:
                if g[j] == g[i]:
                    continue
                if D[i, j] > 1.0:
                    break
                pairs.append((float(D[i, j]), int(i), int(j)))
        pairs.sort(key=lambda t: t[0])
        if not pairs:
            continue
        out_lines.append(f"\n===== {fac} (n={len(sub)}, feats={len(feats)}, total_conflict_pairs={len(pairs)}) =====")
        for dist, i, j in pairs[:12]:
            row_i = sub.iloc[i]
            row_j = sub.iloc[j]
            out_lines.append(
                f"  d={dist:.3f}  grade{g[i]}({DK_GRADE_NAMES[g[i]]}) vs grade{g[j]}({DK_GRADE_NAMES[g[j]]})\n"
                f"    A {row_i['case_name']}: Dk={row_i['Dk']:.4f}  {row_i['heat_flux_log10']:.2f}/{row_i['heat_dose_log10']:.2f}/{row_i['duration_s']:.0f}s elev={row_i.get('elevation_sin', float('nan')):.2f} azim={row_i.get('azimuth_sin', float('nan')):.2f}\n"
                f"    B {row_j['case_name']}: Dk={row_j['Dk']:.4f}  {row_j['heat_flux_log10']:.2f}/{row_j['heat_dose_log10']:.2f}/{row_j['duration_s']:.0f}s elev={row_j.get('elevation_sin', float('nan')):.2f} azim={row_j.get('azimuth_sin', float('nan')):.2f}"
            )
    report = "\n".join(out_lines)
    Path("agent_damage/output/grade_ambiguity_audit.txt").write_text(report, encoding="utf-8")
    print(report[:6000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())