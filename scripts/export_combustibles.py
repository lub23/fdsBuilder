#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export all combustibles & specialized components to Excel.

Structure: one Excel file, one sheet per facility JSON.
Each row = one combustible / specialized_component entry with its
building, story, and compartment context as columns.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.building import Building, BuildingGroup
from models.materials import COMBUSTIBLE_LIBRARY
from models.combustibles import SPECIALIZED_COMPONENTS
from models.parameter_engine import ParameterEngine

LOCATION_COLUMNS = [
    "名称", "英文Key", "类型", "总数量",
    "长度(m)", "宽度(m)", "高度(m)",
    "热释放速率(kW/m²)", "点燃温度(°C)",
    "密度(kg/m³)", "导热系数(W/m·K)", "比热(kJ/kg·K)",
    "燃烧热(kJ/kg)", "参考温度(°C)", "出现位置",
]


def _get_matl(cb_def: dict) -> dict:
    matl = cb_def.get("matl") or {}
    return {
        "DENSITY": matl.get("DENSITY", "-"),
        "CONDUCTIVITY": matl.get("CONDUCTIVITY", "-"),
        "SPECIFIC_HEAT": matl.get("SPECIFIC_HEAT", "-"),
        "HEAT_OF_COMBUSTION": matl.get("HEAT_OF_COMBUSTION", "-"),
        "REFERENCE_TEMPERATURE": matl.get("REFERENCE_TEMPERATURE", "-"),
    }


def _collect_facility_rows(bg: BuildingGroup) -> list[dict]:
    """Return a flat list of per-entry dicts, each representing one combustible
    occurrence at a specific building/story/compartment. These are later
    grouped by (key, type) into a single row per combustible species."""
    entries: list[dict] = []
    for building in bg.buildings:
        bld_name = building.cn_name or building.name

        for story in building.stories:
            story_name = story.name

            for fc in story.fire_compartments:
                for cb_entry in fc.combustibles:
                    key = cb_entry.get("key", "")
                    cb_def = COMBUSTIBLE_LIBRARY.get(key)
                    if cb_def is None:
                        continue
                    matl = _get_matl(cb_def)
                    loc = f"{bld_name}/{story_name}/{fc.name}"
                    entries.append(dict(
                        key=key, name=cb_def.get("name", key), typ="combustible",
                        count=cb_entry.get("count", 1),
                        length=cb_def.get("length", "-"),
                        width=cb_def.get("width", "-"),
                        height=cb_def.get("height", "-"),
                        hrrpua=cb_def.get("hrrpua", "-"),
                        ign_temp=cb_def.get("ignition_temp", "-"),
                        density=matl["DENSITY"], conductivity=matl["CONDUCTIVITY"],
                        specific_heat=matl["SPECIFIC_HEAT"],
                        heat_of_combustion=matl["HEAT_OF_COMBUSTION"],
                        ref_temp=matl["REFERENCE_TEMPERATURE"],
                        loc=loc,
                    ))

                for sc_info in fc.specialized_components:
                    key = sc_info.get("key", "")
                    comp = SPECIALIZED_COMPONENTS.get(key)
                    if comp is None:
                        continue
                    empty = _get_matl({"matl": {}})
                    loc = f"{bld_name}/{story_name}/{fc.name}"
                    entries.append(dict(
                        key=key, name=comp.name, typ="specialized_component",
                        count=sc_info.get("count", 1),
                        length=comp.total_length, width=comp.total_width,
                        height=comp.total_height,
                        hrrpua=comp.hrrpua, ign_temp=comp.ignition_temp,
                        density=empty["DENSITY"], conductivity=empty["CONDUCTIVITY"],
                        specific_heat=empty["SPECIFIC_HEAT"],
                        heat_of_combustion=empty["HEAT_OF_COMBUSTION"],
                        ref_temp=empty["REFERENCE_TEMPERATURE"],
                        loc=loc,
                    ))

            for cb_entry in story.combustibles:
                key = cb_entry.get("key", "")
                cb_def = COMBUSTIBLE_LIBRARY.get(key)
                if cb_def is None:
                    continue
                matl = _get_matl(cb_def)
                loc = f"{bld_name}/{story_name}/楼层级"
                entries.append(dict(
                    key=key, name=cb_def.get("name", key), typ="combustible",
                    count=cb_entry.get("count", 1),
                    length=cb_def.get("length", "-"),
                    width=cb_def.get("width", "-"),
                    height=cb_def.get("height", "-"),
                    hrrpua=cb_def.get("hrrpua", "-"),
                    ign_temp=cb_def.get("ignition_temp", "-"),
                    density=matl["DENSITY"], conductivity=matl["CONDUCTIVITY"],
                    specific_heat=matl["SPECIFIC_HEAT"],
                    heat_of_combustion=matl["HEAT_OF_COMBUSTION"],
                    ref_temp=matl["REFERENCE_TEMPERATURE"],
                    loc=loc,
                ))

            for sc_info in story.specialized_components:
                key = sc_info.get("key", "")
                comp = SPECIALIZED_COMPONENTS.get(key)
                if comp is None:
                    continue
                empty = _get_matl({"matl": {}})
                loc = f"{bld_name}/{story_name}/楼层级"
                entries.append(dict(
                    key=key, name=comp.name, typ="specialized_component",
                    count=sc_info.get("count", 1),
                    length=comp.total_length, width=comp.total_width,
                    height=comp.total_height,
                    hrrpua=comp.hrrpua, ign_temp=comp.ignition_temp,
                    density=empty["DENSITY"], conductivity=empty["CONDUCTIVITY"],
                    specific_heat=empty["SPECIFIC_HEAT"],
                    heat_of_combustion=empty["HEAT_OF_COMBUSTION"],
                    ref_temp=empty["REFERENCE_TEMPERATURE"],
                    loc=loc,
                ))

    return entries


