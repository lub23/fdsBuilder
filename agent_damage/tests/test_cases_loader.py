"""Tests for the cases-layout loader and zero-Dk diagnostic.

These tests build a synthetic two-facility ``cases/`` tree under ``tmp_path``
so the trailer does not depend on committing the production dataset into
this test file. The loader/diagnostic modules are exercised through their
public APIs only.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pytest

from agent_damage.src.data import cases_loader  # noqa: E402
from agent_damage.src.data.cases_loader import (  # noqa: E402
    FacilityCase,
    FacilitySummary,
    find_zero_dk_facilities,
    iter_facilities,
    parse_case_name,
)
from agent_damage.src.data.experimental import (  # noqa: E402
    _ensure_onehot_columns,
    _facility_onehot_column,
    _onehot_row,
    compact_experimental_features,
    dk_to_grade,
    load_experimental_dataset,
    parse_case_name as experimental_parse_case_name,
    parse_fds_features,
)
from agent_damage.src.data.zero_dk_diagnostic import (  # noqa: E402
    build_facility_diagnostic,
    render_zero_dk_report,
    write_zero_dk_report,
)
from agent_damage.src.inference.experimental_predictor import (  # noqa: E402
    ExperimentalDkPredictor,
)


class _ConstantRegressor:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, X):
        return np.full((len(X),), self.value, dtype=float)


def _write_csv(path: Path, header: str, rows: list[str]) -> Path:
    path.write_text(
        "\ufeff" + header + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return path


def _sample_fds(path: Path) -> Path:
    path.write_text(
        """
