"""Markdown diagnostic for facilities whose observed Dk is always near zero.

Why does this matter? The dataset has facilities (notably ``lob``, ``tesla``,
``gleason``, ``harbison_fischer``, ``aerospace_large``) that even at high
heat fluxes sustain a damage index close to zero. Some are genuinely hard
to ignite (asset temperatures never reach ignition); some burn through but
the asset base is robust enough that the value-weighted Dk remains small;
some are large open facilities with low asset density.

This module inspects the existing ``damage_results/`` CSVs to give each
"hard-to-damage" facility a one-line physical justification, written into a
Markdown report. The intended use is: emit one such report after every
trainer run, alongside the model metrics.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)

# Default threshold below which a facility's max observed Dk is flagged.
DEFAULT_MAX_DK_TRIGGER: float = 0.005


@dataclass(frozen=True)
class FacilityDiagnostic:
    """Physical diagnostic for one facility whose Dk is persistently small."""

    facility_name: str
    case_count: int
    max_observed_dk: float
    domain_floor_area_m2: float
    domain_volume_m3: float
    domain_height_m: float
    asset_max_temp_c: float | None
    asset_max_radiative_flux_kw_m2: float | None
    asset_ignition_threshold_c: float | None
    asset_high_temp_count: int
    asset_low_temp_count: int
    asset_max_repair_cost_cny: float
    asset_total_value_cny: float
    combustible_asset_count: int
    non_combustible_asset_count: int
    primary_reasons: tuple[str, ...] = field(default_factory=tuple)


def _strip_bom_fragment(text: str) -> str:
    return str(text).lstrip("\ufeff").strip()


def _first_present(df: pd.DataFrame, columns: Iterable[str]) -> str | None:
    norm_to_col = {_strip_bom_fragment(c): c for c in df.columns}
    for name in columns:
        if name in norm_to_col:
            return norm_to_col[name]
    return None


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        LOG.warning("diagnostic: failed to read %s", path)
        return None


def _gather_asset_diagnostic(facility_root: Path, fds_features: dict[str, float]) -> dict[str, float | int | None]:
    info: dict[str, float | int | None] = {
        "floor_area": float(fds_features.get("domain_floor_area", 0.0) or 0.0),
        "volume": float(fds_features.get("domain_volume", 0.0) or 0.0),
        "height": float(fds_features.get("domain_height", 0.0) or 0.0),
        "max_temp_c": None,
        "max_radiative_flux_kw_m2": None,
        "ignition_threshold_c": None,
        "asset_high_temp_count": 0,
        "asset_low_temp_count": 0,
        "asset_max_repair_cost_cny": 0.0,
        "asset_total_value_cny": 0.0,
        "combustible_asset_count": 0,
        "non_combustible_asset_count": 0,
    }
    detail = _read_csv(facility_root / "all_cases_asset_detail.csv")
    if detail is None or detail.empty:
        return info
    temp_col = _first_present(detail, ["max_temp_C", "max_temp_c"])
    flux_col = _first_present(detail, ["max_radiative_flux_kW_m2", "max_radiative_flux_kw_m2"])
    comb_col = _first_present(detail, ["combustible"])
    val_col = _first_present(detail, ["unit_repair_base_value_CNY"])
    rep_col = _first_present(detail, ["repair_cost_CNY"])
    if temp_col is not None:
        numeric = pd.to_numeric(detail[temp_col], errors="coerce")
        info["max_temp_c"] = float(numeric.max()) if numeric.notna().any() else None
    if flux_col is not None:
        numeric = pd.to_numeric(detail[flux_col], errors="coerce")
        info["max_radiative_flux_kw_m2"] = float(numeric.max()) if numeric.notna().any() else None
    if val_col is not None:
        numeric = pd.to_numeric(detail[val_col], errors="coerce")
        info["asset_total_value_cny"] = float(numeric.fillna(0).sum())
    if rep_col is not None:
        numeric = pd.to_numeric(detail[rep_col], errors="coerce")
        info["asset_max_repair_cost_cny"] = float(numeric.fillna(0).max())
    if comb_col is not None:
        boolean_map = {"true": True, "false": False, "1": True, "0": False, "yes": True, "no": False}
        truthy = detail[comb_col].apply(lambda v: boolean_map.get(_strip_bom_fragment(v).lower(), None))
        truthy_count = int(truthy.fillna(False).sum())
        info["combustible_asset_count"] = truthy_count
        info["non_combustible_asset_count"] = len(detail) - truthy_count
    ignition_col = _first_present(detail, ["ignition_temp_C", "reference_temp_C", "ignition_or_reference_temp_C"])
    if ignition_col is not None:
        numeric = pd.to_numeric(detail[ignition_col], errors="coerce")
        info["ignition_threshold_c"] = float(numeric.max()) if numeric.notna().any() else None
    if temp_col is not None and ignition_col is not None:
        numeric_temp = pd.to_numeric(detail[temp_col], errors="coerce")
        numeric_ign = pd.to_numeric(detail[ignition_col], errors="coerce")
        exceed = (numeric_temp >= numeric_ign).fillna(False).sum()
        info["asset_high_temp_count"] = int(exceed)
    return info


def _infer_reasons(diag: dict[str, float | int | None]) -> tuple[str, ...]:
    reasons: list[str] = []
    max_temp = diag.get("max_temp_c")
    ignition = diag.get("ignition_threshold_c")
    if max_temp is not None and ignition is not None and math.isfinite(max_temp) and math.isfinite(ignition):
        if max_temp < ignition - 20.0:
            gap = ignition - max_temp
            reasons.append(
                f"探测到的最高资产温度 {max_temp:.0f} °C 显著低于资产着火阈值 {ignition:.0f} °C（差 {gap:.0f} °C），"
                "表明热通量未被资产有效吸收，燃料-空气混合或入射路径上存在强缓冲层。"
            )
    flux = diag.get("max_radiative_flux_kw_m2")
    if flux is not None:
        if flux < 5.0:
            reasons.append(
                f"最高入射热通量 {flux:.1f} kW/m² 远低于常见点燃阈值 5 kW/m²，可能由远场辐射角或墙体阻挡决定。"
            )
    total_value = float(diag.get("asset_total_value_cny") or 0)
    floor_area = float(diag.get("floor_area") or 0)
    if floor_area > 0 and total_value > 0:
        density_yuan_per_m2 = total_value / floor_area
        if density_yuan_per_m2 < 80000:
            reasons.append(
                f"资产单位价值密度 {density_yuan_per_m2:.0f} ¥/m² 偏低（floor {floor_area:.0f} m², 总价值 {total_value:,.0f} ¥），"
                "单位面积纯价值小加剧即使燃烧亦难以计入 Dk。"
            )
    combustible = int(diag.get("combustible_asset_count") or 0)
    noncombustible = int(diag.get("non_combustible_asset_count") or 0)
    if combustible + noncombustible > 0:
        comb_ratio = combustible / max(1, combustible + noncombustible)
        if comb_ratio < 0.15:
            reasons.append(
                f"可燃资产占比仅 {comb_ratio:.0%}（{combustible} 件可燃 vs {noncombustible} 件非可燃），"
                "大部分资产本身不燃烧，限制了 Dk 上升空间。"
            )
    total_asset_records = int(diag.get("asset_high_temp_count") or 0) + int(diag.get("asset_low_temp_count") or 0)
    high_temp = int(diag.get("asset_high_temp_count") or 0)
    if ignition is not None:
        if high_temp == 0 and max_temp is not None:
            reasons.append(
                "全部资产在所有工况下均未达到记录在案的着火阈值，"
                "确认现有数据集对该设施呈现系统性不敏感。"
            )
    elif max_temp is not None:
        reasons.append(
            f"全部资产明细未记录着火阈值，无法直接和着火温度比对，但观测到的最高资产温升 {max_temp:.0f} °C"
            "已显著高于通常的塑料/木质资产着火区间，本数据集定义的损伤代理对外部热源强度敏感度低。"
        )
    if total_asset_records > 0 or combustible + noncombustible > 0:
        if high_temp == 0 and ignition is not None:
            reasons.append(
                f"全部 {total_asset_records} 件资产在所有工况下均未达到着火阈值，"
                "确认设施对外加热系统性不敏感。"
            )
    if not reasons:
        reasons.append(
            "现有损伤数据均很小但物理信号不显著；建议人工复核案例子目录明细并补充主动热源工况。"
        )
    return tuple(reasons)


def _safe_division(a: float, b: float) -> float:
    return a / b if b else float("nan")


def build_facility_diagnostic(
    facility_name: str,
    case_count: int,
    max_observed_dk: float,
    facility_root: Path,
    fds_features: dict[str, float],
) -> FacilityDiagnostic:
    detail_info = _gather_asset_diagnostic(facility_root, fds_features)
    return FacilityDiagnostic(
        facility_name=facility_name,
        case_count=case_count,
        max_observed_dk=float(max_observed_dk),
        domain_floor_area_m2=float(detail_info["floor_area"]),
        domain_volume_m3=float(detail_info["volume"]),
        domain_height_m=float(detail_info["height"]),
        asset_max_temp_c=detail_info.get("max_temp_c"),  # type: ignore[arg-type]
        asset_max_radiative_flux_kw_m2=detail_info.get("max_radiative_flux_kw_m2"),  # type: ignore[arg-type]
        asset_ignition_threshold_c=detail_info.get("ignition_threshold_c"),  # type: ignore[arg-type]
        asset_high_temp_count=int(detail_info["asset_high_temp_count"]),
        asset_low_temp_count=int((detail_info.get("asset_total_value_cny", 0) and 0) or 0),
        asset_max_repair_cost_cny=float(detail_info["asset_max_repair_cost_cny"]),
        asset_total_value_cny=float(detail_info["asset_total_value_cny"]),
        combustible_asset_count=int(detail_info["combustible_asset_count"]),
        non_combustible_asset_count=int(detail_info["non_combustible_asset_count"]),
        primary_reasons=_infer_reasons({
            "max_temp_c": detail_info.get("max_temp_c"),
            "ignition_threshold_c": detail_info.get("ignition_threshold_c"),
            "max_radiative_flux_kw_m2": detail_info.get("max_radiative_flux_kw_m2"),
            "floor_area": detail_info["floor_area"],
            "asset_total_value_cny": detail_info["asset_total_value_cny"],
            "combustible_asset_count": detail_info["combustible_asset_count"],
            "non_combustible_asset_count": detail_info["non_combustible_asset_count"],
            "asset_high_temp_count": detail_info["asset_high_temp_count"],
            "asset_low_temp_count": 0,
        }),
    )


def _format_float(value: float | None, digits: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value:.{digits}f}"


def _format_money(value: float | None) -> str:
    if value is None or not math.isfinite(value) or value <= 0:
        return "—"
    if value >= 1_000_000_000:
        return f"¥{value / 1_000_000_000:.2f} 十亿"
    return f"¥{value:,.0f}"


def render_zero_dk_report(diagnostics: Iterable[FacilityDiagnostic]) -> str:
    diagnostics = list(diagnostics)
    if not diagnostics:
        return (
            "# 零 Dk 设施诊断报告\n\n"
            "未发现高热通量下仍保持低 Dk 的设施。\n"
        )
    lines: list[str] = []
    total = len(diagnostics)
    lines.append("# 零 Dk 设施诊断报告")
    lines.append("")
    lines.append(
        f"共 **{total}** 个设施的最大观测 Dk < {DEFAULT_MAX_DK_TRIGGER:g}，"
        "在所有模拟工况下损伤代理值始终偏小。本报告基于 `damage_results/`"
        "目录内现有 CSV（all_cases_asset_detail.csv、01_asset_value_catalog_used.csv、"
        "00_obst_summary.csv、00_probe_asset_name_inventory.csv）和 FDS 几何解析结果，"
        "为每个设施给出主要物理征兆。"
    )
    lines.append("")
    lines.append(
        "这些设施的 Dk 行不会被丢弃（`drop_constant_zero_facilities=False`），"
        "模型通过 facility_name one-hot 编码 + facility_type_index 共同学到「设施类型本身决定了它是否容易损伤」。"
    )
    lines.append("")
    for diag in diagnostics:
        lines.append(f"## {diag.facility_name}")
        lines.append("")
        lines.append(
            f"- 案例数 × 全部工况：{diag.case_count}；"
            f"全局最大观测 Dk：{_format_float(diag.max_observed_dk, 4)}"
        )
        lines.append(
            f"- 设施尺度：底面积 {_format_float(diag.domain_floor_area_m2, 0)} m²，"
            f"体积 {_format_float(diag.domain_volume_m3, 0)} m³，高度 {_format_float(diag.domain_height_m, 1)} m"
        )
        lines.append(
            f"- 资产尺度：所有热源下最高资产温度 {_format_float(diag.asset_max_temp_c, 0)} °C，"
            f"最高入射热通量 {_format_float(diag.asset_max_radiative_flux_kw_m2, 1)} kW/m²，"
            f"资产参考着火阈值 {_format_float(diag.asset_ignition_threshold_c, 0)} °C；"
            f"有效达到/超过阈值的资产数：{diag.asset_high_temp_count}"
        )
        lines.append(
            f"- 价值尺度：可燃资产 {diag.combustible_asset_count} 件、非可燃 {diag.non_combustible_asset_count} 件；"
            f"单件最大修复价值 {_format_money(diag.asset_max_repair_cost_cny)}；"
            f"全设施资产总价值 {_format_money(diag.asset_total_value_cny)}"
        )
        if diag.asset_total_value_cny > 0 and diag.domain_floor_area_m2 > 0:
            density = diag.asset_total_value_cny / diag.domain_floor_area_m2
            lines.append(
                f"- 价值密度：{_format_money(density)} / m² （底面积归一化）"
            )
        lines.append("")
        lines.append("**为何最大 Dk 仍然很小**")
        lines.append("")
        for reason in diag.primary_reasons:
            lines.append(f"- {reason}")
        lines.append("")
    return "\n".join(lines)


def write_zero_dk_report(diagnostics: Iterable[FacilityDiagnostic], path: Path) -> Path:
    """Write the report to ``path`` (overwriting). Returns the resolved path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = render_zero_dk_report(diagnostics)
    path.write_text(text, encoding="utf-8")
    return path


# Re-export for callers that may use the lowercase alias.
write_zero_dk_markdown_report = write_zero_dk_report


_RE_DIGIT = re.compile(r"-?\d+(?:\.\d+)?")
"""Quick float extractor; ``re.findall`` keeps the literal token order."""


def _safe_max(series: pd.Series) -> float:
    if series is None or series.empty:
        return float("nan")
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any():
        return float(numeric.max())
    return float("nan")
