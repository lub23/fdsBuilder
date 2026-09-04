#!/usr/bin/env python3
"""Classify every facility into one of three surrogate-model families.

The three families are:

* ``specific``   - single-building real facilities. The surrogate predicts the
                   facility's single Dk target directly.
* ``equivalent`` - template facilities with a ``subtarget_damage_summary/``
                   directory holding one CSV per sub-target building. The
                   surrogate predicts every sub-target Dk and derives the
                   overall Dk as the value-weighted sum of the sub-targets.
* ``hangar``     - airport hangar scale facilities. Each scale is a single
                   building (no sub-target summary), but the three scales are
                   structurally similar and are handled as independent
                   single-target models (one per scale).

The classification is data-driven: the presence of a
``subtarget_damage_summary`` directory is the authoritative discriminator.
Buildings are counted from the facility JSON ``buildings`` list. Facilities
with no case data at all are excluded from the manifest but reported.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_damage.src.data.cases_loader import iter_facilities  # noqa: E402


SUBTARGET_DIR_NAME = "subtarget_damage_summary"

FAMILY_LABELS: Mapping[str, str] = {
    "specific": "特异模型（单目标，直接预测设施 Dk 与等级）",
    "equivalent": "等效模型（多目标，预测各子目标并解析求整体）",
    "hangar": "机场机库（单建筑规模族，每规模一个单目标模型）",
}


def _facility_scale_suffix(name: str) -> str | None:
    """Return ``small``/``medium``/``large`` when the name carries a scale."""
    lowered = str(name).lower()
    for scale in ("small", "medium", "large"):
        if lowered.endswith(f"_{scale}"):
            return scale
    return None


def _building_count(facility_name: str, facilities_root: Path) -> int:
    """Return the number of buildings declared in the facility JSON, if any."""
    json_path = facilities_root / f"{facility_name}.json"
    if not json_path.exists():
        return 0
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    buildings = data.get("buildings")
    if isinstance(buildings, list):
        return len(buildings)
    return 0


def _subtarget_files(facility_root: Path) -> list[Path]:
    summary_dir = facility_root / SUBTARGET_DIR_NAME
    if not summary_dir.is_dir():
        return []
    return sorted(summary_dir.glob("*subtarget_Dk_*.csv"))


def _subtarget_info(subtarget_files: list[Path]) -> list[dict[str, str]]:
    info: list[dict[str, str]] = []
    for csv_path in subtarget_files:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig", nrows=0)
        except Exception:
            continue
        columns = {str(c) for c in df.columns}
        name = "".join(csv_path.stem.split("subtarget_Dk_", 1)[1:]) if "subtarget_Dk_" in csv_path.stem else csv_path.stem
        info.append(
            {
                "csv": csv_path.name,
                "subtarget_en": str(name),
                "has_dk_column": "Dk" in columns,
                "has_grade_column": "damage_grade" in columns,
                "has_value_column": "total_asset_value_CNY" in columns,
            }
        )
    return info


def classify_facilities(
    cases_root: Path,
    facilities_root: Path,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Classify all facility directories under ``cases_root``.

    Returns ``(manifest, skipped)`` where ``skipped`` lists facility names
    with no usable case data.
    """
    manifest: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    known_facilities: dict[str, Any] = {}

    for summary in iter_facilities(cases_root):
        name = str(summary.facility_name)
        known_facilities[name] = summary

    for name, summary in known_facilities.items():
        if summary.fds_path is None and not summary.cases:
            skipped.append(name)
            continue
        facility_root = cases_root / name
        subtarget_files = _subtarget_files(facility_root)
        building_count = _building_count(name, facilities_root)
        scale = _facility_scale_suffix(name)
        if subtarget_files:
            family = "equivalent"
        elif name.lower().startswith("airport_hangar") and scale is not None:
            family = "hangar"
        else:
            family = "specific"
        manifest[name] = {
            "facility_name": name,
            "family": family,
            "family_label": FAMILY_LABELS[family],
            "scale": scale,
            "building_count": building_count,
            "case_count": int(len(summary.cases)),
            "has_subtarget_summary": bool(subtarget_files),
            "subtarget_files": [str(p.relative_to(facility_root)) for p in subtarget_files],
            "subtargets": _subtarget_info(subtarget_files),
        }
    return manifest, skipped


def _write_manifest(manifest: dict[str, dict[str, Any]], path: Path) -> None:
    payload: dict[str, Any] = {
        "families": {name: label for name, label in FAMILY_LABELS.items()},
        "counts": {
            family: sum(1 for item in manifest.values() if item["family"] == family)
            for family in FAMILY_LABELS
        },
        "facilities": manifest,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_summary(manifest: dict[str, dict[str, Any]], skipped: list[str]) -> None:
    print("=== 模型类别清单（数据驱动判定） ===")
    for family in ("specific", "equivalent", "hangar"):
        rows = [item for item in manifest.values() if item["family"] == family]
        print(f"\n[{family}] {FAMILY_LABELS[family]}  ({len(rows)} 个)")
        for item in sorted(rows, key=lambda r: r["facility_name"]):
            scale = f" scale={item['scale']}" if item["scale"] else ""
            sub = f" 子目标={len(item['subtargets'])}" if item["subtargets"] else ""
            print(f"  {item['facility_name']}{scale} 工况={item['case_count']}{sub}")
    if skipped:
        print(f"\n跳过（无可用数据）: {', '.join(skipped)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", type=Path, default=Path(__file__).resolve().parents[1] / "cases")
    parser.add_argument(
        "--facilities-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "facilities",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "output" / "target_type_manifest.json",
    )
    args = parser.parse_args()

    manifest, skipped = classify_facilities(args.cases_dir, args.facilities_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest, args.output)
    _print_summary(manifest, skipped)
    print(f"\n清单已写入: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
