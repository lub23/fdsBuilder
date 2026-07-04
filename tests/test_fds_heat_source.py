"""Integration: FDSGenerator heat-source with multi-face heat-flux radiation.

Scheme (2026-06-12):
- Per-face radiation SURFs named 'radiation_{FACE}' with NET_HEAT_FLUX
  converted from the UI target q_avg to calibrated q_set (kW/m²).
- Optional RAMP_Q='radiation_timer' when duration > 0.
- Boundary &VENT blocks are emitted per mesh when the default refinement strip
  is active. Faces with non-zero flux get SURF_ID='radiation_{FACE}', others
  get 'OPEN'.
"""
import re
import math
import pytest
from models.building import Building, BuildingGroup, Story, FireCompartment, Roof
from generators.fds_generator import FDSGenerator, HEAT_FLUX_PROBE_WALL_OFFSET
from models.window_flux_calibration import q_avg_to_q_set


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
    r"&SURF ID='(radiation_[^']+)',[^/]*?NET_HEAT_FLUX=([\d.\-]+)"
)
_VENT_PATTERN = re.compile(
    r"&VENT ID='(?:Domain|[^']+) Vent \[(XMIN|XMAX|YMIN|YMAX|ZMIN|ZMAX|ZMAX_TOP|ZMAX_OPEN_\d+)\]',\s*"
    r"SURF_ID='([^']+)',\s*"
    r"(?:DEVC_ID='[^']+',\s*)?"
    r"XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)\s*/"
)


def _face_fluxes(fds: str) -> dict[str, float]:
    """Extract per-face flux from generated FDS text.

    ``NET_HEAT_FLUX`` carries the face flux directly (kW/m²).
    """
    out = {}
    for m in _SURF_PATTERN.finditer(fds):
        face = m.group(1).replace("radiation_", "")
        out[face] = float(m.group(2))
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


def _mesh_domain(fds: str):
    meshes = re.findall(
        r"&MESH(?: ID='[^']+',)? IJK=\d+,\d+,\d+, "
        r"XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)"
        r"(?:, MPI_PROCESS=\d+)? /",
        fds,
    )
    assert meshes, "missing MESH lines"
    vals = [[float(v) for v in mesh] for mesh in meshes]
    return (
        min(v[0] for v in vals),
        max(v[1] for v in vals),
        min(v[2] for v in vals),
        max(v[3] for v in vals),
        min(v[4] for v in vals),
        max(v[5] for v in vals),
    )


