#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export equivalent-facility combustible assignment to a new xlsx workbook.

Design:
- Each row = ONE placed combustible/component *instance*, carrying the exact
  FDS instance ID (方案乙) and the sub-target building's en/zh names.
- The reported IDs come from the real placement algorithm (per-story seq
  counter; unfitting items dropped; rocket azimuth), so we drive the actual
  FDSGenerator and parse the emitted ``&OBST ... ID=`` lines.
- Output: one sheet per equivalent facility (组织乙).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

from generators.fds_generator import FDSGenerator
from models.building import BuildingGroup
from models.combustibles import SPECIALIZED_COMPONENTS
from models.facility import FacilityManager
from models.materials import COMBUSTIBLE_LIBRARY

SCALES = (
    ("small", 0, "小"),
    ("medium", 1, "中"),
    ("large", 2, "大"),
)

_OBST_ID_RE = re.compile(r"(?<![A-Za-z_])ID='(?P<id>[^']+)'")
_COMPONENT_PART_RE = re.compile(r"^(?P<base>.+?_\d{3})_(?P<pi>\d+)$")


def _build_group(mgr: FacilityManager, facility: str, scale_idx: int) -> list:
    from models.build_arranger import arrange_buildings

    buildings = []
    for building_name in mgr.list_buildings(facility):
        params = mgr.params_for_scale(facility, building_name, scale_idx=scale_idx)
        buildings.append(mgr.load_equivalent(facility, building_name, params))
    if len(buildings) > 1:
        applied = mgr.arrange_buildings_by_layout(facility, buildings)
        if not applied:
            arrange_buildings(buildings, gap=20.0)
    for building_ in buildings:
        building_.update_z_offsets()
    return buildings


def _write_sheet(wb: Workbook, name: str, rows: list[dict]) -> None:
    ws = wb.create_sheet(title=name)
    if not rows:
        ws.append(["无数据"])
        return
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for column_cells in ws.columns:
        header = str(column_cells[0].value or "")
        max_len = max(len(header), *(
            len(str(cell.value)) for cell in column_cells[1:] if cell.value is not None
        ))
        ws.column_dimensions[column_cells[0].column_letter].width = min(max(max_len + 2, 10), 42)


def _make_row(facility, facility_cn, scale, scale_cn, building, story, si,
              typ, key, name, base_id, part_ids) -> dict:
    return {
        "等效设施(英文)": facility,
        "等效设施(中文)": facility_cn,
        "规模": scale,
        "规模中文": scale_cn,
        "子目标建筑(英文)": building.name,
        "子目标建筑(中文)": building.cn_name,
        "楼层": story.name,
        "类型": typ,
        "可燃物Key": key,
        "名称(中文)": name,
        "实例ID": base_id,
        "组件部件ID": part_ids,
    }


def _key_from_base(base: str, bi: int, si: int) -> str:
    tag_fc = f"B{bi}S{si}"
    tag_story = f"B{bi}STORY{si}"
    if tag_fc in base:
        return base.split(tag_fc)[0].rstrip("_")
    if tag_story in base:
        return base.split(tag_story)[0].rstrip("_")
    return base


def _extract_story_rows(text: str, facility, facility_cn, scale, scale_cn,
                        building, story, si: int, bi: int) -> list[dict]:
    rows: list[dict] = []

    def flush_component(parts: list[str]):
        base = parts[0].rsplit("_", 1)[0]
        key = _key_from_base(base, bi, si)
        comp = SPECIALIZED_COMPONENTS.get(key)
        name = comp.name if comp else key
        rows.append(_make_row(
            facility, facility_cn, scale, scale_cn, building, story, si,
            "component", key, name, base, "; ".join(parts),
        ))

    def flush_combustible(obst_id: str):
        key = _key_from_base(obst_id, bi, si)
        definition = COMBUSTIBLE_LIBRARY.get(key, {})
        rows.append(_make_row(
            facility, facility_cn, scale, scale_cn, building, story, si,
            "combustible", key, definition.get("name", key), obst_id, "",
        ))

    pending: list[str] = []  # consecutive component-part ids sharing one base

    for obst_id in _iter_obst_ids(text):
        part_m = _COMPONENT_PART_RE.match(obst_id)
        if part_m and (not pending or part_m.group("base") == pending[0].rsplit("_", 1)[0]):
            pending.append(obst_id)
            continue
        if pending:
            flush_component(pending)
            pending = []
        if part_m:
            pending = [obst_id]
        else:
            flush_combustible(obst_id)
    if pending:
        flush_component(pending)
    return rows


def _iter_obst_ids(text: str):
    """Yield the ID= value of each complete &OBST record in order.

    FDS records span multiple lines; the ID may sit on a continuation line.
    We collect a record from a line beginning with '&OBST' until its closing
    '/', then extract the single ID within it. Lines for &DEVC probes (T_/HF_)
    start with '&DEVC', not '&OBST', and are therefore excluded.
    """
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].lstrip()
        if not stripped.startswith("&OBST"):
            i += 1
            continue
        block = [stripped]
        while i + 1 < n and not lines[i + 1].rstrip().endswith("/"):
            block.append(lines[i + 1])
            i += 1
        if i + 1 < n:
            block.append(lines[i + 1])
        i += 1
        record = "".join(block)
        m = _OBST_ID_RE.search(record)
        if m:
            yield m.group("id")


def export(path: Path) -> int:
    mgr = FacilityManager()
    wb = Workbook()
    wb.remove(wb.active)
    row_count = 0
    for facility in sorted(mgr.facilities):
        if mgr.get_type(facility) != "equivalent":
            continue
        facility_data = mgr.facilities[facility]
        facility_cn = facility_data.get("cn_name", facility_data.get("name", ""))
        sheet_rows: list[dict] = []
        for scale, scale_idx, scale_cn in SCALES:
            buildings = _build_group(mgr, facility, scale_idx)
            gen = FDSGenerator(BuildingGroup(buildings=buildings, name=facility))
            for bi, building in enumerate(buildings):
                for si, story in enumerate(building.stories):
                    lines: list[str] = []
                    gen._generate_combustibles(building, story, si, lines, grid_size=1.0, bi=bi)
                    gen._generate_story_combustibles(building, story, si, lines, grid_size=1.0, bi=bi)
                    text = "".join(lines)
                    sheet_rows.extend(_extract_story_rows(
                        text, facility, facility_cn, scale, scale_cn,
                        building, story, si, bi,
                    ))
        row_count += len(sheet_rows)
        sheet_name = "".join(
            c for c in facility[:31] if c.isprintable() and c not in r'\/[]:*?'
        )
        _write_sheet(wb, sheet_name, sheet_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return row_count


def main() -> int:
    out_path = PROJECT_DIR / "export" / "equivalent_facility_combustible_assignment.xlsx"
    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1]).expanduser()
        if not out_path.is_absolute():
            out_path = PROJECT_DIR / out_path
    n = export(out_path)
    print(out_path)
    print(f"exported {n} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())