"""Tests for per-story SLCF slices + rocket FC-role placement.

Layout strategy (2026-06-19):
* Each story emits a TEMPERATURE + HRRPUV ``&SLCF`` slice at z = z_bottom + 2 m
  (subject to "no slice inside the roof slab").
* Rockets are placed in assembly fire compartments horizontally and in
  launch-site fire compartments upright.
* Volume-rendering SLCFs, &BNDF, &DUMP DT_SL3D are gone.
* Per-item DEVC probes (TEMPERATURE + HF) still on every combustible/component.
* ``&DEVC ID='incident_heat_flux'`` window probe is restored.
"""

import re

import pytest

from models.building import Building, BuildingGroup, Story
from generators.fds_generator import FDSGenerator, DEFAULT_DEVC_DT, HEAT_FLUX_PROBE_WALL_OFFSET


def _simple_bg() -> BuildingGroup:
    b = Building(
        name="Plant",
        boundary=[0, 20, 0, 10],
        wall_thickness=0.3,
        stories=[Story(name="1F", height=4.0)],
    )
    b.update_z_offsets()
    return BuildingGroup(buildings=[b])


def test_no_volume_slices_in_output():
    """Volume-rendering SLCF blocks (CELL_CENTERED) and BNDF are gone."""
    fds = FDSGenerator(_simple_bg()).generate()
    assert "CELL_CENTERED" not in fds
    assert "&BNDF" not in fds
    assert "&SLCF QUANTITY='HRRPUV', VECTOR" not in fds


def test_no_dt_sl3d_in_dump():
    fds = FDSGenerator(_simple_bg()).generate()
    assert "DT_SL3D" not in fds


def test_device_output_interval_matches_flux_calibration():
    fds = FDSGenerator(_simple_bg()).generate()
    assert f"DT_DEVC={DEFAULT_DEVC_DT:.2f}" in fds


def test_no_custom_dev_n_in_output():
    """The deleted custom-device UI must not leave stale ``custom_dev_*`` lines."""
    fds = FDSGenerator(_simple_bg()).generate()
    assert "custom_dev_" not in fds


def test_center_temp_device_not_emitted():
    """The facility-aggregate center_temp / radiation_loss DEVCs were removed
    in favour of per-story 2D slices.  They must not appear in the output."""
    fds = FDSGenerator(_simple_bg()).generate()
    assert "ID='center_temp'" not in fds
    assert "ID='radiation_loss'" not in fds


def test_devices_off_still_emits_no_aggregate_deck():
    """``output['devices'] = False`` must still produce no aggregate devices."""
    fds = FDSGenerator(_simple_bg())
    fds.bg.output["devices"] = False
    text = fds.generate()
    assert "ID='center_temp'" not in text
    assert "ID='radiation_loss'" not in text


def test_window_heat_flux_probe_emitted():
    """A near-wall radiative gas heat-flux DEVC is emitted."""
    fds = FDSGenerator(_simple_bg()).generate()
    assert "ID='incident_heat_flux'" in fds


def test_window_flux_probe_is_radiative_gas_heat_flux():
    """The probe uses the same gas-phase heat-flux quantity as object probes."""
    import re
    fds = FDSGenerator(_simple_bg()).generate()
    m = re.search(r"&DEVC[^/]*ID='incident_heat_flux' /", fds, re.DOTALL)
    assert m, "missing incident_heat_flux probe"
    block = m.group(0)
    assert "QUANTITY='RADIATIVE HEAT FLUX GAS'" in block, (
        f"probe must measure gas radiative heat flux (got: {block!r})"
    )
    assert "ORIENTATION=" in block, (
        f"gas radiative heat-flux probe must carry ORIENTATION= (got: {block!r})"
    )
    assert "IOR=" not in block, (
        f"gas radiative heat-flux probe must not carry IOR= (got: {block!r})"
    )


