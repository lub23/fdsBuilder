"""Integration: FDSGenerator heat-source with multi-face fixed-temperature radiation.

Scheme (2026-06-12):
- Per-face radiation SURFs named 'radiation_{FACE}' with TMP_FRONT = equilibrium
  blackbody temperature computed from face flux via T = (flux / εσ)^¼.
  Matches FDS back_wall_test_2.fds pattern: TAU_T=0.0, HEAT_TRANSFER_COEFFICIENT=0.0,
  EMISSIVITY=1.0. No MATL_ID required (direct temperature boundary).
- Optional &DEVC ID='TIMER->OUT' (no SETVAL) when duration > 0.
- Six &VENT ID='Domain Vent [<FACE>]' blocks, XB on the MESH domain boundary.
  Faces with non-zero flux get SURF_ID='radiation_{FACE}', others get 'OPEN'.
"""
import re
import math
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
        heat_source={"azimuth": azimuth, "elevation": elevation, "net_heat_flux": flux_mw * 1000, "duration": duration},
    )


_SURF_PATTERN = re.compile(
    r"&SURF ID='(radiation_[^']+)',[^/]*?TMP_FRONT=([\d.\-]+)"
)
_VENT_PATTERN = re.compile(
    r"&VENT ID='Domain Vent \[(XMIN|XMAX|YMIN|YMAX|ZMIN|ZMAX)\]',\s*"
    r"SURF_ID='([^']+)',\s*"
    r"(?:DEVC_ID='[^']+',\s*)?"
    r"XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)\s*/"
)


def _face_fluxes(fds: str) -> dict[str, float]:
    """Extract per-face flux from generated FDS text via TMP_FRONT → flux (εσT⁴)."""
    SIGMA_SB = 5.670374419e-11
    out = {}
    for m in _SURF_PATTERN.finditer(fds):
        face = m.group(1).replace("radiation_", "")
        t = float(m.group(2))
        # Reverse: flux = εσT⁴ (emissivity=1.0)
        out[face] = t ** 4 * SIGMA_SB
    return out


def _vents(fds: str):
    out = []
    for m in _VENT_PATTERN.finditer(fds):
        out.append({
            "face": m.group(1),
            "surf_id": m.group(2),
            "xb": tuple(float(m.group(i)) for i in range(3, 9)),
        })
    return out


