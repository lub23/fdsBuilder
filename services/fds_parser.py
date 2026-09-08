#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Lightweight FDS parser for facility geometry preview.

Extracts only what the 3D preview needs — domain mesh, obstruction boxes,
material (combustible) data and the surface→material mapping.  Unknown
cards are skipped; this is not a full FDS validator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FdsObstacle:
    """Axis-aligned obstruction box (FDS coordinates, metres)."""

    xmin: float
    xmax: float
    ymin: float
    ymax: float
    zmin: float
    zmax: float
    surf_ids: list[str] = field(default_factory=list)


@dataclass
class FdsMaterial:
    """Material properties of interest for preview / combustible listing."""

    id: str
    fuel: str = ""
    combustible: bool = False
    heat_of_combustion: float | None = None
    hrrpuv: float | None = None
    tig: float | None = None


@dataclass
class FdsHeat:
    """Heat source location/size (first &HEAT card only)."""

    xyz: tuple[float, float, float] | None = None
    radius: float | None = None
    width: float | None = None
    depth: float | None = None
    qcc: float | None = None


@dataclass
class FdsScene:
    """Parsed preview data for one FDS file."""

    source: str = ""
    raw_text: str = ""
    domain: tuple[float, ...] | None = None  # XB of the first &MESH (6 values)
    obstacles: list[FdsObstacle] = field(default_factory=list)
    materials: dict[str, FdsMaterial] = field(default_factory=dict)
    surfaces: dict[str, str] = field(default_factory=dict)  # SURF_ID -> MATL_ID
    heat: FdsHeat | None = None

    def combustible(self, obstacle: FdsObstacle) -> bool:
        """True if any surface of the obstacle maps to a combustible material."""
        for surf in obstacle.surf_ids:
            matl_id = self.surfaces.get(surf)
            if matl_id and self.materials.get(matl_id, FdsMaterial(matl_id)).combustible:
                return True
        return False

    def combustible_materials(self) -> list[FdsMaterial]:
        return [m for m in self.materials.values() if m.combustible]


_CARD_RE = re.compile(r"^\s*&([A-Za-z_][A-Za-z0-9_]*)\s*(.*)$")


def _split_top_level(text: str) -> list[str]:
    """Split on commas that are outside quotes and parentheses."""
    parts: list[str] = []
    depth = 0
    quote = ""
    current: list[str] = []
    for ch in text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "'\"":
            quote = ch
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _parse_value(raw: str) -> Any:
    """Parse one FDS value: number, quoted string, or (possibly nested) list."""
    value = raw.strip()
    if value.startswith("(") and value.endswith(")"):
        return [_parse_value(item) for item in _split_top_level(value[1:-1])]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    try:
        return float(value)
    except ValueError:
        return value


