"""Build experimental Dk regression data from raw FDS and summary CSV files."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping

import numpy as np
import pandas as pd


DK_THRESHOLDS: tuple[float, float, float] = (0.04, 0.10, 0.40)
DK_GRADE_NAMES: tuple[str, str, str, str] = (
    "未达到破坏等级/基本完好",
    "轻微破坏",
    "中等破坏",
    "严重破坏",
)

COMBUSTIBLE_CATEGORIES: tuple[str, ...] = (
    "wood_paper",
    "textile",
    "plastic",
    "fuel_oil",
    "electronics",
    "chemical",
    "metal",
    "composite",
)

WALL_KEYS: tuple[str, ...] = ("x_max", "y_min", "x_min", "y_max")
WALL_ANGLES: Mapping[str, float] = {
    "x_max": 0.0,
    "y_min": 90.0,
    "x_min": 180.0,
    "y_max": 270.0,
}

EXPERIMENT_FEATURE_COLUMNS: tuple[str, ...] = (
    "facility_index",
    "domain_length",
    "domain_width",
    "domain_height",
    "domain_floor_area",
    "domain_volume",
    "mesh_count",
    "mesh_cell_count",
    "mesh_cell_density",
    "obst_count",
    "obst_total_volume",
    "obst_volume_ratio",
    "vent_count",
    "vent_total_area",
    "open_vent_count",
    "open_vent_area",
    "door_window_count",
    "door_count",
    "window_count",
    "door_window_area",
    "door_window_area_ratio",
    "surface_count",
    "material_count",
    "device_count",
    "temperature_device_count",
    "radiative_flux_device_count",
    "asset_sensor_count",
    "asset_density",
    "asset_bbox_x",
    "asset_bbox_y",
    "asset_bbox_z",
    "asset_mean_z",
    "asset_std_z",
    "wall_area_x_max",
    "wall_area_y_min",
    "wall_area_x_min",
    "wall_area_y_max",
    "wall_open_vent_count_x_max",
    "wall_open_vent_count_y_min",
    "wall_open_vent_count_x_min",
    "wall_open_vent_count_y_max",
    "wall_open_vent_area_x_max",
    "wall_open_vent_area_y_min",
    "wall_open_vent_area_x_min",
    "wall_open_vent_area_y_max",
    "wall_open_vent_ratio_x_max",
    "wall_open_vent_ratio_y_min",
    "wall_open_vent_ratio_x_min",
    "wall_open_vent_ratio_y_max",
    "wall_radiation_vent_count_x_max",
    "wall_radiation_vent_count_y_min",
    "wall_radiation_vent_count_x_min",
    "wall_radiation_vent_count_y_max",
    "wall_radiation_vent_area_x_max",
    "wall_radiation_vent_area_y_min",
    "wall_radiation_vent_area_x_min",
    "wall_radiation_vent_area_y_max",
    "wall_radiation_vent_ratio_x_max",
    "wall_radiation_vent_ratio_y_min",
    "wall_radiation_vent_ratio_x_min",
    "wall_radiation_vent_ratio_y_max",
    "wall_door_window_count_x_max",
    "wall_door_window_count_y_min",
    "wall_door_window_count_x_min",
    "wall_door_window_count_y_max",
    "wall_door_window_area_x_max",
    "wall_door_window_area_y_min",
    "wall_door_window_area_x_min",
    "wall_door_window_area_y_max",
    "wall_door_window_ratio_x_max",
    "wall_door_window_ratio_y_min",
    "wall_door_window_ratio_x_min",
    "wall_door_window_ratio_y_max",
    "wall_asset_front_count_x_max",
    "wall_asset_front_count_y_min",
    "wall_asset_front_count_x_min",
    "wall_asset_front_count_y_max",
    "wall_asset_front_ratio_x_max",
    "wall_asset_front_ratio_y_min",
    "wall_asset_front_ratio_x_min",
    "wall_asset_front_ratio_y_max",
    "heat_flux_kw_m2",
    "heat_flux_log10",
    "heat_flux_squared",
    "heat_azimuth_deg",
    "heat_azimuth_sin",
    "heat_azimuth_cos",
    "heat_azimuth_is_0",
    "heat_azimuth_is_90",
    "heat_azimuth_is_180",
    "heat_azimuth_is_270",
    "heat_elevation_deg",
    "heat_elevation_sin",
    "heat_elevation_cos",
    "heat_elevation_is_0",
    "heat_elevation_is_30",
    "heat_elevation_is_45",
    "heat_elevation_is_60",
    "radiation_duration_ms",
    "radiation_duration_s",
    "duration_is_1360ms",
    "duration_is_2100ms",
    "duration_is_7500ms",
    "case_t_end_s",
    "heat_dose_kw_s_m2",
    "heat_dose_log10",
    "incident_wall_code",
    "incident_open_vent_count",
    "incident_open_vent_area",
    "incident_open_vent_ratio",
    "incident_radiation_vent_count",
    "incident_radiation_vent_area",
    "incident_radiation_vent_ratio",
    "incident_door_window_count",
    "incident_door_window_area",
    "incident_door_window_ratio",
    "incident_total_opening_count",
    "incident_total_opening_area",
    "incident_total_opening_ratio",
    "incident_has_opening",
    "incident_windowless_wall",
    "incident_asset_front_count",
    "incident_asset_front_ratio",
    "incident_opening_heat_dose",
    "incident_opening_heat_flux",
    "incident_radiation_heat_dose",
    "no_opening_heat_flux",
    "wood_paper_count",
    "textile_count",
    "plastic_count",
    "fuel_oil_count",
    "electronics_count",
    "chemical_count",
    "metal_count",
    "composite_count",
    "wood_paper_ratio",
    "textile_ratio",
    "plastic_ratio",
    "fuel_oil_ratio",
    "electronics_ratio",
    "chemical_ratio",
    "metal_ratio",
    "composite_ratio",
)

COMPACT_EXPERIMENT_FEATURE_COLUMNS: tuple[str, ...] = (
    "heat_flux_log10",
    "duration_s",
    "heat_dose_log10",
    "elevation_sin",
    "azimuth_sin",
    "azimuth_cos",
    "facility_type_index",
    "log_floor_area",
    "log_volume",
    "height",
    "incident_wall_area_log",
    "incident_door_window_count",
    "incident_door_window_ratio",
    "incident_total_opening_ratio",
    "combustible_target_density",
    "incident_combustible_target_ratio",
)

_CASE_RE = re.compile(
    r"^(?P<facility>.+?)_q(?P<q>-?\d+(?:\.\d+)?)"
    r"_a(?P<a>-?\d+(?:\.\d+)?)"
    r"_e(?P<e>-?\d+(?:\.\d+)?)"
    r"_d(?P<d>-?\d+(?:\.\d+)?)"
    r"_t(?P<t>-?\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)

_RECORD_RE = re.compile(r"&(?P<kind>[A-Z0-9_]+)\b(?P<body>.*?)/", re.IGNORECASE | re.DOTALL)
_FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?")
_KEYWORDS: Mapping[str, tuple[str, ...]] = {
    "wood_paper": (
        "wood",
        "paper",
        "cardboard",
        "pallet",
        "mu_",
        "_mu",
        "zhi",
        "zhi_xiang",
        "wen_jian",
        "dang_an",
        "bao_zhuang",
    ),
    "textile": ("textile", "cloth", "fabric", "sha_fa", "sofa", "_bu", "bu_"),
    "plastic": ("plastic", "pvc", "poly", "su_liao", "suliao"),
    "fuel_oil": (
        "fuel",
        "oil",
        "diesel",
        "gasoline",
        "methane",
        "run_hua",
        "you_pin",
        "you_tong",
        "lubric",
    ),
    "electronics": (
        "electric",
        "electronic",
        "computer",
        "server",
        "cable",
        "dian_",
        "dianqi",
        "dian_lan",
        "dian_nao",
    ),
    "chemical": (
        "chem",
        "paint",
        "solvent",
        "clean",
        "qing_xi",
        "tu_liao",
        "hua_xue",
    ),
    "metal": ("metal", "steel", "aluminum", "aluminium", "jin_shu", "gang", "tie"),
    "composite": ("composite", "carbon", "foam", "rubber", "fu_he", "kevlar"),
}
_DOOR_KEYWORDS: tuple[str, ...] = ("door", "ifcdoor", "门", "men")
_WINDOW_KEYWORDS: tuple[str, ...] = ("window", "ifcwindow", "窗", "chuang")


@dataclass(frozen=True)
class CaseParams:
    facility: str
    heat_flux_kw_m2: float
    heat_azimuth_deg: float
    heat_elevation_deg: float
    radiation_duration_ms: float
    case_t_end_s: float


def dk_to_grade(dk: float, thresholds: tuple[float, float, float] = DK_THRESHOLDS) -> int:
    """Map a Dk value to 0..3 damage grade using fixed engineering thresholds."""
    value = float(np.clip(dk, 0.0, 1.0))
    if value < thresholds[0]:
        return 0
    if value < thresholds[1]:
        return 1
    if value < thresholds[2]:
        return 2
    return 3


def grade_name(grade: int) -> str:
    return DK_GRADE_NAMES[int(grade)]


def parse_case_name(case_name: str) -> CaseParams:
    match = _CASE_RE.match(str(case_name).strip())
    if not match:
        raise ValueError(f"Cannot parse case name: {case_name!r}")
    return CaseParams(
        facility=match.group("facility"),
        heat_flux_kw_m2=float(match.group("q")),
        heat_azimuth_deg=float(match.group("a")),
        heat_elevation_deg=float(match.group("e")),
        radiation_duration_ms=float(match.group("d")),
        case_t_end_s=float(match.group("t")),
    )


def case_condition_features(case: CaseParams) -> Dict[str, float]:
    azimuth_rad = math.radians(case.heat_azimuth_deg)
    elevation_rad = math.radians(case.heat_elevation_deg)
    duration_s = case.radiation_duration_ms / 1000.0
    heat_flux = max(case.heat_flux_kw_m2, 0.0)
    heat_dose = heat_flux * duration_s
    return {
        "heat_flux_kw_m2": case.heat_flux_kw_m2,
        "heat_flux_log10": math.log10(heat_flux + 1.0),
        "heat_flux_squared": heat_flux * heat_flux,
        "heat_azimuth_deg": case.heat_azimuth_deg,
        "heat_azimuth_sin": math.sin(azimuth_rad),
        "heat_azimuth_cos": math.cos(azimuth_rad),
        "heat_azimuth_is_0": float(abs((case.heat_azimuth_deg % 360.0) - 0.0) < 1e-6),
        "heat_azimuth_is_90": float(abs((case.heat_azimuth_deg % 360.0) - 90.0) < 1e-6),
        "heat_azimuth_is_180": float(abs((case.heat_azimuth_deg % 360.0) - 180.0) < 1e-6),
        "heat_azimuth_is_270": float(abs((case.heat_azimuth_deg % 360.0) - 270.0) < 1e-6),
        "heat_elevation_deg": case.heat_elevation_deg,
        "heat_elevation_sin": math.sin(elevation_rad),
        "heat_elevation_cos": math.cos(elevation_rad),
        "heat_elevation_is_0": float(abs(case.heat_elevation_deg - 0.0) < 1e-6),
        "heat_elevation_is_30": float(abs(case.heat_elevation_deg - 30.0) < 1e-6),
        "heat_elevation_is_45": float(abs(case.heat_elevation_deg - 45.0) < 1e-6),
        "heat_elevation_is_60": float(abs(case.heat_elevation_deg - 60.0) < 1e-6),
        "radiation_duration_ms": case.radiation_duration_ms,
        "radiation_duration_s": duration_s,
        "duration_is_1360ms": float(abs(case.radiation_duration_ms - 1360.0) < 1e-6),
        "duration_is_2100ms": float(abs(case.radiation_duration_ms - 2100.0) < 1e-6),
        "duration_is_7500ms": float(abs(case.radiation_duration_ms - 7500.0) < 1e-6),
        "case_t_end_s": case.case_t_end_s,
        "heat_dose_kw_s_m2": heat_dose,
        "heat_dose_log10": math.log10(heat_dose + 1.0),
    }


def _smallest_angle_diff(a: float, b: float) -> float:
    diff = abs((float(a) - float(b)) % 360.0)
    complement = 360.0 - diff
    return diff if diff <= complement else complement


def _wall_weight(wall: str, azimuth: float) -> float:
    diff = _smallest_angle_diff(WALL_ANGLES[wall], azimuth)
    return max(0.0, math.cos(math.radians(diff)))


def _incident_wall(azimuth: float) -> str:
    return min(WALL_KEYS, key=lambda wall: _smallest_angle_diff(WALL_ANGLES[wall], azimuth))


def _weighted_wall_feature(features: Mapping[str, float], prefix: str, azimuth: float) -> float:
    return float(
        sum(
            _wall_weight(wall, azimuth) * float(features.get(f"{prefix}_{wall}", 0.0))
            for wall in WALL_KEYS
        )
    )


def directional_case_features(
    fds_features: Mapping[str, float],
    case: CaseParams,
) -> Dict[str, float]:
    """Create case-specific exterior-wall exposure features from FDS wall metrics."""
    azimuth = case.heat_azimuth_deg
    wall = _incident_wall(azimuth)
    wall_code = float(WALL_KEYS.index(wall))
    open_count = _weighted_wall_feature(fds_features, "wall_open_vent_count", azimuth)
    open_area = _weighted_wall_feature(fds_features, "wall_open_vent_area", azimuth)
    open_ratio = _weighted_wall_feature(fds_features, "wall_open_vent_ratio", azimuth)
    radiation_count = _weighted_wall_feature(fds_features, "wall_radiation_vent_count", azimuth)
    radiation_area = _weighted_wall_feature(fds_features, "wall_radiation_vent_area", azimuth)
    radiation_ratio = _weighted_wall_feature(fds_features, "wall_radiation_vent_ratio", azimuth)
    door_window_count = _weighted_wall_feature(fds_features, "wall_door_window_count", azimuth)
    door_window_area = _weighted_wall_feature(fds_features, "wall_door_window_area", azimuth)
    door_window_ratio = _weighted_wall_feature(fds_features, "wall_door_window_ratio", azimuth)
    asset_front_count = _weighted_wall_feature(fds_features, "wall_asset_front_count", azimuth)
    asset_front_ratio = _weighted_wall_feature(fds_features, "wall_asset_front_ratio", azimuth)
    total_count = open_count + door_window_count
    total_area = open_area + door_window_area
    open_ratio = min(open_ratio, 1.0)
    radiation_ratio = min(radiation_ratio, 1.0)
    door_window_ratio = min(door_window_ratio, 1.0)
    total_ratio = min(open_ratio + door_window_ratio, 1.0)
    has_opening = float(total_area > 1e-9 or total_count > 1e-9)
    heat_flux = max(case.heat_flux_kw_m2, 0.0)
    heat_dose = heat_flux * (case.radiation_duration_ms / 1000.0)
    return {
        "incident_wall_code": wall_code,
        "incident_open_vent_count": open_count,
        "incident_open_vent_area": open_area,
        "incident_open_vent_ratio": open_ratio,
        "incident_radiation_vent_count": radiation_count,
        "incident_radiation_vent_area": radiation_area,
        "incident_radiation_vent_ratio": radiation_ratio,
        "incident_door_window_count": door_window_count,
        "incident_door_window_area": door_window_area,
        "incident_door_window_ratio": door_window_ratio,
        "incident_total_opening_count": total_count,
        "incident_total_opening_area": total_area,
        "incident_total_opening_ratio": total_ratio,
        "incident_has_opening": has_opening,
        "incident_windowless_wall": 1.0 - has_opening,
        "incident_asset_front_count": asset_front_count,
        "incident_asset_front_ratio": asset_front_ratio,
        "incident_opening_heat_dose": total_ratio * heat_dose,
        "incident_opening_heat_flux": total_ratio * heat_flux,
        "incident_radiation_heat_dose": radiation_ratio * heat_dose,
        "no_opening_heat_flux": (1.0 - min(total_ratio, 1.0)) * heat_flux,
    }


def compact_experimental_features(features: Mapping[str, float]) -> Dict[str, float]:
    """Build the compact, presentation-facing 20-dim experimental feature set."""
    floor_area = max(float(features.get("domain_floor_area", 0.0)), 0.0)
    volume = max(float(features.get("domain_volume", 0.0)), 0.0)
    azimuth = float(features.get("heat_azimuth_deg", 0.0))
    incident_wall_area = max(_weighted_wall_feature(features, "wall_area", azimuth), 0.0)
    return {
        "heat_flux_log10": float(features.get("heat_flux_log10", 0.0)),
        "duration_s": float(features.get("radiation_duration_s", 0.0)),
        "heat_dose_log10": float(features.get("heat_dose_log10", 0.0)),
        "elevation_sin": float(features.get("heat_elevation_sin", 0.0)),
        "azimuth_sin": float(features.get("heat_azimuth_sin", 0.0)),
        "azimuth_cos": float(features.get("heat_azimuth_cos", 0.0)),
        "facility_type_index": float(features.get("facility_index", 0.0)),
        "log_floor_area": math.log1p(floor_area),
        "log_volume": math.log1p(volume),
        "height": float(features.get("domain_height", 0.0)),
        "incident_wall_area_log": math.log1p(incident_wall_area),
        "incident_door_window_count": float(features.get("incident_door_window_count", 0.0)),
        "incident_door_window_ratio": float(features.get("incident_door_window_ratio", 0.0)),
        "incident_total_opening_ratio": float(features.get("incident_total_opening_ratio", 0.0)),
        "combustible_target_density": float(features.get("asset_density", 0.0)),
        "incident_combustible_target_ratio": float(
            features.get("incident_asset_front_ratio", 0.0)
        ),
    }


def _extract_value(body: str, key: str) -> str | None:
    match = re.search(
        rf"\b{re.escape(key)}\s*=\s*(.*?)(?=,\s*[A-Z][A-Z0-9_]*\s*=|$)",
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return match.group(1).strip().rstrip(",")


def _numbers(body: str, key: str) -> list[float]:
    value = _extract_value(body, key)
    if value is None:
        return []
    return [float(x) for x in _FLOAT_RE.findall(value)]


def _string_value(body: str, key: str) -> str:
    value = _extract_value(body, key)
    if value is None:
        return ""
    return value.strip().strip("'\"")


def _record_text(body: str) -> str:
    values = []
    for key in ("ID", "SURF_ID", "MATL_ID", "FUEL", "FYI"):
        values.append(_string_value(body, key))
    return " ".join(values).lower()


def _count_categories(texts: Iterable[str]) -> Dict[str, float]:
    counts = {name: 0.0 for name in COMBUSTIBLE_CATEGORIES}
    for raw_text in texts:
        text = raw_text.lower()
        for category, keywords in _KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                counts[category] += 1.0
    return counts


def _volume_from_xb(xb: list[float]) -> float:
    if len(xb) < 6:
        return 0.0
    dx = max(0.0, xb[1] - xb[0])
    dy = max(0.0, xb[3] - xb[2])
    dz = max(0.0, xb[5] - xb[4])
    return dx * dy * dz


def _area_from_xb(xb: list[float]) -> float:
    if len(xb) < 6:
        return 0.0
    spans = [abs(xb[1] - xb[0]), abs(xb[3] - xb[2]), abs(xb[5] - xb[4])]
    positive = [span for span in spans if span > 0]
    if len(positive) >= 2:
        return positive[0] * positive[1]
    return 0.0


def _face_area_from_xb(xb: list[float]) -> float:
    if len(xb) < 6:
        return 0.0
    spans = sorted((abs(xb[1] - xb[0]), abs(xb[3] - xb[2]), abs(xb[5] - xb[4])), reverse=True)
    return spans[0] * spans[1] if len(spans) >= 2 else 0.0


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(keyword in low for keyword in keywords)


def _is_door_window(text: str) -> bool:
    return _contains_any(text, _DOOR_KEYWORDS) or _contains_any(text, _WINDOW_KEYWORDS)


def _is_door(text: str) -> bool:
    return _contains_any(text, _DOOR_KEYWORDS)


def _is_window(text: str) -> bool:
    return _contains_any(text, _WINDOW_KEYWORDS)


def _wall_from_xb(
    xb: list[float],
    domain_mins: np.ndarray,
    domain_maxs: np.ndarray,
    tolerance: float,
) -> str | None:
    if len(xb) < 6:
        return None
    spans = (abs(xb[1] - xb[0]), abs(xb[3] - xb[2]), abs(xb[5] - xb[4]))
    thin_tolerance = max(0.25, tolerance)
    candidates = {
        "x_min": min(abs(xb[0] - domain_mins[0]), abs(xb[1] - domain_mins[0]))
        if spans[0] <= thin_tolerance
        else float("inf"),
        "x_max": min(abs(xb[0] - domain_maxs[0]), abs(xb[1] - domain_maxs[0]))
        if spans[0] <= thin_tolerance
        else float("inf"),
        "y_min": min(abs(xb[2] - domain_mins[1]), abs(xb[3] - domain_mins[1]))
        if spans[1] <= thin_tolerance
        else float("inf"),
        "y_max": min(abs(xb[2] - domain_maxs[1]), abs(xb[3] - domain_maxs[1]))
        if spans[1] <= thin_tolerance
        else float("inf"),
    }
    wall, distance = min(candidates.items(), key=lambda item: item[1])
    if distance <= tolerance:
        return wall
    return None


def _wall_areas(dims: np.ndarray) -> Dict[str, float]:
    length, width, height = float(dims[0]), float(dims[1]), float(dims[2])
    return {
        "x_max": width * height,
        "x_min": width * height,
        "y_min": length * height,
        "y_max": length * height,
    }


def parse_fds_features(path: Path) -> Dict[str, float]:
    """Extract coarse building and combustible descriptors from an FDS file."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    records = [(m.group("kind").upper(), m.group("body")) for m in _RECORD_RE.finditer(text)]

    mesh_xbs: list[list[float]] = []
    mesh_cells = 0.0
    obst_volume = 0.0
    vent_area = 0.0
    open_vent_area = 0.0
    open_vent_count = 0.0
    door_window_area = 0.0
    door_window_count = 0.0
    door_count = 0.0
    window_count = 0.0
    xyzs: list[list[float]] = []
    category_texts: list[str] = []
    vent_wall_records: list[tuple[list[float], str, float]] = []
    door_window_records: list[tuple[list[float], str, float]] = []
    counts = {
        "mesh_count": 0.0,
        "obst_count": 0.0,
        "vent_count": 0.0,
        "surface_count": 0.0,
        "material_count": 0.0,
        "device_count": 0.0,
        "temperature_device_count": 0.0,
        "radiative_flux_device_count": 0.0,
    }
    asset_ids: set[str] = set()
    asset_positions: dict[str, list[float]] = {}

    for kind, body in records:
        if kind == "MESH":
            counts["mesh_count"] += 1.0
            xb = _numbers(body, "XB")
            if len(xb) >= 6:
                mesh_xbs.append(xb[:6])
            ijk = _numbers(body, "IJK")
            if len(ijk) >= 3:
                mesh_cells += max(0.0, ijk[0] * ijk[1] * ijk[2])
        elif kind == "OBST":
            counts["obst_count"] += 1.0
            xb = _numbers(body, "XB")
            text_value = _record_text(body)
            obst_volume += _volume_from_xb(xb)
            if _is_door_window(text_value):
                area = _face_area_from_xb(xb)
                door_window_count += 1.0
                door_window_area += area
                door_count += float(_is_door(text_value))
                window_count += float(_is_window(text_value))
                door_window_records.append((xb, text_value, area))
            category_texts.append(text_value)
        elif kind == "VENT":
            counts["vent_count"] += 1.0
            xb = _numbers(body, "XB")
            area = _area_from_xb(xb)
            surf_id = _string_value(body, "SURF_ID")
            vent_area += area
            if surf_id.upper() == "OPEN":
                open_vent_count += 1.0
                open_vent_area += area
            vent_wall_records.append((xb, surf_id, area))
            category_texts.append(_record_text(body))
        elif kind == "SURF":
            counts["surface_count"] += 1.0
            category_texts.append(_record_text(body))
        elif kind in {"MATL", "REAC"}:
            if kind == "MATL":
                counts["material_count"] += 1.0
            category_texts.append(_record_text(body))
        elif kind == "DEVC":
            counts["device_count"] += 1.0
            quantity = _string_value(body, "QUANTITY").upper()
            if quantity == "TEMPERATURE":
                counts["temperature_device_count"] += 1.0
            if "RADIATIVE HEAT FLUX" in quantity:
                counts["radiative_flux_device_count"] += 1.0
            xyz = _numbers(body, "XYZ")
            if len(xyz) >= 3:
                xyzs.append(xyz[:3])
            dev_id = _string_value(body, "ID")
            asset_id = re.sub(r"^(TC|RHFG)_", "", dev_id, flags=re.IGNORECASE)
            if asset_id:
                asset_ids.add(asset_id)
                if len(xyz) >= 3 and asset_id not in asset_positions:
                    asset_positions[asset_id] = xyz[:3]
            category_texts.append(dev_id)

    if mesh_xbs:
        mins = np.min(np.array([[xb[0], xb[2], xb[4]] for xb in mesh_xbs], dtype=float), axis=0)
        maxs = np.max(np.array([[xb[1], xb[3], xb[5]] for xb in mesh_xbs], dtype=float), axis=0)
        dims = np.maximum(maxs - mins, 0.0)
    else:
        dims = np.zeros(3, dtype=float)

    floor_area = float(dims[0] * dims[1])
    volume = float(floor_area * dims[2])
    wall_areas = _wall_areas(dims)
    if mesh_xbs:
        domain_mins = np.min(
            np.array([[xb[0], xb[2], xb[4]] for xb in mesh_xbs], dtype=float),
            axis=0,
        )
        domain_maxs = np.max(
            np.array([[xb[1], xb[3], xb[5]] for xb in mesh_xbs], dtype=float),
            axis=0,
        )
    else:
        domain_mins = np.zeros(3, dtype=float)
        domain_maxs = np.zeros(3, dtype=float)
    exterior_tolerance = max(0.5, 0.02 * max(float(dims[0]), float(dims[1]), 1.0))
    wall_open_counts = {wall: 0.0 for wall in WALL_KEYS}
    wall_open_areas = {wall: 0.0 for wall in WALL_KEYS}
    wall_radiation_counts = {wall: 0.0 for wall in WALL_KEYS}
    wall_radiation_areas = {wall: 0.0 for wall in WALL_KEYS}
    wall_door_window_counts = {wall: 0.0 for wall in WALL_KEYS}
    wall_door_window_areas = {wall: 0.0 for wall in WALL_KEYS}
    wall_asset_front_counts = {wall: 0.0 for wall in WALL_KEYS}

    for xb, surf_id, area in vent_wall_records:
        wall = _wall_from_xb(xb, domain_mins, domain_maxs, exterior_tolerance)
        if wall is None:
            continue
        surf_upper = surf_id.upper()
        if surf_upper == "OPEN":
            wall_open_counts[wall] += 1.0
            wall_open_areas[wall] += area
        if "RADIATION" in surf_upper:
            wall_radiation_counts[wall] += 1.0
            wall_radiation_areas[wall] += area

    for xb, _, area in door_window_records:
        wall = _wall_from_xb(xb, domain_mins, domain_maxs, exterior_tolerance)
        if wall is None:
            continue
        wall_door_window_counts[wall] += 1.0
        wall_door_window_areas[wall] += area

    asset_position_values = np.array(list(asset_positions.values()), dtype=float)
    if len(asset_position_values):
        x_front_band = max(2.0, 0.10 * float(dims[0]))
        y_front_band = max(2.0, 0.10 * float(dims[1]))
        wall_asset_front_counts["x_max"] = float(
            np.sum((domain_maxs[0] - asset_position_values[:, 0]) <= x_front_band)
        )
        wall_asset_front_counts["x_min"] = float(
            np.sum((asset_position_values[:, 0] - domain_mins[0]) <= x_front_band)
        )
        wall_asset_front_counts["y_min"] = float(
            np.sum((asset_position_values[:, 1] - domain_mins[1]) <= y_front_band)
        )
        wall_asset_front_counts["y_max"] = float(
            np.sum((domain_maxs[1] - asset_position_values[:, 1]) <= y_front_band)
        )
    xyz_arr = np.array(xyzs, dtype=float) if xyzs else np.zeros((0, 3), dtype=float)
    if len(xyz_arr):
        bbox = np.maximum(xyz_arr.max(axis=0) - xyz_arr.min(axis=0), 0.0)
        mean_z = float(xyz_arr[:, 2].mean())
        std_z = float(xyz_arr[:, 2].std())
    else:
        bbox = np.zeros(3, dtype=float)
        mean_z = 0.0
        std_z = 0.0

    category_counts = _count_categories(category_texts)
    category_denominator = max(1.0, counts["obst_count"] + len(asset_ids))
    features: Dict[str, float] = {
        "domain_length": float(dims[0]),
        "domain_width": float(dims[1]),
        "domain_height": float(dims[2]),
        "domain_floor_area": floor_area,
        "domain_volume": volume,
        "mesh_count": counts["mesh_count"],
        "mesh_cell_count": float(mesh_cells),
        "mesh_cell_density": float(mesh_cells / max(volume, 1.0)),
        "obst_count": counts["obst_count"],
        "obst_total_volume": float(obst_volume),
        "obst_volume_ratio": float(obst_volume / max(volume, 1.0)),
        "vent_count": counts["vent_count"],
        "vent_total_area": float(vent_area),
        "open_vent_count": float(open_vent_count),
        "open_vent_area": float(open_vent_area),
        "door_window_count": float(door_window_count),
        "door_count": float(door_count),
        "window_count": float(window_count),
        "door_window_area": float(door_window_area),
        "door_window_area_ratio": float(door_window_area / max(floor_area, 1.0)),
        "surface_count": counts["surface_count"],
        "material_count": counts["material_count"],
        "device_count": counts["device_count"],
        "temperature_device_count": counts["temperature_device_count"],
        "radiative_flux_device_count": counts["radiative_flux_device_count"],
        "asset_sensor_count": float(len(asset_ids)),
        "asset_density": float(len(asset_ids) / max(floor_area, 1.0)),
        "asset_bbox_x": float(bbox[0]),
        "asset_bbox_y": float(bbox[1]),
        "asset_bbox_z": float(bbox[2]),
        "asset_mean_z": mean_z,
        "asset_std_z": std_z,
    }
    for wall in WALL_KEYS:
        wall_area = max(wall_areas[wall], 1.0)
        features[f"wall_area_{wall}"] = float(wall_areas[wall])
        features[f"wall_open_vent_count_{wall}"] = wall_open_counts[wall]
        features[f"wall_open_vent_area_{wall}"] = wall_open_areas[wall]
        features[f"wall_open_vent_ratio_{wall}"] = wall_open_areas[wall] / wall_area
        features[f"wall_radiation_vent_count_{wall}"] = wall_radiation_counts[wall]
        features[f"wall_radiation_vent_area_{wall}"] = wall_radiation_areas[wall]
        features[f"wall_radiation_vent_ratio_{wall}"] = wall_radiation_areas[wall] / wall_area
        features[f"wall_door_window_count_{wall}"] = wall_door_window_counts[wall]
        features[f"wall_door_window_area_{wall}"] = wall_door_window_areas[wall]
        features[f"wall_door_window_ratio_{wall}"] = wall_door_window_areas[wall] / wall_area
        features[f"wall_asset_front_count_{wall}"] = wall_asset_front_counts[wall]
        features[f"wall_asset_front_ratio_{wall}"] = wall_asset_front_counts[wall] / max(
            float(len(asset_positions)), 1.0
        )
    for category in COMBUSTIBLE_CATEGORIES:
        count = category_counts[category]
        features[f"{category}_count"] = count
        features[f"{category}_ratio"] = float(count / category_denominator)
    return features