&HEAD CHID='sample'/
&TIME T_END=1800.0/
&MESH ID='Mesh01', IJK=10,20,5, XB=0.0,10.0,0.0,20.0,0.0,5.0/
&VENT ID='open_door', XB=0.0,0.0,1.0,3.0,0.0,2.0, SURF_ID='OPEN'/
&DEVC ID='T_box_01', QUANTITY='TEMPERATURE', XYZ=2.0,3.0,1.0/
&DEVC ID='RHFG_box_01', QUANTITY='RADIATIVE HEAT FLUX GAS', XYZ=2.0,3.0,1.0/
""",
        encoding="utf-8",
    )
    return path


def _build_synthetic_cases_root(root: Path) -> dict[str, str]:
    """Create a small `cases/.../damage_results/` directory with two facilities."""
    structure = {
        "alpha": {
            "fds_count": 1,
            "rollup_columns": [
                "case_name", "total_asset_quantity",
                "DS0_count_完好或未燃烧", "DS1_count_轻微",
                "DS2_count_中等", "DS3_count_严重或燃烧烧毁",
                "total_asset_value_CNY", "total_repair_cost_CNY",
                "Dk", "damage_grade",
                "simulation_time_s", "target_T_END_s", "completion_ratio",
            ],
            "rows": [
                ["alpha_q500_a0_e0_d1360_t1800", 10, 9, 0, 0, 1,
                 "100000", "5000", "0.05", "1", "1800", "1800", "1.0"],
                ["alpha_q5000_a90_e30_d2100_t1800", 10, 8, 1, 0, 1,
                 "100000", "8000", "0.08", "1", "1800", "1800", "1.0"],
                ["alpha_q15000_a180_e45_d7500_t1800", 10, 0, 5, 3, 2,
                 "100000", "55000", "0.55", "2", "1800", "1800", "1.0"],
            ],
            "fds_q0a0e0d1360t1800": True,
        },
        "beta": {
            "fds_count": 1,
            "rollup_columns": [
                "case",  # Hangar-style alias
                "asset_count",
                "total_repair_base_value_CNY",
                "total_repair_cost_CNY",
                "Dk",
                "damage_level",
                "simulation_time_s",
                "target_T_END_s",
                "completion_ratio",
            ],
            "rows": [
                ["beta_q500_a0_e0_d1360_t1800", 8, "50000", "0",
                 "0.0", "未达到破坏等级/基本完好",
                 "1800", "1800", "1.0"],
                ["beta_q15000_a270_e60_d7500_t1800", 8, "50000", "100",
                 "1e-5", "未达到破坏等级/基本完好",
                 "12.0", "1800", "0.007"],
            ],
            "fds_q0a0e0d1360t1800": True,
        },
    }

    for facility_name, info in structure.items():
        fac_root = root / facility_name
        fac_damage = fac_root / "damage_results"
        fac_damage.mkdir(parents=True, exist_ok=True)
        if info.get("fds_count", 0):
            (fac_root / f"{facility_name}_q500_a0_e0_d1360_t1800.fds").write_text(
                "placeholder FDS content\n",
                encoding="utf-8",
            )
        _write_csv(
            fac_damage / "04_all_cases_Dk_summary.csv",
            ",".join(info["rollup_columns"]),
            [",".join(str(v) for v in row) for row in info["rows"]],
        )
    return {name: "OK" for name in structure}


@pytest.fixture
def cases_root(tmp_path: Path) -> Path:
    root = tmp_path / "cases"
    root.mkdir(parents=True, exist_ok=True)
    _build_synthetic_cases_root(root)
    return root


def test_iter_facilities_handles_bom_and_hangar_alias(cases_root: Path) -> None:
    summaries: list[FacilitySummary] = list(iter_facilities(cases_root))
    by_name = {s.facility_name: s for s in summaries}
    assert set(by_name) == {"alpha", "beta"}
    assert all(s.fds_path and s.fds_path.is_file() for s in summaries)
    alpha_rows = {(c.case_name, c.dk) for c in by_name["alpha"].cases}
    assert ("alpha_q15000_a180_e45_d7500_t1800", 0.55) in alpha_rows

    beta_case_names = {c.case_name for c in by_name["beta"].cases}
    assert beta_case_names == {
        "beta_q500_a0_e0_d1360_t1800",
        "beta_q15000_a270_e60_d7500_t1800",
    }


def test_load_experimental_dataset_builds_full_shell(cases_root: Path) -> None:
    df = load_experimental_dataset(cases_root, min_completion=0.0)
    assert not df.empty
    assert set(df["facility_name"]) == {"alpha", "beta"}
    assert {"total_repair_cost_cny", "total_asset_value_cny"}.issubset(df.columns)
    assert {"Dk", "dk_grade", "completion_ratio", "simulation_time_s"}.issubset(df.columns)
    onehot_columns = tuple(df.attrs["facility_onehot_columns"])
    target_alpha = _facility_onehot_column("alpha")
    assert target_alpha in onehot_columns
    target_beta = _facility_onehot_column("beta")
    assert target_beta in onehot_columns
    sample_alpha = df.iloc[0]
    assert sample_alpha[target_alpha] in (0.0, 1.0)


def test_load_experimental_dataset_keeps_zero_dk_rows(cases_root: Path) -> None:
    df = load_experimental_dataset(cases_root, min_completion=0.0)
    beta_zero = df[(df["facility_name"] == "beta") & (df["Dk"] < 1e-3)]
    assert not beta_zero.empty
    assert (beta_zero["dk_grade"] == 0).all()


def test_facility_onehot_columns_helpers() -> None:
    cols = _ensure_onehot_columns(["alpha", "beta", "Gamma-1", "alpha"])
    base_alpha = _facility_onehot_column("alpha")
    base_gamma_dashed = _facility_onehot_column("AlphaWith-Dash")
    assert base_alpha.startswith("facility_oh_alpha")
    assert base_gamma_dashed == "facility_oh_AlphaWith_Dash"
    row = _onehot_row("alpha", cols)
    assert row[base_alpha] == 1.0
    assert sum(row.values()) == 1.0


def test_compact_experimental_features_uses_facility_index() -> None:
    features = {
        "facility_index": 5,
        "domain_floor_area": 3600.0,
        "domain_volume": 14400.0,
        "domain_height": 4.0,
        "heat_flux_log10": 2.0,
        "heat_elevation_sin": 0.0,
        "heat_azimuth_sin": 0.0,
        "heat_azimuth_cos": 1.0,
        "radiation_duration_s": 1.36,
        "heat_dose_log10": 3.0,
        "asset_density": 0.02,
        "incident_asset_front_ratio": 0.1,
    }
    pack = compact_experimental_features(features)
    assert pack["facility_type_index"] == 5
    assert pack["log_floor_area"] >= 0.0


def test_find_zero_dk_facilities_flags_persistent_low_damage(cases_root: Path) -> None:
    summaries = list(iter_facilities(cases_root))
    flagged = find_zero_dk_facilities(summaries, min_dk_threshold=1e-3)
    flagged_names = {s.facility_name for s in flagged}
    assert "beta" in flagged_names
    assert "alpha" not in flagged_names


def test_zero_dk_diagnostic_reports_lob_like_signals(cases_root: Path) -> None:
    fac_root = cases_root / "beta"
    detail_csv = fac_root / "damage_results" / "all_cases_asset_detail.csv"
    _write_csv(
        detail_csv,
        "case_name,asset_id,asset_cn,combustible,max_temp_C,max_radiative_flux_kW_m2,"
        "ignition_temp_C,repair_cost_CNY,unit_repair_base_value_CNY,simulation_time_s,"
        "target_T_END_s,completion_ratio,source_basis,source_url",
        [
            "beta_q500_a0_e0_d1360_t1800,desk01,办公工位,True,191,260,292,0,15000,1800,1800,1.0,SI,http",
            "beta_q15000_a270_e60_d7500_t1800,desk02,办公工位,True,190,5,292,100,15000,12,1800,0.007,SI,http",
        ],
    )

    fds_features = parse_fds_features(_sample_fds(fac_root / ".fds_placeholder.fds"))
    diag = build_facility_diagnostic(
        facility_name="beta",
        case_count=2,
        max_observed_dk=1e-5,
        facility_root=fac_root / "damage_results",
        fds_features=fds_features,
    )
    text = render_zero_dk_report([diag])
    assert "beta" in text
    assert "探测到的最高资产温度 191" in text
    assert "低于资产着火阈值 292" in text
    out = write_zero_dk_report([diag], cases_root / "out.md")
    assert out.is_file() and out.read_text(encoding="utf-8").startswith("# ")


def test_pickle_round_trip_with_one_hot_and_facility_map(cases_root: Path) -> None:
    df = load_experimental_dataset(cases_root, min_completion=0.0)
    onehot = df.attrs["facility_onehot_columns"]
    facility_index_map = df.attrs["facility_index_map"]
    X = df[list(onehot)]
    assert X.dtypes.map(str).tolist() == ["float64"] * len(onehot)
    model = _ConstantRegressor(value=0.10)
    artifact = {
        "model": model,
        "model_name": "constant_zero_one",
        "feature_columns": onehot,
        "dk_thresholds": (0.04, 0.10, 0.40),
        "dk_grade_names": (
            "未达到破坏等级/基本完好",
            "轻微破坏",
            "中等破坏",
            "严重破坏",
        ),
        "facility_index_map": facility_index_map,
        "facility_onehot_columns": onehot,
        "min_completion": 0.0,
    }
    pickle_path = cases_root / "experimental_dk_regressor.pkl"
    pickle_path.write_bytes(pickle.dumps(artifact))
    loaded = ExperimentalDkPredictor(
        model=_ConstantRegressor(value=0.10),
        facility_index_map=facility_index_map,
        facility_onehot_columns=tuple(onehot),
    )
    sample_csv_row = (
        "z,10,20,5,1.0,1800.0,1800.0,1.0,pre,M\n"
    )
    fds = cases_root / "alpha" / "alpha_q500_a0_e0_d1360_t1800.fds"
    fds.write_text(
        _make_fds_text(),
        encoding="utf-8",
    )
    pred = loaded.predict(fds, "alpha_q500_a0_e0_d1360_t1800")
    assert 0.0 <= pred.predicted_dk <= 1.0
    assert pred.damage_grade in {0, 1, 2, 3}


def _make_fds_text() -> str:
    return (
        "&HEAD CHID='strategy'/\n"
        "&TIME T_END=1800.0/\n"
        "&MESH ID='m', IJK=10,20,5, XB=0.0,10.0,0.0,20.0,0.0,5.0/\n"
        "&VENT ID='open', XB=0.0,0.0,1.0,3.0,0.0,2.0, SURF_ID='OPEN'/\n"
        "&DEVC ID='T_wood_paper_01', QUANTITY='TEMPERATURE', XYZ=2.0,3.0,1.0/\n"
        "&DEVC ID='RHFG_wood_paper_01', QUANTITY='RADIATIVE HEAT FLUX GAS', XYZ=2.0,3.0,1.0/\n"
    )


def test_load_experimental_dataset_honours_min_completion_threshold(cases_root: Path) -> None:
    df = load_experimental_dataset(cases_root, min_completion=0.05)
    bad_min = df[df["facility_name"] == "beta"][df["completion_ratio"] < 0.05]
    assert bad_min.empty
    full_run = df[df["facility_name"] == "beta"][df["completion_ratio"] >= 0.05]
    assert not full_run.empty


def test_load_experimental_dataset_default_min_completion_is_zero(
    cases_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    df = load_experimental_dataset(cases_root)
    assert (df["completion_ratio"] >= 0.0).all()
    assert df.attrs["facility_onehot_columns"]


def test_parse_case_name_round_trip() -> None:
    parsed = experimental_parse_case_name("frymaster_corporation_q500_a0_e0_d1360_t1800")
    assert parsed.facility == "frymaster_corporation"
    assert parsed.heat_flux_kw_m2 == 500
    assert parsed.heat_azimuth_deg == 0
    assert parsed.heat_elevation_deg == 0
    assert parsed.radiation_duration_ms == 1360
    assert parsed.case_t_end_s == 1800
    parsed_dict = parse_case_name("alpha_q500_a0_e0_d1360_t1800")
    assert parsed_dict["facility"] == "alpha"
    assert parsed_dict["q"] == 500.0
    with pytest.raises(ValueError):
        parse_case_name("not-a-case-name")
    with pytest.raises(ValueError):
        experimental_parse_case_name("not-a-case-name")
    assert dk_to_grade(0.05) == 1
    assert dk_to_grade(0.50) == 3


def test_json_dump_artifact_loads(cases_root: Path) -> None:
    artifact = {"onehot_columns": ["facility_oh_alpha"], "json": True}
    j = json.dumps(artifact)
    reloaded = json.loads(j)
    assert reloaded == artifact