def _parse_cards(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Yield (CARD_NAME, {key: parsed_value}) for every card in the file."""
    cards: list[tuple[str, dict[str, Any]]] = []
    card_name: str | None = None
    buffer: list[str] = []

    def _finish() -> None:
        nonlocal card_name, buffer
        if card_name is None:
            return
        tokens = " ".join(buffer)
        params: dict[str, Any] = {}
        current_key: str | None = None
        key_value_parenthesized = False
        for token in _split_top_level(tokens):
            if "=" not in token:
                # Bare continuation item. Two shapes exist:
                #   IJK=97,59,23          -> flat numeric continuation
                #   XB=(box1),(box2)      -> extra parenthesized items
                if current_key is not None:
                    if key_value_parenthesized:
                        if not token.lstrip().startswith("("):
                            continue
                        previous = params[current_key]
                        # A single parenthesized value parses to one flat
                        # item; wrap it before appending further items.
                        if (
                            isinstance(previous, list)
                            and previous
                            and not isinstance(previous[0], list)
                        ):
                            previous = [previous]
                        elif not isinstance(previous, list):
                            previous = [previous]
                        previous.append(_parse_value(token))
                        params[current_key] = previous
                    else:
                        previous = params[current_key]
                        if not isinstance(previous, list):
                            params[current_key] = [previous]
                        params[current_key].append(_parse_value(token))
                continue
            key, _, value = token.partition("=")
            current_key = key.strip().upper()
            key_value_parenthesized = value.strip().startswith("(")
            params[current_key] = _parse_value(value)
        cards.append((card_name, params))
        card_name = None
        buffer = []

    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        terminated = raw.endswith("/")
        if terminated:
            raw = raw[:-1].rstrip()
        match = _CARD_RE.match(raw)
        if match and card_name is None:
            card_name = match.group(1).upper()
            buffer = [match.group(2)]
        elif card_name is not None:
            buffer.append(raw)
        if card_name is not None and terminated:
            _finish()
    _finish()
    return cards


def _as_float_list(value: Any, size: int | None = None) -> list[float] | None:
    if not isinstance(value, list):
        return None
    try:
        numbers = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    if size is not None and len(numbers) != size:
        return None
    return numbers


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _first_string(params: dict[str, Any], prefix: str) -> str | None:
    """Return the first string value whose key equals or starts with *prefix*.

    Older FDS/PyroSim files use indexed keys such as ``MATL_ID(1,1)='fuel'``
    instead of a plain ``MATL_ID='fuel'``.
    """
    direct = params.get(prefix)
    if isinstance(direct, str):
        return direct
    if isinstance(direct, list) and direct:
        return str(direct[0])
    for key, value in params.items():
        if key.startswith(prefix) and (isinstance(value, str) or (isinstance(value, list) and value)):
            return str(value if isinstance(value, str) else value[0])
    return None


def parse_fds_text(text: str, source: str = "") -> FdsScene:
    """Parse FDS text into an :class:`FdsScene` for previewing."""
    scene = FdsScene(source=source, raw_text=text)

    for name, p in _parse_cards(text):
        if name == "MESH" and scene.domain is None:
            box = _as_float_list(p.get("XB"), 6)
            if box:
                scene.domain = tuple(box)
        elif name == "OBST":
            surf_ids = _as_str_list(p.get("SURF_ID"))
            box_list = p.get("XB")
            if isinstance(box_list, list) and box_list and isinstance(box_list[0], list):
                boxes = box_list
            else:
                boxes = [box_list]
            for box in boxes:
                coords = _as_float_list(box, 6)
                if not coords:
                    continue
                xmin, xmax, ymin, ymax, zmin, zmax = coords
                if xmax <= xmin or ymax <= ymin or zmax <= zmin:
                    continue
                scene.obstacles.append(
                    FdsObstacle(xmin, xmax, ymin, ymax, zmin, zmax, surf_ids)
                )
        elif name == "MATL":
            matl_id = str(p.get("ID", ""))
            if not matl_id:
                continue
            comb = p.get("COMB")
            fuel = _first_string(p, "FUEL") or ""
            hoc = p.get("HEAT_OF_COMBUSTION")
            hrrpuv = p.get("HRRPUV")
            tig = p.get("TIG")
            # New-style materials declare FUEL/COMB; older PyroSim-style
            # materials define a reaction with HEAT_OF_COMBUSTION instead.
            if isinstance(comb, (int, float)):
                combustible = float(comb) != 0.0
            else:
                combustible = bool(
                    fuel and fuel.upper() not in ("NONE", "AIR", "NITROGEN")
                ) or (isinstance(hoc, (int, float)) and float(hoc) > 0)
            scene.materials[matl_id] = FdsMaterial(
                id=matl_id,
                fuel=fuel,
                combustible=combustible,
                heat_of_combustion=float(hoc) if isinstance(hoc, (int, float)) else None,
                hrrpuv=float(hrrpuv) if isinstance(hrrpuv, (int, float)) else None,
                tig=float(tig) if isinstance(tig, (int, float)) else None,
            )
        elif name == "SURF":
            surf_id = str(p.get("ID", ""))
            matl_id = _first_string(p, "MATL_ID")
            hrrpuv = p.get("HRRPUA", p.get("HRRPUV"))
            if surf_id and isinstance(hrrpuv, (int, float)) and float(hrrpuv) > 0:
                # PyroSim commonly models combustible inventory directly on a
                # SURF with HRRPUA, without declaring an FDS MATL record. Keep
                # the surface itself as the combustible "material" so those
                # objects are visible in the combustible overview.
                scene.materials[surf_id] = FdsMaterial(
                    id=surf_id,
                    fuel=str(p.get("FUEL", "") or ""),
                    combustible=True,
                    hrrpuv=float(hrrpuv),
                )
                scene.surfaces[surf_id] = surf_id
            elif surf_id and matl_id:
                scene.surfaces[surf_id] = matl_id
        elif name == "HEAT" and scene.heat is None:
            heat = FdsHeat()
            xyz = p.get("XYZ")
            coords = _as_float_list(xyz, 3) if isinstance(xyz, list) else None
            if coords:
                heat.xyz = tuple(coords)  # type: ignore[arg-type]
            for key in ("RADIUS", "WIDTH", "DEPTH", "QCC"):
                value = p.get(key)
                if isinstance(value, (int, float)):
                    setattr(heat, key.lower(), float(value))
            scene.heat = heat

    return scene


def load_fds_scene(path: str | Path) -> FdsScene:
    """Read and parse an FDS file from disk."""
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return parse_fds_text(text, source=str(file_path))


def resolve_reference_fds(facility_name: str) -> Path | None:
    """Locate a reference FDS file for a facility.

    Preference order:
    1. ``facilities/{code}.fds`` — the committed preview reference.
    2. the first ``*.fds`` under ``agent_damage/cases/{code}/`` (dev trees).
    """
    from models.facility import facilities_dir

    candidate = Path(facilities_dir()) / f"{facility_name}.fds"
    if candidate.is_file():
        return candidate
    cases_dir = Path("agent_damage") / "cases" / facility_name
    matches = sorted(cases_dir.glob("*.fds")) if cases_dir.is_dir() else []
    return matches[0] if matches else None


def combustible_summary(scene: FdsScene) -> list[dict]:
    """Aggregate the combustible load per material, ordered by volume.

    Each row: material id, fuel, heat of combustion, HRRPUV, number of
    obstruction boxes and their total volume (m³).
    """
    per_material: dict[str, dict] = {}
    for o in scene.obstacles:
        matl_id = None
        for surf in o.surf_ids:
            candidate_id = scene.surfaces.get(surf)
            if candidate_id and scene.materials.get(candidate_id, FdsMaterial(candidate_id)).combustible:
                matl_id = candidate_id
                break
        if matl_id is None:
            continue
        entry = per_material.setdefault(matl_id, {"boxes": 0, "volume": 0.0})
        entry["boxes"] += 1
        entry["volume"] += (o.xmax - o.xmin) * (o.ymax - o.ymin) * (o.zmax - o.zmin)

    rows: list[dict] = []
    for matl_id, agg in per_material.items():
        material = scene.materials.get(matl_id, FdsMaterial(matl_id))
        rows.append({
            "material": matl_id,
            "fuel": material.fuel,
            "heat_of_combustion": material.heat_of_combustion,
            "hrrpuv": material.hrrpuv,
            "boxes": agg["boxes"],
            "volume": agg["volume"],
        })
    rows.sort(key=lambda row: -row["volume"])
    return rows