def test_window_flux_probe_is_outside_exterior_wall():
    """For azimuth 0, the probe sits just off the wall on the source side."""
    import re
    fds = FDSGenerator(_simple_bg()).generate()
    m = re.search(r"&DEVC XYZ=([^,]+),([^,]+),([^,]+),[^/]*?ID='incident_heat_flux'", fds)
    assert m, "missing incident_heat_flux probe"
    px, py, pz = [float(v.strip()) for v in m.groups()]
    meshes = re.findall(
        r"&MESH(?: ID='[^']+',)? IJK=[^,]+,[^,]+,[^,]+, "
        r"XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)[^/]* /",
        fds,
    )
    assert meshes, "missing MESH"
    vals = [[float(v) for v in mesh] for mesh in meshes]
    x0 = min(v[0] for v in vals)
    x1 = max(v[1] for v in vals)
    z0 = min(v[4] for v in vals)
    z1 = max(v[5] for v in vals)
    assert px == pytest.approx(x1 - 1.0 + HEAT_FLUX_PROBE_WALL_OFFSET)
    assert py == 5.00
    assert pz == pytest.approx((z0 + z1) / 2)
    block = re.search(r"&DEVC[^/]*ID='incident_heat_flux' /", fds, re.DOTALL).group(0)
    assert "ORIENTATION=1.000,0.000,0.000" in block


class TestPerStorySlices:
    """Each story emits a TEMPERATURE + HRRPUV SLCF at z=z_bottom+2m."""

    def _multi_story_bg(self):
        b = Building(
            name="Plant",
            boundary=[0, 30, 0, 20],
            wall_thickness=0.3,
            stories=[
                Story(name="1F", height=5.0),
                Story(name="2F", height=4.0),
            ],
        )
        b.update_z_offsets()
        return BuildingGroup(buildings=[b])

    def test_two_slices_per_story(self):
        bg = self._multi_story_bg()
        fds = FDSGenerator(bg).generate()
        # Two stories -> four SLCF blocks (TEMPERATURE + HRRPUV × 2).
        temp_slices = re.findall(
            r"&SLCF PBZ=([\d.]+), QUANTITY='TEMPERATURE'", fds
        )
        hrr_slices = re.findall(
            r"&SLCF PBZ=([\d.]+), QUANTITY='HRRPUV'", fds
        )
        assert len(temp_slices) == 2
        assert len(hrr_slices) == 2

    def test_slice_pbz_is_two_metres_above_floor(self):
        bg = self._multi_story_bg()
        fds = FDSGenerator(bg).generate()
        # 1F: z_bottom=0, expect PBZ=2.00
        # 2F: z_bottom=5, expect PBZ=7.00
        temp_pbz = sorted(float(x) for x in re.findall(
            r"&SLCF PBZ=([\d.]+), QUANTITY='TEMPERATURE'", fds
        ))
        assert temp_pbz == sorted([2.0, 7.0])

    def test_slice_skipped_when_too_close_to_roof(self):
        """A 2 m tall story has no valid 2 m slice — must be skipped."""
        b = Building(
            name="Plant",
            boundary=[0, 20, 0, 10],
            wall_thickness=0.3,
            stories=[Story(name="1F", height=2.0)],
        )
        b.update_z_offsets()
        bg = BuildingGroup(buildings=[b])
        fds = FDSGenerator(bg).generate()
        temp_pbz = re.findall(
            r"&SLCF PBZ=([\d.]+), QUANTITY='TEMPERATURE'", fds
        )
        assert temp_pbz == [], "story too short for 2m slice — should be skipped"

    def test_duplicate_pbz_deduped_across_buildings(self):
        """Two buildings whose 1F floor sit at the same elevation should
        produce only one TEMPERATURE + one HRRPUV SLCF (dedup by PBZ).
        """
        b1 = Building(
            name="A", cn_name="A主厂房",
            boundary=[0, 18, 0, 38],
            wall_thickness=0.25,
            stories=[Story(name="1F", height=5.0)],
        )
        b2 = Building(
            name="B", cn_name="B仓库",
            boundary=[20, 26, 14, 10],
            wall_thickness=0.15,
            stories=[Story(name="1F", height=3.0)],
        )
        b1.update_z_offsets()
        b2.update_z_offsets()
        bg = BuildingGroup(buildings=[b1, b2])

        fds = FDSGenerator(bg).generate()
        temp_pbz = re.findall(
            r"&SLCF PBZ=([\d.]+), QUANTITY='TEMPERATURE'", fds
        )
        hrr_pbz = re.findall(
            r"&SLCF PBZ=([\d.]+), QUANTITY='HRRPUV'", fds
        )
        # Both buildings' 1F share PBZ=2.00 (z_bottom=0 + 2.0), so once is
        # enough — the duplicate is dropped.
        assert len(temp_pbz) == 1, f"expected 1 dedup'd TEMPERATURE slice, got {temp_pbz}"
        assert len(hrr_pbz) == 1, f"expected 1 dedup'd HRRPUV slice, got {hrr_pbz}"
        assert temp_pbz[0] == "2.00"
        assert hrr_pbz[0] == "2.00"

    def test_distinct_pbz_kept_for_distinct_floors(self):
        """Distinct elevations across buildings/stories each keep their SLCF.

        Building A is a single-storey structure (1F at z=0..5, PBZ=2.00).
        Building B has two stories; 1F at z=0..4 (PBZ=2.00, deduplicated
        against A's 1F) and 2F at z=4..8 (PBZ=6.00, unique).  Hence the
        surviving PBZ set is {2.00, 6.00}.
        """
        b1 = Building(
            name="A", cn_name="A厂房",
            boundary=[0, 10, 0, 10],
            wall_thickness=0.25,
            stories=[Story(name="1F", height=5.0)],
        )
        b2 = Building(
            name="B", cn_name="B仓库",
            boundary=[12, 20, 0, 10],
            wall_thickness=0.15,
            stories=[
                Story(name="1F", height=4.0),
                Story(name="2F", height=4.0),
            ],
        )
        b1.update_z_offsets()
        b2.update_z_offsets()
        bg = BuildingGroup(buildings=[b1, b2])

        fds = FDSGenerator(bg).generate()
        temp_pbz = sorted(
            float(x) for x in re.findall(
                r"&SLCF PBZ=([\d.]+), QUANTITY='TEMPERATURE'", fds
            )
        )
        hrr_pbz = sorted(
            float(x) for x in re.findall(
                r"&SLCF PBZ=([\d.]+), QUANTITY='HRRPUV'", fds
            )
        )
        # A1F @ 0..5  -> PBZ=2.00 (kept; first occurrence)
        # B1F @ 0..4  -> PBZ=2.00 (dropped; dedup against A1F)
        # B2F @ 4..8  -> PBZ=6.00 (kept; distinct PBZ)
        assert temp_pbz == sorted([2.00, 6.00]), f"want 2.00 + 6.00, got {temp_pbz}"
        assert hrr_pbz == sorted([2.00, 6.00]), f"want 2.00 + 6.00, got {hrr_pbz}"