def _case_columns(df: pd.DataFrame) -> tuple[str, str | None]:
    case_col = "case_name" if "case_name" in df.columns else "case" if "case" in df.columns else None
    if case_col is None:
        raise ValueError("CSV summary does not contain case_name or case")
    grade_col = next((c for c in ("damage_grade", "damage_level", "Dk_level") if c in df.columns), None)
    return case_col, grade_col


def _fds_lookup(raw_dir: Path) -> Dict[str, Path]:
    paths = sorted(Path(raw_dir).glob("*.fds"))
    return {path.stem.lower(): path for path in paths}


def _resolve_fds(case_name: str, lookup: Mapping[str, Path]) -> Path | None:
    key = case_name.lower()
    if key in lookup:
        return lookup[key]
    try:
        facility = parse_case_name(case_name).facility.lower()
    except ValueError:
        return None
    prefix = facility + "_q"
    candidates = [path for stem, path in lookup.items() if stem.startswith(prefix)]
    if candidates:
        return sorted(candidates, key=lambda p: p.name.lower())[0]
    return None


def load_experimental_dataset(
    raw_dir: Path,
    min_completion: float = 0.95,
    drop_constant_zero_facilities: bool = True,
) -> pd.DataFrame:
    """Load all usable raw result rows and join them with parsed FDS features."""
    raw_dir = Path(raw_dir)
    fds_by_stem = _fds_lookup(raw_dir)
    fds_feature_cache: Dict[Path, Dict[str, float]] = {}
    rows: list[dict[str, object]] = []

    for csv_path in sorted(raw_dir.glob("*_summary.csv")):
        summary = pd.read_csv(csv_path, encoding="utf-8-sig")
        case_col, source_grade_col = _case_columns(summary)
        for _, raw_row in summary.iterrows():
            case_name = str(raw_row[case_col]).strip()
            try:
                case = parse_case_name(case_name)
            except ValueError:
                continue
            dk = float(raw_row.get("Dk", np.nan))
            completion = float(raw_row.get("completion_ratio", 1.0))
            if not math.isfinite(dk) or dk < 0.0 or dk > 1.0:
                continue
            if not math.isfinite(completion) or completion < min_completion:
                continue
            fds_path = _resolve_fds(case_name, fds_by_stem)
            if fds_path is None:
                continue
            if fds_path not in fds_feature_cache:
                fds_feature_cache[fds_path] = parse_fds_features(fds_path)
            fds_features = fds_feature_cache[fds_path]
            row: dict[str, object] = {
                **fds_features,
                **case_condition_features(case),
                **directional_case_features(fds_features, case),
                "facility_name": case.facility,
                "case_name": case_name,
                "csv_file": csv_path.name,
                "fds_file": fds_path.name,
                "source_damage_grade": raw_row.get(source_grade_col, "") if source_grade_col else "",
                "completion_ratio": completion,
                "Dk": dk,
                "dk_grade": dk_to_grade(dk),
                "dk_grade_name": grade_name(dk_to_grade(dk)),
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    if drop_constant_zero_facilities:
        max_by_facility = df.groupby("facility_name")["Dk"].transform("max")
        df = df[max_by_facility > 0.0].copy()

    facilities = sorted(df["facility_name"].unique())
    facility_index = {name: idx for idx, name in enumerate(facilities)}
    df["facility_index"] = df["facility_name"].map(facility_index).astype(float)

    for column in EXPERIMENT_FEATURE_COLUMNS:
        if column not in df.columns:
            df[column] = 0.0
    df = df.replace([np.inf, -np.inf], np.nan)
    df[list(EXPERIMENT_FEATURE_COLUMNS)] = df[list(EXPERIMENT_FEATURE_COLUMNS)].fillna(0.0)
    compact_rows = [compact_experimental_features(row) for row in df.to_dict("records")]
    compact_df = pd.DataFrame(compact_rows, index=df.index).astype(float)
    compact_df = compact_df[list(COMPACT_EXPERIMENT_FEATURE_COLUMNS)].fillna(0.0)
    df = df.drop(columns=[c for c in COMPACT_EXPERIMENT_FEATURE_COLUMNS if c in df.columns])
    df = pd.concat([df, compact_df], axis=1)
    return df.reset_index(drop=True)
