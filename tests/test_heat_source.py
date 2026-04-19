"""Tests for models.heat_source.face_fluxes."""
import math
import pytest
from models.heat_source import face_fluxes


def _close(d1, d2, tol=1e-6):
    """Dict float-compare."""
    if set(d1) != set(d2):
        return False
    return all(abs(d1[k] - d2[k]) < tol for k in d1)


class TestFaceFluxes:
    def test_azimuth_0_elevation_0_single_face_ymax(self):
        assert _close(face_fluxes(0, 0, 20.0), {"YMAX": 20.0})

    def test_azimuth_90_single_face_xmax(self):
        assert _close(face_fluxes(90, 0, 20.0), {"XMAX": 20.0})

    def test_azimuth_180_single_face_ymin(self):
        assert _close(face_fluxes(180, 0, 20.0), {"YMIN": 20.0})

    def test_azimuth_270_single_face_xmin(self):
        assert _close(face_fluxes(270, 0, 20.0), {"XMIN": 20.0})

    def test_azimuth_360_wraps_to_ymax(self):
        assert _close(face_fluxes(360, 0, 20.0), {"YMAX": 20.0})

    def test_azimuth_45_splits_ymax_xmax_equally(self):
        result = face_fluxes(45, 0, 20.0)
        expected = 20.0 * math.cos(math.radians(45))
        assert set(result) == {"YMAX", "XMAX"}
        assert abs(result["YMAX"] - expected) < 1e-6
        assert abs(result["XMAX"] - expected) < 1e-6

    def test_azimuth_135_splits_xmax_ymin(self):
        result = face_fluxes(135, 0, 20.0)
        expected = 20.0 * math.cos(math.radians(45))
        assert set(result) == {"XMAX", "YMIN"}
        assert abs(result["XMAX"] - expected) < 1e-6
        assert abs(result["YMIN"] - expected) < 1e-6

    def test_azimuth_225_splits_ymin_xmin(self):
        result = face_fluxes(225, 0, 20.0)
        assert set(result) == {"YMIN", "XMIN"}

    def test_azimuth_315_splits_xmin_ymax(self):
        result = face_fluxes(315, 0, 20.0)
        assert set(result) == {"XMIN", "YMAX"}

    def test_elevation_adds_zmax(self):
        result = face_fluxes(0, 30, 20.0)
        assert "ZMAX" in result
        assert abs(result["ZMAX"] - 20.0 * math.sin(math.radians(30))) < 1e-6
        assert abs(result["YMAX"] - 20.0 * math.cos(math.radians(30))) < 1e-6

    def test_elevation_60_distributes(self):
        result = face_fluxes(45, 60, 20.0)
        cos_e = math.cos(math.radians(60))
        sin_e = math.sin(math.radians(60))
        cos_a = math.cos(math.radians(45))
        sin_a = math.sin(math.radians(45))
        assert abs(result["ZMAX"] - 20.0 * sin_e) < 1e-6
        assert abs(result["YMAX"] - 20.0 * cos_e * cos_a) < 1e-6
        assert abs(result["XMAX"] - 20.0 * cos_e * sin_a) < 1e-6

    def test_zero_flux(self):
        assert face_fluxes(0, 0, 0.0) == {}

    def test_azimuth_wraps_negative(self):
        # -5° should behave like 355°
        r1 = face_fluxes(-5, 0, 20.0)
        r2 = face_fluxes(355, 0, 20.0)
        assert _close(r1, r2)

    def test_primary_secondary_energy_conservation(self):
        # primary^2 + secondary^2 + zmax^2 == Q^2
        r = face_fluxes(37, 23, 20.0)
        total = sum(v**2 for v in r.values())
        assert abs(total - 20.0**2) < 1e-4
