"""Integration: FDSGenerator heat-source multi-face output."""
import re
import pytest
from models.building import Building, BuildingGroup, Story, FireCompartment, Roof
from generators.fds_generator import FDSGenerator


def _bg(azimuth, elevation, flux_kw=20.0):
    b = Building(
        name="T",
        cn_name="T",
        boundary=[0, 20, 0, 10],
        wall_thickness=0.24,
        height=5.0,
        stories=[Story(name="1F", height=5.0,
                       fire_compartments=[FireCompartment(name="FC1", boundary=[0, 20, 0, 10])],
                       roof=Roof())],
    )
    b.update_z_offsets()
    return BuildingGroup(
        buildings=[b],
        heat_source={"azimuth": azimuth, "elevation": elevation,
                     "net_heat_flux": flux_kw, "duration": 1.36},
    )


def _count_heat_vents(fds: str):
    """Return list of (face_name, flux) tuples extracted from heat-source &VENT lines."""
    matches = []
    for m in re.finditer(r"SURF_ID='HEAT_SOURCE_(\w+)'", fds):
        face = m.group(1)
        # Find the matching &SURF line for its NET_HEAT_FLUX
        surf_pattern = rf"&SURF ID='HEAT_SOURCE_{face}'[^/]*NET_HEAT_FLUX=([\d\.\-]+)"
        sm = re.search(surf_pattern, fds)
        if sm:
            matches.append((face, float(sm.group(1))))
    return matches


class TestHeatSourceFDS:
    def test_azimuth_0_single_ymax_face(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _count_heat_vents(fds)
        assert len(vents) == 1
        assert vents[0][0] == "YMAX"
        assert abs(vents[0][1] - 20.0) < 1e-3

    def test_azimuth_45_splits_two_side_faces(self):
        bg = _bg(45, 0)
        fds = FDSGenerator(bg).generate()
        vents = _count_heat_vents(fds)
        faces = {v[0] for v in vents}
        assert faces == {"YMAX", "XMAX"}

    def test_elevation_adds_zmax(self):
        bg = _bg(0, 30)
        fds = FDSGenerator(bg).generate()
        vents = _count_heat_vents(fds)
        faces = {v[0] for v in vents}
        assert "ZMAX" in faces
        assert "YMAX" in faces

    def test_flux_value_is_kw_per_m2(self):
        bg = _bg(0, 0, flux_kw=12.5)
        fds = FDSGenerator(bg).generate()
        vents = _count_heat_vents(fds)
        assert abs(vents[0][1] - 12.5) < 1e-3
