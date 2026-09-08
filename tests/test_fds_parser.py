"""Tests for the lightweight FDS preview parser."""

from services.fds_parser import FdsMaterial, parse_fds_text

SAMPLE = """
&HEAD CHID='demo'/
&MESH ID='m1', IJK=10,20,30, XB=0.0,10.0,0.0,20.0,0.0,30.0/

&MATL ID='WOOD',
      FUEL='METHANE',
      COMB=1,
      HRRPUV=20.0,
      TIG=450.0/
&MATL ID='STEEL',
      HEAT_OF_COMBUSTION=0.0/
&MATL ID='OLDSTYLE',
      HEAT_OF_COMBUSTION=1.75E4/

&SURF ID='S_WOOD',
      MATL_ID='WOOD'/
&SURF ID='S_STEEL',
      MATL_ID='STEEL'/
&SURF ID='S_OLD',
      MATL_ID(1,1)='OLDSTYLE',
      THICKNESS(1)=0.2/

&OBST ID='o1', XB=0.0,2.0,0.0,2.0,0.0,3.0, SURF_ID='S_WOOD'/
&OBST ID='o2', XB=0.0,2.0,0.0,2.0,3.0,6.0, SURF_ID='S_STEEL'/
&OBST ID='o3', XB=(2.0,4.0,2.0,4.0,0.0,3.0),(4.0,6.0,2.0,4.0,0.0,3.0),
      SURF_ID=('S_OLD','S_STEEL')/
&OBST ID='bad', XB=5.0,1.0,0.0,2.0,0.0,3.0, SURF_ID='S_WOOD'/

&HEAT XYZ=1.0,1.0,0.5, RADIUS=0.6, QCC=1000.0/
"""


def test_parse_domain_and_heat():
    scene = parse_fds_text(SAMPLE)
    assert scene.domain == (0.0, 10.0, 0.0, 20.0, 0.0, 30.0)
    assert scene.heat.xyz == (1.0, 1.0, 0.5)
    assert scene.heat.radius == 0.6
    assert scene.heat.qcc == 1000.0


def test_parse_obstacles_skips_degenerate():
    scene = parse_fds_text(SAMPLE)
    # three valid obstacles: o1, o2, and two boxes from o3 (bad is skipped)
    assert len(scene.obstacles) == 4
    assert scene.obstacles[0].surf_ids == ["S_WOOD"]
    assert scene.obstacles[2].xmax == 4.0


def test_materials_and_combustibility():
    scene = parse_fds_text(SAMPLE)
    assert scene.materials["WOOD"].combustible
    assert scene.materials["WOOD"].hrrpuv == 20.0
    assert scene.materials["WOOD"].tig == 450.0
    assert not scene.materials["STEEL"].combustible
    # old PyroSim-style material: combustible via HEAT_OF_COMBUSTION
    assert scene.materials["OLDSTYLE"].combustible
    assert scene.materials["OLDSTYLE"].heat_of_combustion == 17500.0
    assert [m.id for m in scene.combustible_materials()] == ["WOOD", "OLDSTYLE"]


def test_surface_mapping_and_obstacle_combustible():
    scene = parse_fds_text(SAMPLE)
    # indexed MATL_ID(1,1) key is resolved like a plain MATL_ID
    assert scene.surfaces["S_OLD"] == "OLDSTYLE"
    assert scene.combustible(scene.obstacles[0])  # S_WOOD
    assert not scene.combustible(scene.obstacles[1])  # S_STEEL
    assert scene.combustible(scene.obstacles[2])  # S_OLD first in list


def test_hrrpua_surface_is_combustible_without_matl():
    scene = parse_fds_text(
        """
&MESH IJK=2,2,2, XB=0,2,0,2,0,2/
&SURF ID='CARTON', HRRPUA=300.0/
&OBST ID='carton', XB=0,1,0,1,0,1, SURF_ID='CARTON'/
"""
    )
    assert scene.surfaces["CARTON"] == "CARTON"
    assert scene.materials["CARTON"].combustible
    assert scene.materials["CARTON"].hrrpuv == 300.0
    assert scene.combustible(scene.obstacles[0])


def test_missing_cards_yield_empty_scene():
    scene = parse_fds_text("&HEAD CHID='x'/\n")
    assert scene.domain is None
    assert scene.obstacles == []
    assert scene.materials == {}
    assert scene.heat is None


def test_material_without_fuel_not_combustible():
    scene = parse_fds_text(
        "&MATL ID='AIR', COMB=0/\n&MATL ID='B', FUEL='AIR'/\n"
    )
    assert not scene.materials["AIR"].combustible
    assert not scene.materials["B"].combustible
    assert FdsMaterial("x").fuel == ""
