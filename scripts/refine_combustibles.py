#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refine facility JSONs to the slimmed combustible core set.

Two passes over every ``facilities/*.json``:

1. **Combustibles** — remap each ``key`` to its core key via
   ``models.materials.COMBUSTIBLE_REMAP`` and merge entries that collapse to
   the same core key within the same list (summing ``count`` and elementwise
   ``count_scaled``).  This both folds the library down to the 5-key core and
   reduces the number of distinct combustible types per fire compartment.

2. **Specialized components** — rockets are made "fewer but larger": counts are
   capped to <= 2 and ``ROCKET_VEHICLE_SMALL`` is promoted to
   ``ROCKET_VEHICLE_MEDIUM`` so the laid-down rockets read as substantial
   objects rather than a thin forest of slivers.

The script is idempotent: core keys map to themselves and capped counts stay
capped.  Run from the repo root::

    python3 scripts/refine_combustibles.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.materials import COMBUSTIBLE_REMAP  # noqa: E402

ROCKET_CAP = 2
ROCKET_PROMOTE = {"ROCKET_VEHICLE_SMALL": "ROCKET_VEHICLE_MEDIUM"}


def _merge_combustibles(entries: list) -> tuple[list, bool]:
    """Remap + merge a single ``combustibles`` list. Returns (new_list, changed)."""
    changed = False
    merged: dict = {}
    order: list = []
    for e in entries:
        old_key = e.get("key", "")
        new_key = COMBUSTIBLE_REMAP.get(old_key, old_key)
        if new_key != old_key:
            changed = True
        # Distinguish entries that genuinely should stay separate (different
        # placement boundary or rotation) so story-level layouts are preserved.
        sig = (new_key, json.dumps(e.get("boundary"), sort_keys=True), e.get("rotation", 0))
        if sig not in merged:
            new_e = dict(e)
            new_e["key"] = new_key
            merged[sig] = new_e
            order.append(sig)
        else:
            changed = True
            tgt = merged[sig]
            tgt["count"] = int(tgt.get("count", 0)) + int(e.get("count", 0))
            a = tgt.get("count_scaled")
            b = e.get("count_scaled")
            if isinstance(a, list) and isinstance(b, list):
                n = max(len(a), len(b))
                a = a + [a[-1]] * (n - len(a)) if a else [0] * n
                b = b + [b[-1]] * (n - len(b)) if b else [0] * n
                tgt["count_scaled"] = [int(a[i]) + int(b[i]) for i in range(n)]
            elif isinstance(b, list):
                tgt["count_scaled"] = list(b)
    return [merged[s] for s in order], changed


def _refine_components(entries: list) -> bool:
    """Cap rocket counts and promote SMALL->MEDIUM in place. Returns changed."""
    changed = False
    for e in entries:
        key = e.get("key", "")
        if not key.startswith("ROCKET_VEHICLE"):
            continue
        if key in ROCKET_PROMOTE:
            e["key"] = ROCKET_PROMOTE[key]
            changed = True
        if int(e.get("count", 0)) > ROCKET_CAP:
            e["count"] = ROCKET_CAP
            changed = True
        cs = e.get("count_scaled")
        if isinstance(cs, list):
            capped = [min(int(v), ROCKET_CAP) for v in cs]
            if capped != cs:
                e["count_scaled"] = capped
                changed = True
    return changed


def _walk(obj) -> bool:
    """Recursively refine combustibles / specialized_components. Returns changed."""
    changed = False
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "combustibles" and isinstance(v, list):
                obj[k], c = _merge_combustibles(v)
                changed = changed or c
            elif k == "specialized_components" and isinstance(v, list):
                changed = _refine_components(v) or changed
                changed = _walk(v) or changed
            else:
                changed = _walk(v) or changed
    elif isinstance(obj, list):
        for x in obj:
            changed = _walk(x) or changed
    return changed


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files = sorted(glob.glob(os.path.join(root, "facilities", "*.json")))
    total_changed = 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        if _walk(data):
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            total_changed += 1
            print(f"  refined {os.path.basename(f)}")
        else:
            print(f"  unchanged {os.path.basename(f)}")
    print(f"\nDone. {total_changed}/{len(files)} facility files updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