class TestHeatSourceFDS:
    def test_surf_net_heat_flux_equals_calibrated_q_set_at_zero_elevation(self):
        bg = _bg(0, 0, flux_mw=3.0)  # UI target q_avg = 3000 kW/m2
        fds = FDSGenerator(bg).generate()
        surfs = _face_fluxes(fds)
        expected = q_avg_to_q_set(3000.0, 1.36)
        assert abs(surfs.get("XMAX", 0) - expected) < 1.0

    def test_surf_net_heat_flux_uses_qavg_fit_not_direct_ui_value(self):
        bg = _bg(0, 0, flux_mw=0.1)  # UI target q_avg = 100 kW/m2
        fds = FDSGenerator(bg).generate()
        surfs = _face_fluxes(fds)
        expected = q_avg_to_q_set(100.0, 1.36)
        assert abs(surfs.get("XMAX", 0) - expected) < 1.0
        assert surfs.get("XMAX", 0) != pytest.approx(100.0)

    def test_outer_boundary_vents_emitted_for_all_faces(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        faces = {v["face"] for v in vents}
        assert faces == {"XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"}

    def test_azimuth_0_radiation_on_xmax_others_open(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        rads = [v for v in vents if v["surf_id"] == "radiation_XMAX"]
        opens = [v for v in vents if v["surf_id"] == "OPEN"]
        assert len(rads) == 1
        assert opens
        assert rads[0]["face"] == "XMAX"

    def test_azimuth_90_radiation_on_ymin(self):
        bg = _bg(90, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        rads = [v for v in vents if v["surf_id"] == "radiation_YMIN"]
        assert len(rads) == 1
        assert rads[0]["face"] == "YMIN"

    def test_azimuth_180_radiation_on_xmin(self):
        bg = _bg(180, 0)
        fds = FDSGenerator(bg).generate()
        rads = [v for v in _vents(fds) if v["surf_id"] == "radiation_XMIN"]
        assert len(rads) == 1
        assert rads[0]["face"] == "XMIN"

    def test_azimuth_270_radiation_on_ymax(self):
        bg = _bg(270, 0)
        fds = FDSGenerator(bg).generate()
        rads = [v for v in _vents(fds) if v["surf_id"] == "radiation_YMAX"]
        assert len(rads) == 1
        assert rads[0]["face"] == "YMAX"

    def test_elevation_60_top_strip_vent_present(self):
        bg = _bg(0, 60)
        fds = FDSGenerator(bg).generate()
        rads = [v for v in _vents(fds) if v["surf_id"] == "radiation_ZMAX_TOP"]
        assert len(rads) == 1
        assert rads[0]["face"] == "ZMAX_TOP"

    def test_wall_flux_probe_orientation_remains_wall_normal_for_top_source(self):
        bg = _bg(0, 90)
        fds = FDSGenerator(bg).generate()
        block = re.search(r"&DEVC[^/]*ID='incident_heat_flux' /", fds, re.DOTALL)
        assert block, "missing incident_heat_flux probe"
        assert "QUANTITY='RADIATIVE HEAT FLUX GAS'" in block.group(0)
        assert "ORIENTATION=1.000,0.000,0.000" in block.group(0)
        assert "ORIENTATION=0.000,0.000,1.000" not in block.group(0)

    def test_elevation_45_flux_decomposes_to_side_and_top_faces(self):
        from models.heat_source import face_fluxes
        bg = _bg(45, 45)
        fds = FDSGenerator(bg).generate()
        surfs = _face_fluxes(fds)
        q_set = q_avg_to_q_set(3000.0, 1.36)
        expected = face_fluxes(45.0, 45.0, q_set)
        assert abs(surfs["XMAX"] - expected["XMAX"]) < 1.0
        assert abs(surfs["YMIN"] - expected["YMIN"]) < 1.0
        assert abs(surfs["ZMAX_TOP"] - expected["ZMAX"]) < 1.0

    def test_vent_xb_matches_mesh_boundary_not_facility(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        vents = _vents(fds)
        zmin_vents = [v for v in vents if v["face"] == "ZMIN"]
        assert zmin_vents
        for v in zmin_vents:
            assert v["xb"][4] == v["xb"][5]
        assert min(v["xb"][0] for v in zmin_vents) <= -1.0
        assert max(v["xb"][1] for v in zmin_vents) >= 21.0
        assert min(v["xb"][2] for v in zmin_vents) <= -1.0
        assert max(v["xb"][3] for v in zmin_vents) >= 11.0

    def test_ymax_radiation_vent_xb_on_mesh_y_max(self):
        bg = _bg(270, 0)
        fds = FDSGenerator(bg).generate()
        rad = next(v for v in _vents(fds) if v["surf_id"] == "radiation_YMAX")
        xb = rad["xb"]
        assert xb[2] == xb[3]
        assert xb[2] > 10.0

    def test_ramp_q_emitted_when_duration_positive(self):
        bg = _bg(0, 0, duration=1.36)
        fds = FDSGenerator(bg).generate()
        assert "RAMP_Q='radiation_timer'" in fds
        assert "&RAMP ID='radiation_timer', T=0.000, F=1.0 /" in fds
        assert "&RAMP ID='radiation_timer', T=1.360, F=1.0 /" in fds
        assert "&RAMP ID='radiation_timer', T=1.361, F=0.0 /" in fds
        assert "&DEVC ID='TIMER->OUT'" not in fds

    def test_clip_temperature_limits_emitted(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        assert "&CLIP MINIMUM_TEMPERATURE=20, MAXIMUM_TEMPERATURE=10000 /" in fds

    def test_no_ramp_q_when_duration_zero(self):
        bg = _bg(0, 0, duration=0)
        fds = FDSGenerator(bg).generate()
        assert "&DEVC ID='TIMER->OUT'" not in fds
        assert "RAMP_Q='radiation_timer'" not in fds

    def test_radiation_vent_not_timer_gated(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        assert "DEVC_ID='TIMER->OUT'" not in fds

    def test_open_vents_do_not_carry_devc_id(self):
        bg = _bg(0, 0)
        fds = FDSGenerator(bg).generate()
        open_lines = [
            ln for ln in fds.splitlines()
            if "SURF_ID='OPEN'" in ln and " Vent " in ln
        ]
        assert open_lines, "expected at least one OPEN Domain Vent"
        for ln in open_lines:
            assert "DEVC_ID=" not in ln, ln

    def test_grid_2_forces_exact_one_meter_xmax_source_gap_and_probe(self):
        bg = _bg(0, 0)
        bg.domain["grid_size"] = 2.0
        fds = FDSGenerator(bg).generate()
        x0, x1, y0, y1, z0, z1 = _mesh_domain(fds)

        wall_xmax = 20.0 + 0.24 / 2
        assert x1 - wall_xmax == pytest.approx(1.0)
        assert "ID='MeshRefined'" in fds

        m = re.search(
            r"&DEVC XYZ=([^,]+),([^,]+),([^,]+),[^/]*?ID='incident_heat_flux'",
            fds,
            re.S,
        )
        assert m, "missing incident_heat_flux probe"
        px, py, pz = [float(v.strip()) for v in m.groups()]
        assert px == pytest.approx(x1 - 1.0 + HEAT_FLUX_PROBE_WALL_OFFSET)
        assert py == pytest.approx((y0 + y1) / 2)
        assert pz == pytest.approx((z0 + z1) / 2)

    def test_ymin_wall_flux_probe_is_offset_into_source_side_gas(self):
        bg = _bg(90, 0)
        bg.domain["grid_size"] = 2.0
        fds = FDSGenerator(bg).generate()
        x0, x1, y0, y1, z0, z1 = _mesh_domain(fds)

        m = re.search(
            r"&DEVC XYZ=([^,]+),([^,]+),([^,]+),[^/]*?ID='incident_heat_flux'",
            fds,
            re.S,
        )
        assert m, "missing incident_heat_flux probe"
        px, py, pz = [float(v.strip()) for v in m.groups()]
        assert px == pytest.approx((x0 + x1) / 2)
        assert py == pytest.approx(y0 + 1.0 - HEAT_FLUX_PROBE_WALL_OFFSET)
        assert pz == pytest.approx((z0 + z1) / 2)

    def test_grid_2_top_source_strip_is_one_meter_and_ceiling_is_zmax_minus_one(self):
        bg = _bg(0, 60)
        bg.domain["grid_size"] = 2.0
        fds = FDSGenerator(bg).generate()
        _x0, x1, _y0, _y1, _z0, z1 = _mesh_domain(fds)

        ceiling_z = 5.0
        assert z1 - ceiling_z == pytest.approx(1.0)

        top = next(
            ln for ln in fds.splitlines()
            if "SURF_ID='radiation_ZMAX_TOP'" in ln
        )
        m = re.search(
            r"XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)",
            top,
        )
        assert m, top
        tx1, tx2, _ty1, _ty2, tz1, tz2 = [float(m.group(i)) for i in range(1, 7)]
        assert tx2 - tx1 == pytest.approx(1.0)
        assert tx2 == pytest.approx(x1)
        assert tz1 == pytest.approx(z1)
        assert tz2 == pytest.approx(z1)

    def test_grid_2_diagonal_azimuth_keeps_both_side_radiation_faces(self):
        bg = _bg(45, 0)
        bg.domain["grid_size"] = 2.0
        fds = FDSGenerator(bg).generate()
        assert "SURF_ID='radiation_XMAX'" in fds
        assert "SURF_ID='radiation_YMIN'" in fds


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
            name="总装主厂区",
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
        # The HF gauge block carries the gas heat-flux quantity + ORIENTATION
        # pointing toward the source.  azimuth=0, elevation=0 -> (1, 0, 0).
        block = fds.split("ID='HF_METAL_PARTS_B0S0_000'")[0].rsplit("&DEVC", 1)[1]
        assert "RADIATIVE HEAT FLUX GAS" in block
        assert "ORIENTATION=1.000,0.000,0.000" in block

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

    def test_wall_heat_flux_probe_is_first_device_column(self):
        bg = self._bg_with_combustible("WOODEN_PALLET")
        fds = FDSGenerator(bg).generate()
        first_devc = re.search(r"&DEVC[^/]*ID='([^']+)' /", fds, re.S)
        assert first_devc is not None
        assert first_devc.group(1) == "incident_heat_flux"

    def test_burnable_combustible_surface_uses_hrrpua_not_pyro_matl(self):
        bg = self._bg_with_combustible("CABLE_BUNDLE")
        fds = FDSGenerator(bg).generate()
        surf_block = fds.split("&SURF ID='SURF_CABLE_BUNDLE'", 1)[1].split("/", 1)[0]

        assert "HRRPUA=600" in surf_block
        assert "IGNITION_TEMPERATURE=360.0" in surf_block
        assert "BURN_AWAY=.TRUE." in surf_block
        assert "MATL_ID='PYRO_CABLE_BUNDLE'" in surf_block
        assert "BULK_DENSITY" not in surf_block
        matl_block = fds.split("&MATL ID='PYRO_CABLE_BUNDLE'", 1)[1].split("/", 1)[0]
        assert "DENSITY=1200" in matl_block
        assert "HEAT_OF_REACTION" not in fds
        assert "NU_SPEC" not in fds
        assert "SPEC_ID" not in fds
        assert "REFERENCE_TEMPERATURE" not in fds

    def test_no_devc_uses_wall_temperature(self):
        # The per-item thermocouple (WALL TEMPERATURE DEVC) is gone; only the
        # BNDF output may still reference that quantity.
        bg = self._bg_with_combustible("WOODEN_PALLET")
        fds = FDSGenerator(bg).generate()
        assert not any(
            "&DEVC" in ln and "WALL TEMPERATURE" in ln
            for ln in fds.splitlines()
        )

    def test_specialized_component_emits_both_probes(self):
        # Single-metal components are inert targets -> two probes (T + HF).
        bg = self._bg_with_component("ROCKET_VEHICLE_LARGE")
        fds = FDSGenerator(bg).generate()
        assert "ID='T_ROCKET_VEHICLE_LARGE_B0S0_000'" in fds
        assert "ID='HF_ROCKET_VEHICLE_LARGE_B0S0_000'" in fds
        assert "RADIATIVE HEAT FLUX GAS" in fds
        # The component is aluminium only (no propellant / glass surfaces).
        assert "SOLID_PROPELLANT" not in fds

    def test_component_orientation_y_rotates_footprint(self):
        fc = FireCompartment(
            name="电解跨",
            boundary=[0, 20, 0, 80],
            specialized_components=[
                {"key": "POT_TENDING_MACHINE", "count": 1, "orientation": "y"}
            ],
        )
        b = Building(
            name="T",
            cn_name="T",
            boundary=[0, 20, 0, 80],
            wall_thickness=0.24,
            height=12.0,
            stories=[Story(name="1F", height=12.0, fire_compartments=[fc], roof=Roof())],
        )
        b.update_z_offsets()
        bg = BuildingGroup(
            buildings=[b],
            heat_source={"azimuth": 0, "elevation": 0, "net_heat_flux": 3.0, "duration": 1.36},
        )

        fds = FDSGenerator(bg).generate()
        m = re.search(
            r"&OBST XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),"
            r"[\d.\-]+,[\d.\-]+,[^/]*ID='POT_TENDING_MACHINE_B0S0_000_0'",
            fds,
            re.S,
        )

        assert m is not None
        x1, x2, y1, y2 = (float(m.group(i)) for i in range(1, 5))
        assert y2 - y1 == pytest.approx(36.0, abs=0.05)
        assert y2 - y1 > x2 - x1

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
        ids = re.findall(r"&DEVC[^/]*\bID='([^']+)'", fds, re.S)
        dups = {i for i in ids if ids.count(i) > 1}
        assert not dups, f"duplicate IDs: {sorted(dups)}"