class TestRocketsByFcRole:
    """Rockets follow their fire-compartment role."""

    def _bg(self, fc_name, building_cn="assembly"):
        from models.building import FireCompartment, Roof
        fc = FireCompartment(
            name=fc_name,
            boundary=[0, 40, 0, 40],
            specialized_components=[{"key": "ROCKET_VEHICLE_LARGE", "count": 1}],
        )
        b = Building(
            name="T", cn_name=building_cn,
            boundary=[0, 40, 0, 40],
            wall_thickness=0.24, height=15.0,
            stories=[Story(name="1F", height=15.0,
                           fire_compartments=[fc], roof=Roof())],
        )
        b.update_z_offsets()
        return BuildingGroup(
            buildings=[b],
            heat_source={"azimuth": 0, "elevation": 0,
                         "net_heat_flux": 3.0, "duration": 1.36},
        )

    def test_assembly_fc_accepts_rocket(self):
        fds = FDSGenerator(self._bg("总装主厂区")).generate()
        assert "ROCKET_VEHICLE_LARGE" in fds

    def test_launch_site_fc_accepts_rocket(self):
        fds = FDSGenerator(self._bg("发射场", building_cn="发射场")).generate()
        assert "ROCKET_VEHICLE_LARGE" in fds

    def test_processing_fc_drops_rocket(self):
        fds = FDSGenerator(self._bg("加工作业区", building_cn="加工厂房")).generate()
        assert "ROCKET_VEHICLE_LARGE" not in fds

    def test_unknown_fc_drops_rocket(self):
        fds = FDSGenerator(self._bg("FC1", building_cn="unknown_building")).generate()
        assert "ROCKET_VEHICLE_LARGE" not in fds

    def test_rocket_is_laid_down_not_upright(self):
        """A placed rocket must occupy significantly more ground than vertical."""
        from models.building import FireCompartment, Roof
        fc = FireCompartment(
            name="总装主厂区",
            boundary=[0, 40, 0, 40],
            specialized_components=[{"key": "ROCKET_VEHICLE_LARGE", "count": 1}],
        )
        b = Building(
            name="T", cn_name="T",
            boundary=[0, 40, 0, 40],
            wall_thickness=0.24, height=15.0,
            stories=[Story(name="1F", height=15.0,
                           fire_compartments=[fc], roof=Roof())],
        )
        b.update_z_offsets()
        bg = BuildingGroup(buildings=[b],
                           heat_source={"azimuth": 0, "elevation": 0,
                                        "net_heat_flux": 3.0, "duration": 1.36})
        fds = FDSGenerator(bg).generate()
        # Find the rocket OBST group and compute its bounding box.
        # Each OBST line: &OBST XB=x1,x2,y1,y2,z1,z2, ...
        obst = re.findall(
            r"&OBST\s+XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)[,\s][^/]*?ID='ROCKET_VEHICLE_(?:LARGE|MEDIUM|SMALL)_",
            fds,
        )
        assert obst, "expected at least one rocket OBST"
        xs1 = [float(o[0]) for o in obst]
        xs2 = [float(o[1]) for o in obst]
        ys1 = [float(o[2]) for o in obst]
        ys2 = [float(o[3]) for o in obst]
        zs1 = [float(o[4]) for o in obst]
        zs2 = [float(o[5]) for o in obst]
        width = max(xs2) - min(xs1)
        depth = max(ys2) - min(ys1)
        height = max(zs2) - min(zs1)
        # Horizontal rocket: ground-extent (max of width/depth) > height.
        assert max(width, depth) > height, (
            f"rocket looks upright: width={width:.2f} depth={depth:.2f} "
            f"height={height:.2f}"
        )

    def test_launch_site_rocket_is_upright(self):
        """A launch-site rocket should read as a vertical pad object."""
        from models.building import FireCompartment, Roof
        fc = FireCompartment(
            name="发射准备区",
            boundary=[0, 40, 0, 40],
            specialized_components=[{"key": "ROCKET_VEHICLE_LARGE", "count": 1}],
        )
        b = Building(
            name="T", cn_name="发射场",
            boundary=[0, 40, 0, 40],
            wall_thickness=0.24, height=40.0,
            stories=[Story(name="1F", height=40.0,
                           fire_compartments=[fc], roof=Roof())],
        )
        b.update_z_offsets()
        bg = BuildingGroup(buildings=[b],
                           heat_source={"azimuth": 0, "elevation": 0,
                                        "net_heat_flux": 3.0, "duration": 1.36})
        fds = FDSGenerator(bg).generate()
        obst = re.findall(
            r"&OBST\s+XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)[,\s][^/]*?ID='ROCKET_VEHICLE_(?:LARGE|MEDIUM|SMALL)_",
            fds,
        )
        assert obst, "expected at least one rocket OBST"
        xs1 = [float(o[0]) for o in obst]
        xs2 = [float(o[1]) for o in obst]
        ys1 = [float(o[2]) for o in obst]
        ys2 = [float(o[3]) for o in obst]
        zs1 = [float(o[4]) for o in obst]
        zs2 = [float(o[5]) for o in obst]
        width = max(xs2) - min(xs1)
        depth = max(ys2) - min(ys1)
        height = max(zs2) - min(zs1)
        assert height > max(width, depth), (
            f"launch-site rocket looks horizontal: width={width:.2f} "
            f"depth={depth:.2f} height={height:.2f}"
        )