def _locations_str(locs: set[str]) -> str:
    return "\n".join(sorted(locs))


def _group_by_key(entries: list[dict]) -> list[dict]:
    """Group entries by (key, typ). Same combustible species => one output row
    with total count and all locations aggregated."""
    groups: dict[tuple[str, str], dict] = {}
    for e in entries:
        gk = (e["key"], e["typ"])
        if gk not in groups:
            groups[gk] = dict(
                name=e["name"], key=e["key"], typ=e["typ"],
                total_count=0,
                length=e["length"], width=e["width"], height=e["height"],
                hrrpua=e["hrrpua"], ign_temp=e["ign_temp"],
                density=e["density"], conductivity=e["conductivity"],
                specific_heat=e["specific_heat"],
                heat_of_combustion=e["heat_of_combustion"],
                ref_temp=e["ref_temp"],
                locations=set(),
            )
        g = groups[gk]
        cnt = e["count"]
        g["total_count"] += cnt if isinstance(cnt, (int, float)) else 0
        g["locations"].add(e["loc"])

    rows: list[dict] = []
    for g in groups.values():
        rows.append({
            "名称": g["name"],
            "英文Key": g["key"],
            "类型": g["typ"],
            "总数量": g["total_count"],
            "长度(m)": g["length"],
            "宽度(m)": g["width"],
            "高度(m)": g["height"],
            "热释放速率(kW/m²)": g["hrrpua"],
            "点燃温度(°C)": g["ign_temp"],
            "密度(kg/m³)": g["density"],
            "导热系数(W/m·K)": g["conductivity"],
            "比热(kJ/kg·K)": g["specific_heat"],
            "燃烧热(kJ/kg)": g["heat_of_combustion"],
            "参考温度(°C)": g["ref_temp"],
            "出现位置": _locations_str(g["locations"]),
        })
    rows.sort(key=lambda r: r["英文Key"])
    return rows


def _make_summary_row(rows: list[dict]) -> dict:
    total_count = sum(
        r["总数量"] for r in rows if isinstance(r["总数量"], (int, float))
    )
    return {
        "名称": f"合计：{len(rows)} 种可燃物, 共 {total_count} 件",
        "英文Key": "", "类型": "", "总数量": "",
        "长度(m)": "", "宽度(m)": "", "高度(m)": "",
        "热释放速率(kW/m²)": "", "点燃温度(°C)": "",
        "密度(kg/m³)": "", "导热系数(W/m·K)": "", "比热(kJ/kg·K)": "",
        "燃烧热(kJ/kg)": "", "参考温度(°C)": "", "出现位置": "",
    }


