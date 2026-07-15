"""Loader for the per-facility cases/ dataset layout.

The legacy flat directory (`raw_results/`) is no longer used: every facility
now lives under ``agent_damage/cases/<facility>/`` with one reference FDS at the
facility root and the per-case outputs under
``<facility>/damage_results/<case>/``. This module reads the
rollup ``04_all_cases_Dk_summary.csv`` (carrying one row per simulated case)
and normalises the 14 observed column variants into a single schema used by
the trainer and predictor.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

LOG = logging.getLogger(__name__)

# Damage-grade column aliases observed across the 32 facilities.
DAMAGE_GRADE_COLUMN_ALIASES: tuple[str, ...] = (
    "damage_grade",
    "damage_level",
    "Dk_level",
)

# Case-identifier column aliases — Hangar's rollup uses ``case`` (no suffix).
CASE_NAME_COLUMN_ALIASES: tuple[str, ...] = ("case_name", "case")

# Universal columns present in every observed Dk_summary schema.
UNIVERSAL_DK_COLUMNS: tuple[str, ...] = (
    "case_name",
    "Dk",
    "completion_ratio",
    "simulation_time_s",
    "target_T_END_s",
)


@dataclass(frozen=True)
class FacilityCase:
    """One case row, normalized to the universal schema with bbox metadata."""

    facility_name: str
    case_name: str
    dk: float
    completion_ratio: float
    simulation_time_s: float
    target_t_end_s: float
    damage_grade_raw: str = ""
    total_repair_cost_cny: float | None = None
    total_asset_value_cny: float | None = None
    total_asset_quantity: int | None = None
    case_subdir: Path | None = None
    fds_file: str = ""
    source_csv: Path | None = None


@dataclass(frozen=True)
class FacilitySummary:
    """One facility — its cases plus metadata for that facility's FDS lay."""

    facility_name: str
    fds_path: Path | None
    cases: list[FacilityCase] = field(default_factory=list)
    zero_dk_case_count: int = 0
    max_dk: float = 0.0


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff").strip()


