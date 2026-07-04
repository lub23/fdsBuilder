"""Tests for models.heat_source.face_fluxes.

Compass convention (clockwise from east):
    azimuth = 0°   → XMAX (east)
    azimuth = 90°  → YMIN (south)
    azimuth = 180° → XMIN (west)
    azimuth = 270° → YMAX (north)
"""
import math
import pytest
from models.heat_source import face_fluxes, source_orientation, rad_wall_for_azimuth
from models.window_flux_calibration import fit_for_duration, q_avg_to_q_set


def _close(d1, d2, tol=1e-6):
    """Dict float-compare."""
    if set(d1) != set(d2):
        return False
    return all(abs(d1[k] - d2[k]) < tol for k in d1)


class TestFaceFluxes:
    def test_azimuth_0_elevation_0_single_face_xmax(self):
        assert _close(face_fluxes(0, 0, 20.0), {"XMAX": 20.0})

    def test_azimuth_90_single_face_ymin(self):
        assert _close(face_fluxes(90, 0, 20.0), {"YMIN": 20.0})

    def test_azimuth_180_single_face_xmin(self):
        assert _close(face_fluxes(180, 0, 20.0), {"XMIN": 20.0})

    def test_azimuth_270_single_face_ymax(self):
        assert _close(face_fluxes(270, 0, 20.0), {"YMAX": 20.0})

    def test_azimuth_360_wraps_to_xmax(self):
        assert _close(face_fluxes(360, 0, 20.0), {"XMAX": 20.0})

    def test_azimuth_45_splits_xmax_ymin_equally(self):
        result = face_fluxes(45, 0, 20.0)
        expected = 20.0 * math.cos(math.radians(45))
        assert set(result) == {"XMAX", "YMIN"}
        assert abs(result["XMAX"] - expected) < 1e-6
        assert abs(result["YMIN"] - expected) < 1e-6

    def test_azimuth_135_splits_ymin_xmin(self):
        result = face_fluxes(135, 0, 20.0)
        expected = 20.0 * math.cos(math.radians(45))
        assert set(result) == {"YMIN", "XMIN"}
        assert abs(result["YMIN"] - expected) < 1e-6
        assert abs(result["XMIN"] - expected) < 1e-6

    def test_azimuth_225_splits_xmin_ymax(self):
        result = face_fluxes(225, 0, 20.0)
        assert set(result) == {"XMIN", "YMAX"}

    def test_azimuth_315_splits_ymax_xmax(self):
        result = face_fluxes(315, 0, 20.0)
        assert set(result) == {"YMAX", "XMAX"}

    def test_elevation_adds_zmax(self):
        result = face_fluxes(0, 30, 20.0)
        assert "ZMAX" in result
        assert abs(result["ZMAX"] - 20.0 * math.sin(math.radians(30))) < 1e-6
        assert abs(result["XMAX"] - 20.0 * math.cos(math.radians(30))) < 1e-6

    def test_elevation_60_distributes(self):
        result = face_fluxes(45, 60, 20.0)
        cos_e = math.cos(math.radians(60))
        sin_e = math.sin(math.radians(60))
        cos_a = math.cos(math.radians(45))
        sin_a = math.sin(math.radians(45))
        assert abs(result["ZMAX"] - 20.0 * sin_e) < 1e-6
        assert abs(result["XMAX"] - 20.0 * cos_e * cos_a) < 1e-6
        assert abs(result["YMIN"] - 20.0 * cos_e * sin_a) < 1e-6

    def test_zero_flux(self):
        assert face_fluxes(0, 0, 0.0) == {}

    def test_azimuth_wraps_negative(self):
        r1 = face_fluxes(-5, 0, 20.0)
        r2 = face_fluxes(355, 0, 20.0)
        assert _close(r1, r2)

    def test_primary_secondary_energy_conservation(self):
        r = face_fluxes(37, 23, 20.0)
        total = sum(v**2 for v in r.values())
        assert abs(total - 20.0**2) < 1e-4


class TestSourceOrientation:
    """Test the unit-vector returned by source_orientation()."""

    def test_az_0_points_to_xmax(self):
        sx, sy, sz = source_orientation(0, 0)
        assert sx == pytest.approx(1.0, abs=1e-9)
        assert sy == pytest.approx(0.0, abs=1e-9)
        assert sz == pytest.approx(0.0, abs=1e-9)

    def test_az_90_points_to_ymin(self):
        sx, sy, _ = source_orientation(90, 0)
        assert sx == pytest.approx(0.0, abs=1e-9)
        assert sy == pytest.approx(-1.0, abs=1e-9)

    def test_az_180_points_to_xmin(self):
        sx, sy, _ = source_orientation(180, 0)
        assert sx == pytest.approx(-1.0, abs=1e-9)
        assert sy == pytest.approx(0.0, abs=1e-9)

    def test_az_270_points_to_ymax(self):
        sx, sy, _ = source_orientation(270, 0)
        assert sx == pytest.approx(0.0, abs=1e-9)
        assert sy == pytest.approx(1.0, abs=1e-9)

    def test_elevation_90_straight_up(self):
        sx, sy, sz = source_orientation(45, 90)
        assert abs(sx) < 1e-9 and abs(sy) < 1e-9
        assert sz == pytest.approx(1.0, abs=1e-9)


class TestRadWallForAzimuth:
    def test_cardinal(self):
        assert rad_wall_for_azimuth(0) == "x_max"
        assert rad_wall_for_azimuth(90) == "y_min"
        assert rad_wall_for_azimuth(180) == "x_min"
        assert rad_wall_for_azimuth(270) == "y_max"

    def test_intercardinal_snaps(self):
        assert rad_wall_for_azimuth(44) == "x_max"
        assert rad_wall_for_azimuth(134) == "y_min"
        assert rad_wall_for_azimuth(224) == "x_min"
        assert rad_wall_for_azimuth(314) == "y_max"

    def test_negative_wraps(self):
        assert rad_wall_for_azimuth(-90) == "y_max"
        assert rad_wall_for_azimuth(450) == "y_min"


class TestWindowFluxCalibration:
    def test_qavg_to_qset_uses_duration_1_36_fit(self):
        assert q_avg_to_q_set(20000.0, 1.36) == pytest.approx(32059.5, rel=2e-5)

    def test_qavg_to_qset_uses_duration_2_1_fit(self):
        assert q_avg_to_q_set(20000.0, 2.1) == pytest.approx(21800.0, rel=2e-5)

    def test_qavg_to_qset_uses_duration_7_5_fit(self):
        assert q_avg_to_q_set(20000.0, 7.5) == pytest.approx(8724.18, rel=2e-5)

    def test_fit_for_duration_uses_nearest_calibrated_duration(self):
        assert fit_for_duration(2.0).duration == pytest.approx(2.1)
