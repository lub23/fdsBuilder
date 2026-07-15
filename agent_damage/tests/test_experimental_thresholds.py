import numpy as np
import pandas as pd
import pytest

from agent_damage.scripts.train_experimental import (
    _generate_threshold_heatmaps,
    _threshold_table_for_facility,
)
from agent_damage.src.data.experimental import COMPACT_EXPERIMENT_FEATURE_COLUMNS, DK_GRADE_NAMES


class ConstantDamageRegressor:
    def predict(self, X):
        return np.full(len(X), 0.5, dtype=float)


class LinearFluxDamageRegressor:
    def predict(self, X):
        log_flux_index = COMPACT_EXPERIMENT_FEATURE_COLUMNS.index("heat_flux_log10")
        flux = np.power(10.0, X[:, log_flux_index]) - 1.0
        return flux / 10_000.0


def _scan(model, flux_values):
    return _threshold_table_for_facility(
        model=model,
        fds_features={},
        facility_name="sample",
        facility_index_map={"sample": 0},
        facility_onehot_columns=("facility_oh_sample",),
        azimuths=np.array([0.0]),
        elevations=np.array([0.0]),
        duration_s=1.36,
        flux_values=np.asarray(flux_values, dtype=float),
    )


def test_threshold_scan_keeps_lowest_observation_as_left_censored_bound():
    maps = _scan(ConstantDamageRegressor(), [250.0, 500.0, 1000.0])
    assert maps[DK_GRADE_NAMES[1]][0, 0] == 250.0
    assert maps[DK_GRADE_NAMES[3]][0, 0] == 250.0


def test_threshold_scan_interpolates_only_inside_observed_flux_bracket():
    maps = _scan(LinearFluxDamageRegressor(), [250.0, 500.0, 1000.0, 5000.0])
    # Dk=0.04 is crossed between q=250 and q=500 at q=400.
    assert maps[DK_GRADE_NAMES[1]][0, 0] == pytest.approx(400.0)


def test_all_observed_no_damage_facility_does_not_create_threshold_figure(tmp_path):
    facility_root = tmp_path / "cases" / "sample"
    facility_root.mkdir(parents=True)
    (facility_root / "sample.fds").write_text(
        "&HEAD CHID='sample'/\n&MESH IJK=1,1,1, XB=0,1,0,1,0,1/\n",
        encoding="utf-8",
    )
    df = pd.DataFrame(
        [
            {
                "facility_name": "sample",
                "fds_file": "sample.fds",
                "heat_flux_kw_m2": 1000.0,
                "Dk": 0.0,
            }
        ]
    )

    rows, figures = _generate_threshold_heatmaps(
        ConstantDamageRegressor(),
        df,
        facility_root.parent,
        {"sample": 0},
        ("facility_oh_sample",),
        tmp_path / "figures",
        max_flux=2000.0,
        flux_points=2,
        azimuth_step=360.0,
        elevation_step=60.0,
        max_facilities=None,
    )

    assert len(rows) == 9
    assert figures == []
    assert {row["scan_min_flux"] for row in rows} == {100.0}
    assert {row["scan_limit_flux"] for row in rows} == {2000.0}
    assert all(row["plot_omitted_no_observed_damage"] for row in rows)
    assert not list((tmp_path / "figures").rglob("threshold_grid_*.png"))