def export_one_file(facility_data: dict, output_path: str):
    """Export all buildings in a facility JSON to a single Excel sheet.

    Args:
        facility_data: Parsed facility JSON dict (top-level, with "buildings" key).
        output_path:   Path for the output .xlsx file.
    """
    entries: list[dict] = []
    for b in facility_data.get("buildings", []):
        has_template = "stories_template" in b or "length_range" in b
        if has_template:
            params = {
                "length": ParameterEngine.resolve_range(b.get("length_range", [0, 20])),
                "width": ParameterEngine.resolve_range(b.get("width_range", [0, 10])),
                "height": ParameterEngine.resolve_range(b.get("height_range", [0, 5])),
                "stories": int(ParameterEngine.resolve_range(b.get("stories_range", [1, 1, 1]))),
            }
            bg = ParameterEngine.generate(b, params)
            building_list = [bg]
        else:
            building_list = [Building.from_dict(b)]

        for building in building_list:
            building.update_z_offsets()
            bg = BuildingGroup(buildings=[building], name=facility_data.get("name", ""))
            entries.extend(_collect_facility_rows(bg))

    rows = _group_by_key(entries)
    df = pd.DataFrame(rows, columns=LOCATION_COLUMNS)
    if not rows:
        summary = {"名称": "无可燃物数据"}
    else:
        summary = _make_summary_row(rows)
    df = pd.concat([df, pd.DataFrame([summary], columns=LOCATION_COLUMNS)], ignore_index=True)

    sheet_name = facility_data.get("name", "facility")[:31]
    sheet_name = "".join(c for c in sheet_name if c.isprintable() and c not in r'\/[]:*?')

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return len(rows)


def main():
    facilities_dir = Path(__file__).resolve().parent.parent / "facilities"
    json_files = sorted(facilities_dir.glob("*.json"))

    if not json_files:
        print(f"No JSON files found in {facilities_dir}")
        return

    output_path = Path(__file__).resolve().parent.parent / "export" / "all_combustibles.xlsx"
    output_path.parent.mkdir(exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        total_species = 0
        for json_file in json_files:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            entries: list[dict] = []
            for b in data.get("buildings", []):
                has_template = "stories_template" in b or "length_range" in b
                if has_template:
                    params = {
                        "length": ParameterEngine.resolve_range(b.get("length_range", [0, 20])),
                        "width": ParameterEngine.resolve_range(b.get("width_range", [0, 10])),
                        "height": ParameterEngine.resolve_range(b.get("height_range", [0, 5])),
                        "stories": int(ParameterEngine.resolve_range(b.get("stories_range", [1, 1, 1]))),
                    }
                    bg = ParameterEngine.generate(b, params)
                    building_list = [bg]
                else:
                    building_list = [Building.from_dict(b)]

                for building in building_list:
                    building.update_z_offsets()
                    bg = BuildingGroup(buildings=[building], name=data.get("name", ""))
                    entries.extend(_collect_facility_rows(bg))

            rows = _group_by_key(entries)
            df = pd.DataFrame(rows, columns=LOCATION_COLUMNS)
            if rows:
                summary = _make_summary_row(rows)
                df = pd.concat([df, pd.DataFrame([summary], columns=LOCATION_COLUMNS)], ignore_index=True)
            else:
                empty = pd.DataFrame([{"名称": "无可燃物数据"}], columns=LOCATION_COLUMNS)
                df = pd.concat([df, empty], ignore_index=True)

            sheet_name = json_file.stem[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            print(f"  {json_file.stem}: {len(rows)} 种")
            total_species += len(rows)

    print(f"\nExported to {output_path}")
    print(f"Total distinct combustible species across all facilities: {total_species}")


if __name__ == "__main__":
    main()