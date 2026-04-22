"""Integration: FDSGenerator heat-source with 6 MESH-boundary VENTs.

New scheme (2026-04-19):
- One `&SURF ID='radiation'` with NET_HEAT_FLUX = internal Q (MW/m²) × 1000 (→ kW/m²).
- Optional `&DEVC ID='TIMER->OUT'` (no SETVAL) when duration > 0.
- Six `&VENT ID='Mesh Vent: Mesh01 [<FACE>]'` blocks, XB on the MESH domain
  boundary. One face (determined by azimuth/elevation) gets SURF_ID='radiation',
  the other five get SURF_ID='OPEN'.
"""
import re
import pytest
from models.building import Building, BuildingGroup, Story, FireCompartment, Roof
from generators.fds_generator import FDSGenerator


def _bg(azimuth, elevation, flux_mw=3.0, duration=1.36):
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
                     "net_heat_flux": flux_mw, "duration": duration},
    )


_SURF_PATTERN = re.compile(
    r"&SURF ID='radiation',\s*\n\s*NET_HEAT_FLUX=([\d.\-]+)",
)
_VENT_PATTERN = re.compile(
    r"&VENT ID='(Mesh Vent: Mesh\d+|Domain Vent) \[(XMIN|XMAX|YMIN|YMAX|ZMIN|ZMAX)\]',\s*"
    r"SURF_ID='([^']+)',\s*"
    r"(?:DEVC_ID='[^']+',\s*)?"
    r"XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)\s*/"
)


def _surf_flux_kw(fds: str):
    m = _SURF_PATTERN.search(fds)
    return float(m.group(1)) if m else None


def _vents(fds: str):
    out = []
    for m in _VENT_PATTERN.finditer(fds):
        out.append({
            "face": m.group(2),
            "surf_id": m.group(3),
            "xb": tuple(float(m.group(i)) for i in range(4, 10)),
        })
    return out


