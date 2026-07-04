from pathlib import Path

import numpy as np

from agent_damage.src.data.experimental import (
    EXPERIMENT_FEATURE_COLUMNS,
    dk_to_grade,
    parse_case_name,
    parse_fds_features,
)
from agent_damage.src.inference.experimental_predictor import ExperimentalDkPredictor


class ConstantRegressor:
    def __init__(self, value: float) -> None:
        self.value = value

    def predict(self, X):
        return np.full((len(X),), self.value, dtype=float)


def _sample_fds(path: Path) -> Path:
    path.write_text(
        """
&HEAD CHID='sample'/
&TIME T_END=1800.0/
&MESH ID='Mesh01', IJK=10,20,5, XB=0.0,10.0,0.0,20.0,0.0,5.0/
&SURF ID='WOOD_SURFACE'/
&MATL ID='PLASTIC_MATL'/
&OBST ID='wood_paper_box', XB=1.0,3.0,2.0,4.0,0.0,2.0, SURF_ID='WOOD_SURFACE'/
&VENT ID='open_door', XB=0.0,0.0,1.0,3.0,0.0,2.0, SURF_ID='OPEN'/
&DEVC ID='TC_dian_nao_01', QUANTITY='TEMPERATURE', XYZ=2.0,3.0,1.0/
&DEVC ID='RHFG_dian_nao_01', QUANTITY='RADIATIVE HEAT FLUX GAS', XYZ=2.0,3.0,1.0/
""",
        encoding="utf-8",
    )
    return path


def test_parse_case_name_extracts_condition_fields():
    case = parse_case_name("TWA_q1500_a90_e30_d1360_t1800")
    assert case.facility == "TWA"
    assert case.heat_flux_kw_m2 == 1500
    assert case.heat_azimuth_deg == 90
    assert case.heat_elevation_deg == 30
    assert case.radiation_duration_ms == 1360
    assert case.case_t_end_s == 1800


def test_dk_to_grade_uses_four_threshold_classes():
    assert dk_to_grade(0.0) == 0
    assert dk_to_grade(0.0399) == 0
    assert dk_to_grade(0.04) == 1
    assert dk_to_grade(0.10) == 2
    assert dk_to_grade(0.40) == 3


def test_parse_fds_features_extracts_geometry_and_counts(tmp_path: Path):
    features = parse_fds_features(_sample_fds(tmp_path / "sample.fds"))
    assert features["domain_length"] == 10
    assert features["domain_width"] == 20
    assert features["domain_height"] == 5
    assert features["mesh_count"] == 1
    assert features["obst_count"] == 1
    assert features["vent_count"] == 1
    assert features["open_vent_count"] == 1
    assert features["temperature_device_count"] == 1
    assert features["radiative_flux_device_count"] == 1
    assert features["wood_paper_count"] >= 1
    assert features["plastic_count"] >= 1
    assert features["electronics_count"] >= 1


def test_experimental_predictor_returns_dk_and_grade(tmp_path: Path):
    fds = _sample_fds(tmp_path / "sample.fds")
    predictor = ExperimentalDkPredictor(
        model=ConstantRegressor(0.16),
        feature_columns=EXPERIMENT_FEATURE_COLUMNS,
        facility_index_map={"TWA": 0},
    )
    result = predictor.predict(fds, "TWA_q1500_a90_e30_d1360_t1800")
    assert result.predicted_dk == 0.16
    assert result.damage_grade == 2
    assert result.damage_grade_name == "中等破坏"