def _normalize_header(line: str) -> tuple[str, ...]:
    """Strip BOM, split on commas, strip whitespace from each column name."""
    return tuple(_strip_bom(cell) for cell in line.split(","))


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV handling UTF-8 BOM and BOM-prefixed first column names."""
    return pd.read_csv(path, encoding="utf-8-sig")


def _resolve_case_name_column(columns: Iterable[str]) -> str | None:
    cols = list(columns)
    for alias in CASE_NAME_COLUMN_ALIASES:
        if alias.lstrip("\ufeff") in (c.lstrip("\ufeff") for c in cols):
            return next(c for c in cols if _strip_bom(c) == alias)
    return None


def _resolve_dk(row: dict[str, object], columns: list[str]) -> float | None:
    raw = row.get("Dk", None)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _resolve_completion(row: dict[str, object]) -> float:
    raw = row.get("completion_ratio", 1.0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(value):
        return 1.0
    return value


def _resolve_damage_grade_label(row: dict[str, object], columns: list[str]) -> str:
    for col in DAMAGE_GRADE_COLUMN_ALIASES:
        match = next((c for c in columns if _strip_bom(c) == col), None)
        if match is not None:
            raw = row.get(match, "")
            if raw is not None and str(raw).strip():
                return str(raw).strip()
    return ""


def _resolve_optional_float(row: dict[str, object], column: str) -> float | None:
    raw = row.get(column, None)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _resolve_optional_int(row: dict[str, object], column: str) -> int | None:
    raw = row.get(column, None)
    if raw is None or raw == "":
        return None
    try:
        return int(round(float(raw)))
    except (TypeError, ValueError):
        return None


def _resolve_fds_for_facility(facility_root: Path) -> Path | None:
    """Locate the single reference FDS at the facility root (one per facility)."""
    candidates = sorted(facility_root.glob("*.fds"))
    if not candidates:
        return None
    return candidates[0]


def _per_case_diagnostic_table(facility_root: Path) -> pd.DataFrame | None:
    """Best-effort per-case diagnostic table for the facility, for zero-Dk detection.

    Reads ``all_cases_asset_detail.csv`` (whose layout differs per facility) and
    returns a tidy frame with the diagnostic columns used by the zero-Dk report,
    or ``None`` if the asset-detail file is missing/incompatible.
    """
    detail_path = facility_root / "all_cases_asset_detail.csv"
    if not detail_path.is_file():
        return None
    try:
        df = _read_csv(detail_path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return None
    if df.empty:
        return df
    cases = df.columns.tolist()
    column_index: dict[str, str] = {c.lstrip("\ufeff"): c for c in cases}

    def col(name: str) -> str | None:
        return column_index.get(name)

    case_col = col("case_name") or _resolve_case_name_column(cases)
    if case_col is None:
        return None
    out = pd.DataFrame()
    out["case_name"] = df[case_col].astype(str)
    if (temp_col := col("max_temp_C")) is not None:
        out["max_temp_C"] = pd.to_numeric(df[temp_col], errors="coerce")
    if (flux_col := col("max_radiative_flux_kW_m2")) is not None:
        out["max_radiative_flux_kW_m2"] = pd.to_numeric(df[flux_col], errors="coerce")
    if (ign_col := col("ignition_temp_C")) is not None:
        out["ignition_temp_C"] = pd.to_numeric(df[ign_col], errors="coerce")
    if (repair_unit_col := col("unit_repair_base_value_CNY")) is not None:
        out["unit_repair_base_value_CNY"] = pd.to_numeric(df[repair_unit_col], errors="coerce")
    if (repair_col := col("repair_cost_CNY")) is not None:
        out["repair_cost_CNY"] = pd.to_numeric(df[repair_col], errors="coerce")
    if (asset_cn_col := col("asset_cn")) is not None:
        out["asset_cn"] = df[asset_cn_col].astype(str)
    if (asset_id_col := col("asset_id")) is not None:
        out["asset_id"] = df[asset_id_col].astype(str)
    return out


def _rows_from_summary(
    facility_name: str,
    damage_results: Path,
    csv_path: Path,
    *,
    default_case_name: str = "",
) -> list[FacilityCase]:
    """Normalize rows from either the facility rollup or one per-case summary."""
    try:
        df = _read_csv(csv_path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        LOG.warning("facility %s: failed to read %s (%s)", facility_name, csv_path, exc)
        return []
    if df.empty:
        return []

    columns = df.columns.tolist()
    case_col = _resolve_case_name_column(columns)
    if case_col is None and not default_case_name:
        LOG.warning(
            "facility %s: summary missing case identifier column (case_name/case); headers=%s",
            facility_name,
            columns[:5],
        )
        return []

    rows: list[FacilityCase] = []
    for _, raw_row in df.iterrows():
        row_dict = raw_row.to_dict()
        case_name = str(row_dict.get(case_col) or "").strip() if case_col else default_case_name
        case_name = case_name or default_case_name
        if not case_name:
            continue
        dk_value = _resolve_dk(row_dict, columns)
        if dk_value is None:
            continue
        sim_time = _resolve_optional_float(row_dict, "simulation_time_s")
        target_t = _resolve_optional_float(row_dict, "target_T_END_s")
        repair_cost = _resolve_optional_float(row_dict, "total_repair_cost_CNY")
        if repair_cost is None:
            repair_cost = _resolve_optional_float(row_dict, "repair_cost_CNY")
        asset_value = _resolve_optional_float(row_dict, "total_asset_value_CNY")
        if asset_value is None:
            asset_value = _resolve_optional_float(row_dict, "total_repair_base_value_CNY")
        if asset_value is None:
            asset_value = _resolve_optional_float(row_dict, "total_value_CNY")
        if asset_value is None:
            asset_value = _resolve_optional_float(row_dict, "total_base_value_CNY")
        asset_quantity = _resolve_optional_int(row_dict, "total_asset_quantity")
        if asset_quantity is None:
            asset_quantity = _resolve_optional_int(row_dict, "asset_quantity")
        if asset_quantity is None:
            asset_quantity = _resolve_optional_int(row_dict, "asset_quantity_total")
        if asset_quantity is None:
            asset_quantity = _resolve_optional_int(row_dict, "asset_count")
        case_subdir = damage_results / case_name
        rows.append(FacilityCase(
            facility_name=facility_name,
            case_name=case_name,
            dk=dk_value,
            completion_ratio=_resolve_completion(row_dict),
            simulation_time_s=float(sim_time) if sim_time is not None else 0.0,
            target_t_end_s=float(target_t) if target_t is not None else 0.0,
            damage_grade_raw=_resolve_damage_grade_label(row_dict, columns),
            total_repair_cost_cny=repair_cost,
            total_asset_value_cny=asset_value,
            total_asset_quantity=asset_quantity,
            case_subdir=case_subdir if case_subdir.is_dir() else None,
            source_csv=csv_path,
        ))
    return rows


def _load_facility_rollup(facility_name: str, damage_results: Path) -> list[FacilityCase]:
    """Load a facility rollup and supplement it with newly-added case folders.

    The rollup is preferred because it is cheap to read and already contains one
    row per case.  Contributors may copy a new case directory before regenerating
    ``04_all_cases_Dk_summary.csv``; any such directory is read from its own
    ``Dk_summary_*.csv`` so incremental/incomplete facilities remain usable.
    """
    rollup = damage_results / "04_all_cases_Dk_summary.csv"
    rows = _rows_from_summary(facility_name, damage_results, rollup) if rollup.is_file() else []
    if not rollup.is_file():
        LOG.warning("facility %s: missing %s; falling back to per-case summaries", facility_name, rollup)

    deduplicated: list[FacilityCase] = []
    seen: set[str] = set()
    for row in rows:
        if row.case_name not in seen:
            deduplicated.append(row)
            seen.add(row.case_name)
    rows = deduplicated

    for case_dir in sorted(path for path in damage_results.iterdir() if path.is_dir()):
        if case_dir.name in seen:
            continue
        summaries = sorted(case_dir.glob("Dk_summary_*.csv"))
        if not summaries:
            LOG.warning("facility %s: case %s has no Dk summary", facility_name, case_dir.name)
            continue
        additions = _rows_from_summary(
            facility_name,
            damage_results,
            summaries[0],
            default_case_name=case_dir.name,
        )
        for row in additions:
            if row.case_name not in seen:
                rows.append(row)
                seen.add(row.case_name)
    return rows


def iter_facilities(cases_root: Path) -> Iterator[FacilitySummary]:
    """Yield one ``FacilitySummary`` per facility directory under ``cases_root``.

    A facility directory is any direct child of ``cases_root`` that contains
    either a ``damage_results/`` subdir or a top-level ``.fds`` file.
    """
    cases_root = Path(cases_root)
    if not cases_root.is_dir():
        return
    for child in sorted(cases_root.iterdir()):
        if not child.is_dir():
            continue
        damage_results = child / "damage_results"
        fds_path = _resolve_fds_for_facility(child)
        cases = _load_facility_rollup(child.name, damage_results) if damage_results.is_dir() else []
        yield FacilitySummary(
            facility_name=child.name,
            fds_path=fds_path,
            cases=cases,
            zero_dk_case_count=sum(1 for c in cases if math.isclose(c.dk, 0.0, abs_tol=1e-9)),
            max_dk=max((c.dk for c in cases), default=0.0),
        )


def load_facilities(cases_root: Path) -> list[FacilitySummary]:
    """Return ``list(iter_facilities(cases_root))`` for direct callers."""
    return list(iter_facilities(cases_root))


def find_zero_dk_facilities(
    facilities: Iterable[FacilitySummary],
    *,
    min_dk_threshold: float = 1e-3,
) -> list[FacilitySummary]:
    """Facilities whose maximum observed Dk is below ``min_dk_threshold``.

    Such facilities never (or almost never) sustain damage in the dataset — they
    are flagged for the diagnostic report so downstream analysis can explain
    why even extreme heat fluxes fail to ignite them.
    """
    flagged: list[FacilitySummary] = []
    for summary in facilities:
        if summary.cases and summary.max_dk < min_dk_threshold:
            flagged.append(summary)
    return flagged


def facility_first_fds(cases_root: Path) -> dict[str, Path]:
    """Map facility_name → its single reference .fds path (if it exists)."""
    return {
        s.facility_name: s.fds_path
        for s in iter_facilities(cases_root)
        if s.fds_path is not None
    }


_RE_CASE_NAME_RE = re.compile(
    r"^(?P<facility>.+?)_q(?P<q>-?\d+(?:\.\d+)?)"
    r"_a(?P<a>-?\d+(?:\.\d+)?)"
    r"_e(?P<e>-?\d+(?:\.\d+)?)"
    r"_d(?P<d>-?\d+(?:\.\d+)?)"
    r"_t(?P<t>-?\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)


def parse_case_name(case_name: str) -> dict[str, float | str]:
    """Parse a case_name like ``facility_q500_a0_e0_d1360_t1800`` into parts.

    Returns a ``dict`` with keys ``facility``, ``q``, ``a``, ``e``, ``d``, ``t``.
    Raises ``ValueError`` if the case name does not match the canonical format.
    """
    match = _RE_CASE_NAME_RE.match(case_name.strip())
    if not match:
        raise ValueError(f"Cannot parse case name: {case_name!r}")
    return {
        "facility": match.group("facility"),
        "q": float(match.group("q")),
        "a": float(match.group("a")),
        "e": float(match.group("e")),
        "d": float(match.group("d")),
        "t": float(match.group("t")),
    }
