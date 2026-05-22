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

COLUMNS = [
    "名称",
    "英文Key",
    "类型",
    "总数量",
    "长度(m)",
    "宽度(m)",
    "高度(m)",
    "热释放速率(kW/m²)",
    "点燃温度(°C)",
    "密度(kg/m³)",
    "导热系数(W/m·K)",
    "比热(kJ/kg·K)",
    "燃烧热(kJ/kg)",
    "参考温度(°C)",
    "出现位置",
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


def _make_row(
    name: str, key: str, typ: str,
    building_name: str, story_name: str, fc_name: str,
    count, length, width, height,
    hrrpua, ign_temp, matl: dict,
    fc_boundary: str = "-", placement: str = "-",
) -> dict:
    return {
        "名称": name,
        "英文Key": key,
        "类型": typ,
        "所在建筑": building_name,
        "所在楼层": story_name,
        "所在分区": fc_name,
        "数量": count,
        "长度(m)": length,
        "宽度(m)": width,
        "高度(m)": height,
        "热释放速率(kW/m²)": hrrpua,
        "点燃温度(°C)": ign_temp,
        "密度(kg/m³)": matl["DENSITY"],
        "导热系数(W/m·K)": matl["CONDUCTIVITY"],
        "比热(kJ/kg·K)": matl["SPECIFIC_HEAT"],
        "燃烧热(kJ/kg)": matl["HEAT_OF_COMBUSTION"],
        "参考温度(°C)": matl["REFERENCE_TEMPERATURE"],
        "分区坐标": fc_boundary,
        "摆放区域": placement,
    }


def _collect_facility_rows(bg: BuildingGroup) -> list[dict]:
    rows: list[dict] = []
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
                    rows.append(_make_row(
                        name=cb_def.get("name", key),
                        key=key,
                        typ="combustible",
                        building_name=bld_name,
                        story_name=story_name,
                        fc_name=fc.name,
                        count=cb_entry.get("count", 1),
                        length=cb_def.get("length", "-"),
                        width=cb_def.get("width", "-"),
                        height=cb_def.get("height", "-"),
                        hrrpua=cb_def.get("hrrpua", "-"),
                        ign_temp=cb_def.get("ignition_temp", "-"),
                        matl=matl,
                        fc_boundary=str(fc.boundary),
                    ))

                for sc_info in fc.specialized_components:
                    key = sc_info.get("key", "")
                    comp = SPECIALIZED_COMPONENTS.get(key)
                    if comp is None:
                        continue
                    empty_matl = _get_matl({"matl": {}})
                    rows.append(_make_row(
                        name=comp.name,
                        key=key,
                        typ="specialized_component",
                        building_name=bld_name,
                        story_name=story_name,
                        fc_name=fc.name,
                        count=sc_info.get("count", 1),
                        length=comp.total_length,
                        width=comp.total_width,
                        height=comp.total_height,
                        hrrpua=comp.hrrpua,
                        ign_temp=comp.ignition_temp,
                        matl=empty_matl,
                        fc_boundary=str(fc.boundary),
                    ))

            for cb_entry in story.combustibles:
                key = cb_entry.get("key", "")
                cb_def = COMBUSTIBLE_LIBRARY.get(key)
                if cb_def is None:
                    continue
                matl = _get_matl(cb_def)
                rows.append(_make_row(
                    name=cb_def.get("name", key),
                    key=key,
                    typ="combustible",
                    building_name=bld_name,
                    story_name=story_name,
                    fc_name="楼层级",
                    count=cb_entry.get("count", 1),
                    length=cb_def.get("length", "-"),
                    width=cb_def.get("width", "-"),
                    height=cb_def.get("height", "-"),
                    hrrpua=cb_def.get("hrrpua", "-"),
                    ign_temp=cb_def.get("ignition_temp", "-"),
                    matl=matl,
                    placement=str(cb_entry.get("boundary", "-")),
                ))

            for sc_info in story.specialized_components:
                key = sc_info.get("key", "")
                comp = SPECIALIZED_COMPONENTS.get(key)
                if comp is None:
                    continue
                empty_matl = _get_matl({"matl": {}})
                rows.append(_make_row(
                    name=comp.name,
                    key=key,
                    typ="specialized_component",
                    building_name=bld_name,
                    story_name=story_name,
                    fc_name="楼层级",
                    count=sc_info.get("count", 1),
                    length=comp.total_length,
                    width=comp.total_width,
                    height=comp.total_height,
                    hrrpua=comp.hrrpua,
                    ign_temp=comp.ignition_temp,
                    matl=empty_matl,
                    placement=str(sc_info.get("boundary", "-")),
                ))

    return rows


def _make_summary_row(rows: list[dict]) -> dict:
    distinct_keys = set(r["英文Key"] for r in rows)
    return {
        "名称": f"合计：{len(rows)} 条记录, {len(distinct_keys)} 种可燃物",
        "英文Key": "", "类型": "", "所在建筑": "", "所在楼层": "", "所在分区": "",
        "数量": "", "长度(m)": "", "宽度(m)": "", "高度(m)": "",
        "热释放速率(kW/m²)": "", "点燃温度(°C)": "",
        "密度(kg/m³)": "", "导热系数(W/m·K)": "", "比热(kJ/kg·K)": "",
        "燃烧热(kJ/kg)": "", "参考温度(°C)": "", "分区坐标": "", "摆放区域": "",
    }


def export_one_file(facility_data: dict, output_path: str):
    """Export all buildings in a facility JSON to a single Excel sheet.

    Args:
        facility_data: Parsed facility JSON dict (top-level, with "buildings" key).
        output_path:   Path for the output .xlsx file.
    """
    rows: list[dict] = []
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
            rows.extend(_collect_facility_rows(bg))

    rows.sort(key=lambda r: r["英文Key"])
    df = pd.DataFrame(rows, columns=COLUMNS)
    if not rows:
        summary = {"名称": "无可燃物数据"}
    else:
        summary = _make_summary_row(rows)
    df = pd.concat([df, pd.DataFrame([summary], columns=COLUMNS)], ignore_index=True)

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
        total_rows = 0
        for json_file in json_files:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            rows: list[dict] = []
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
                    rows.extend(_collect_facility_rows(bg))

            rows.sort(key=lambda r: r["英文Key"])
            df = pd.DataFrame(rows, columns=COLUMNS)
            if rows:
                summary = _make_summary_row(rows)
                df = pd.concat([df, pd.DataFrame([summary], columns=COLUMNS)], ignore_index=True)
            else:
                empty = pd.DataFrame([{"名称": "无可燃物数据"}], columns=COLUMNS)
                df = pd.concat([df, empty], ignore_index=True)

            sheet_name = json_file.stem[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            print(f"  {json_file.stem}: {len(rows)} rows")
            total_rows += len(rows)

    print(f"\nExported to {output_path}")
    print(f"Total combustibles across all facilities: {total_rows}")


if __name__ == "__main__":
    main()