class TestHeatSourceFDS:
    def test_surf_flux_via_temp_front_in_kw_from_mw(self):
        bg = _bg(0, 0, flux_mw=3.0)
        fds = FDSGenerator(bg).generate()
        surfs = _face_fluxes(fds)
        # azimuth=0 elevation=0 → YMAX=3000 kW/m² → TEMP_FRONT ≈ 2675K → back to flux
        assert abs(surfs.get("YMAX", 0) - 3000.0) < 0.5

    def test_surf_flux_via_temp_front_small_mw(self):
        bg = _bg(0, 0, flux_mw=0.05)
        fds = FDSGenerator(bg).generate()
        surfs = _face_fluxes(fds)
        assert abs(surfs.get("YMAX", 0) - 50.0) < 0.5

    def test_six_domain_vents_emitted(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        faces = {v["face"] for v in vents}
        assert faces == {"XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"}

    def test_azimuth_0_radiation_on_ymax_others_open(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        rads = [v for v in vents if v["surf_id"] == "radiation_YMAX"]
        opens = [v for v in vents if v["surf_id"] == "OPEN"]
        assert len(rads) == 1
        assert len(opens) == 5
        assert rads[0]["face"] == "YMAX"

    def test_azimuth_90_radiation_on_xmax(self):
        bg = _bg(90, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        rads = [v for v in vents if v["surf_id"] == "radiation_XMAX"]
        assert len(rads) == 1
        assert rads[0]["face"] == "XMAX"

    def test_azimuth_180_radiation_on_ymin(self):
        bg = _bg(180, 0)
        fds = FDSGenerator(bg).generate()
        rads = [v for v in _vents(fds) if v["surf_id"] == "radiation_YMIN"]
        assert len(rads) == 1
        assert rads[0]["face"] == "YMIN"

    def test_azimuth_270_radiation_on_xmin(self):
        bg = _bg(270, 0)
        fds = FDSGenerator(bg).generate()
        rads = [v for v in _vents(fds) if v["surf_id"] == "radiation_XMIN"]
        assert len(rads) == 1
        assert rads[0]["face"] == "XMIN"

    def test_elevation_60_radiation_on_zmax(self):
        bg = _bg(0, 60)
        fds = FDSGenerator(bg).generate()
        rads = [v for v in _vents(fds) if v["surf_id"] == "radiation_ZMAX"]
        assert len(rads) == 1
        assert rads[0]["face"] == "ZMAX"

    def test_elevation_45_bisects_ymax_xmax_zmax(self):
        import math
        bg = _bg(45, 45)
        fds = FDSGenerator(bg).generate()
        surfs = _face_fluxes(fds)
        Q = 3000.0
        cos_e = math.cos(math.radians(45))
        sin_e = math.sin(math.radians(45))
        cos_a = math.cos(math.radians(45))
        sin_a = math.sin(math.radians(45))
        assert abs(surfs["YMAX"] - Q * cos_e * cos_a) < 0.5
        assert abs(surfs["XMAX"] - Q * cos_e * sin_a) < 0.5
        assert abs(surfs["ZMAX"] - Q * sin_e) < 0.5

    def test_vent_xb_matches_mesh_boundary_not_facility(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        zmin_vent = next(v for v in vents if v["face"] == "ZMIN")
        xb = zmin_vent["xb"]
        assert xb[4] == xb[5]
        assert xb[0] <= -1.0
        assert xb[1] >= 21.0
        assert xb[2] <= -1.0
        assert xb[3] >= 11.0

    def test_ymax_radiation_vent_xb_on_mesh_y_max(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        rad = next(v for v in _vents(fds) if v["surf_id"] == "radiation_YMAX")
        xb = rad["xb"]
        assert xb[2] == xb[3]
        assert xb[2] > 10.0

    def test_timer_devc_emitted_without_setval_when_duration_positive(self):
        bg = _bg(0, 0, duration=1.36)
        fds = FDSGenerator(bg).generate()
        assert "&DEVC ID='TIMER->OUT'" in fds
        assert "SETPOINT=1.36" in fds
        assert "INITIAL_STATE=.TRUE." in fds
        assert "SETVAL=" not in fds

    def test_no_timer_devc_when_duration_zero(self):
        bg = _bg(0, 0, duration=0)
        fds = FDSGenerator(bg).generate()
        assert "&DEVC ID='TIMER->OUT'" not in fds

    def test_radiation_vent_carries_timer_devc_id(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        assert "DEVC_ID='TIMER->OUT'" in fds

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
    """Per-item DEVC probes: thermocouples for burnable fuel, heat-flux
    gauges for inert targets (non-burnable combustibles + components)."""

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

    def _bg_with_component(self, key):
        fc = FireCompartment(
            name="FC1",
            boundary=[0, 40, 0, 40],
            specialized_components=[{"key": key, "count": 1}],
        )
        b = Building(
            name="T",
            cn_name="T",
            boundary=[0, 40, 0, 40],
            wall_thickness=0.24,
            height=25.0,
            stories=[Story(name="1F", height=25.0, fire_compartments=[fc], roof=Roof())],
        )
        b.update_z_offsets()
        return BuildingGroup(
            buildings=[b],
            heat_source={"azimuth": 0, "elevation": 0, "net_heat_flux": 3.0, "duration": 1.36},
        )

    def test_metal_combustible_emits_temperature_and_heat_flux(self):
        # METAL_PARTS is inert; it still gets BOTH probes above it.
        bg = self._bg_with_combustible("METAL_PARTS")
        fds = FDSGenerator(bg).generate()
        assert "ID='T_METAL_PARTS_B0S0_000'" in fds
        assert "ID='HF_METAL_PARTS_B0S0_000'" in fds
        # The HF gauge block carries the gas heat-flux quantity + ORIENTATION.
        block = fds.split("ID='HF_METAL_PARTS_B0S0_000'")[0].rsplit("&DEVC", 1)[1]
        assert "RADIATIVE HEAT FLUX GAS" in block
        assert "ORIENTATION=0.000,1.000,0.000" in block

    def test_burnable_combustible_emits_temperature_and_heat_flux(self):
        # Burnable fuel now also gets TWO probes: gas temperature + heat flux.
        bg = self._bg_with_combustible("WOODEN_PALLET")
        fds = FDSGenerator(bg).generate()
        t_line = next(
            ln for ln in fds.splitlines()
            if "&DEVC" in ln and "ID='T_WOODEN_PALLET_B0S0_000'" in ln
        )
        assert "QUANTITY='TEMPERATURE'" in t_line
        assert "ID='HF_WOODEN_PALLET_B0S0_000'" in fds

    def test_no_devc_uses_wall_temperature(self):
        # The per-item thermocouple (WALL TEMPERATURE DEVC) is gone; only the
        # BNDF output may still reference that quantity.
        bg = self._bg_with_combustible("WOODEN_PALLET")
        fds = FDSGenerator(bg).generate()
        assert not any(
            "&DEVC" in ln and "WALL TEMPERATURE" in ln
            for ln in fds.splitlines()
        )

    def test_specialized_component_emits_heat_flux_probe(self):
        # Single-metal components are inert targets -> heat-flux gauge, no TC.
        bg = self._bg_with_component("ROCKET_VEHICLE_LARGE")
        fds = FDSGenerator(bg).generate()
        assert "ID='HF_ROCKET_VEHICLE_LARGE_B0S0_000'" in fds
        assert "RADIATIVE HEAT FLUX GAS" in fds
        # The component is aluminium only (no propellant / glass surfaces).
        assert "SOLID_PROPELLANT" not in fds

    def test_probe_ids_are_unique(self):
        # Multiple fire compartments + components must not collide.
        fcs = [
            FireCompartment(name="FC1", boundary=[0, 20, 0, 20],
                            combustibles=[{"key": "WOODEN_PALLET", "count": 5},
                                          {"key": "METAL_PARTS", "count": 3}]),
            FireCompartment(name="FC2", boundary=[20, 40, 0, 20],
                            combustibles=[{"key": "WOODEN_PALLET", "count": 5},
                                          {"key": "CABLE_BUNDLE", "count": 4}]),
        ]
        b = Building(name="T", cn_name="T", boundary=[0, 40, 0, 20],
                     wall_thickness=0.24, height=6.0,
                     stories=[Story(name="1F", height=6.0, fire_compartments=fcs, roof=Roof())])
        b.update_z_offsets()
        bg = BuildingGroup(buildings=[b],
                           heat_source={"azimuth": 0, "elevation": 0,
                                        "net_heat_flux": 3.0, "duration": 1.36})
        fds = FDSGenerator(bg).generate()
        ids = re.findall(r"\bID='([^']+)'", fds)
        dups = {i for i in ids if ids.count(i) > 1}
        assert not dups, f"duplicate IDs: {sorted(dups)}"