class TestHeatSourceFDS:
    def test_surf_net_heat_flux_in_kw_converts_from_mw(self):
        # Internal 3.0 MW/m² → FDS 3000.0 kW/m²
        bg = _bg(0, 0, flux_mw=3.0)
        fds = FDSGenerator(bg).generate()
        assert _surf_flux_kw(fds) == pytest.approx(3000.0, abs=0.1)

    def test_surf_net_heat_flux_converts_small_mw(self):
        bg = _bg(0, 0, flux_mw=0.05)
        fds = FDSGenerator(bg).generate()
        assert _surf_flux_kw(fds) == pytest.approx(50.0, abs=0.1)

    def test_six_mesh_vents_emitted(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        faces = {v["face"] for v in vents}
        assert faces == {"XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"}

    def test_azimuth_0_radiation_on_ymax_others_open(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        rad = [v for v in vents if v["surf_id"] == "radiation"]
        opens = [v for v in vents if v["surf_id"] == "OPEN"]
        assert len(rad) == 1
        assert len(opens) == 5
        assert rad[0]["face"] == "YMAX"

    def test_azimuth_90_radiation_on_xmax(self):
        bg = _bg(90, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        rad = [v for v in vents if v["surf_id"] == "radiation"]
        assert len(rad) == 1
        assert rad[0]["face"] == "XMAX"

    def test_azimuth_180_radiation_on_ymin(self):
        bg = _bg(180, 0)
        fds = FDSGenerator(bg).generate()
        rad = [v for v in _vents(fds) if v["surf_id"] == "radiation"]
        assert len(rad) == 1
        assert rad[0]["face"] == "YMIN"

    def test_azimuth_270_radiation_on_xmin(self):
        bg = _bg(270, 0)
        fds = FDSGenerator(bg).generate()
        rad = [v for v in _vents(fds) if v["surf_id"] == "radiation"]
        assert len(rad) == 1
        assert rad[0]["face"] == "XMIN"

    def test_elevation_60_radiation_on_zmax(self):
        bg = _bg(0, 60)
        fds = FDSGenerator(bg).generate()
        rad = [v for v in _vents(fds) if v["surf_id"] == "radiation"]
        assert len(rad) == 1
        assert rad[0]["face"] == "ZMAX"

    def test_vent_xb_matches_mesh_boundary_not_facility(self):
        # facility bbox is x:[0,20] y:[0,10] z:[0,5]; MESH adds expand ≥2m.
        # Verify a non-radiation VENT (ZMIN) sits on mesh XB, not facility.
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        zmin_vent = next(v for v in vents if v["face"] == "ZMIN")
        xb = zmin_vent["xb"]
        # ZMIN: x spans full mesh, y spans full mesh, z is degenerate at z0
        assert xb[4] == xb[5]  # thickness 0 in Z
        # Mesh x extent should at least include facility +/- expand (2 or 10%)
        assert xb[0] <= -1.0  # well below facility x_min=0
        assert xb[1] >= 21.0  # well above facility x_max=20
        assert xb[2] <= -1.0
        assert xb[3] >= 11.0

    def test_ymax_radiation_vent_xb_on_mesh_y_max(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        rad = next(v for v in _vents(fds) if v["surf_id"] == "radiation")
        xb = rad["xb"]
        # YMAX face: y is degenerate at mesh y_max (> facility y_max=10)
        assert xb[2] == xb[3]
        assert xb[2] > 10.0

    def test_timer_devc_emitted_without_setval_when_duration_positive(self):
        bg = _bg(0, 0, duration=1.36)
        fds = FDSGenerator(bg).generate()
        assert "&DEVC ID='TIMER->OUT'" in fds
        assert "SETPOINT=1.36" in fds
        assert "INITIAL_STATE=.TRUE." in fds
        # new reference drops SETVAL
        assert "SETVAL=" not in fds

    def test_no_timer_devc_when_duration_zero(self):
        bg = _bg(0, 0, duration=0)
        fds = FDSGenerator(bg).generate()
        assert "&DEVC ID='TIMER->OUT'" not in fds

    def test_radiation_vent_carries_timer_devc_id(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        rad_line = next(
            ln for ln in fds.splitlines() if "SURF_ID='radiation'" in ln
        )
        assert "DEVC_ID='TIMER->OUT'" in rad_line

    def test_open_vents_do_not_carry_devc_id(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        open_lines = [
            ln for ln in fds.splitlines()
            if "SURF_ID='OPEN'" in ln and "Domain Vent" in ln
        ]
        assert open_lines, "expected at least one OPEN Domain Vent"
        for ln in open_lines:
            assert "DEVC_ID=" not in ln, ln


class TestCombustibleProbes:
    """Per-combustible DEVC probes attached to each item's top face."""

    def _bg_with_combustible(self, key):
        fc = FireCompartment(
            name="FC1",
            boundary=[0, 20, 0, 10],
            combustibles=[{"key": key, "count": 1}],
        )
        b = Building(
            name="T",
            cn_name="T",
            boundary=[0, 20, 0, 10],
            wall_thickness=0.24,
            height=5.0,
            stories=[Story(name="1F", height=5.0, fire_compartments=[fc], roof=Roof())],
        )
        b.update_z_offsets()
        return BuildingGroup(
            buildings=[b],
            heat_source={"azimuth": 0, "elevation": 0, "net_heat_flux": 3.0, "duration": 1.36},
        )

    def test_metal_combustible_emits_radiative_heat_flux_probe(self):
        bg = self._bg_with_combustible("STEEL_PLATE")
        fds = FDSGenerator(bg).generate()
        probe = next(
            ln for ln in fds.splitlines()
            if "&DEVC" in ln and "STEEL_PLATE_01" in ln
        )
        assert "QUANTITY='RADIATIVE HEAT FLUX'" in probe
        assert "IOR=3" in probe
        assert "ORIENTATION" not in probe

    def test_non_metal_combustible_emits_wall_temperature_probe(self):
        bg = self._bg_with_combustible("WOODEN_PALLET")
        fds = FDSGenerator(bg).generate()
        probe = next(
            ln for ln in fds.splitlines()
            if "&DEVC" in ln and "WOODEN_PALLET_01" in ln
        )
        assert "QUANTITY='WALL TEMPERATURE'" in probe
        assert "IOR=3" in probe
        assert "ORIENTATION" not in probe

    def test_probes_never_use_radiative_heat_flux_gas(self):
        # Option A contract: no gas-phase directional probes anywhere.
        bg = self._bg_with_combustible("STEEL_PLATE")
        fds = FDSGenerator(bg).generate()
        assert "RADIATIVE HEAT FLUX GAS" not in fds
