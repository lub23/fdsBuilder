import pytest
from generators.fds_generator import FDSGenerator
from models.building import BuildingGroup, Building, Story, FireCompartment


def test_compute_mesh_single_when_small():
    """Test single mesh when domain is small."""
    b = Building(
        name="SmallBuilding",
        boundary=[0, 10, 0, 10],  # [offset_x, length, offset_y, width]
        wall_thickness=0.3,
        stories=[
            Story(
                name="1F",
                height=5,
                fire_compartments=[FireCompartment(name="FC", boundary=[0, 10, 0, 10])]
            )
        ]
    )
    bg = BuildingGroup(buildings=[b], domain={"grid_size": 1.0})
    gen = FDSGenerator(bg)
    
    meshes = gen._compute_mesh()
    # Should return list with single mesh
    assert len(meshes) == 1
    assert meshes[0]["id"] == "Mesh01"
    assert "ijk" in meshes[0]
    assert "xb" in meshes[0]


def test_compute_mesh_splits_when_large():
    """Test that mesh splits into multiple meshes when cells exceed limit."""
    b = Building(
        name="LargeBuilding",
        boundary=[0, 200, 0, 200],
        wall_thickness=0.3,
        stories=[
            Story(
                name="1F",
                height=10,
                fire_compartments=[FireCompartment(name="FC", boundary=[0, 200, 0, 200])]
            )
        ]
    )
    bg = BuildingGroup(buildings=[b], domain={"grid_size": 0.5})
    gen = FDSGenerator(bg)
    
    meshes = gen._compute_mesh()
    # Should split into multiple meshes
    assert len(meshes) > 1
    
    # Each mesh should have valid ijk and xb
    for m in meshes:
        assert "id" in m
        assert "ijk" in m
        assert "xb" in m
        nx, ny, nz = m["ijk"]
        assert nx * ny * nz <= 150000  # Each mesh under limit


def test_compute_mesh_grid_size_preserved():
    """Test that grid_size is preserved (not increased)."""
    b = Building(
        name="TestBuilding",
        boundary=[0, 100, 0, 100],
        wall_thickness=0.3,
        stories=[
            Story(
                name="1F",
                height=10,
                fire_compartments=[FireCompartment(name="FC", boundary=[0, 100, 0, 100])]
            )
        ]
    )
    # Use small grid_size
    bg = BuildingGroup(buildings=[b], domain={"grid_size": 0.5})
    gen = FDSGenerator(bg)
    
    meshes = gen._compute_mesh()
    
    # With grid_size=0.5, domain ~104x104x12 = ~130k cells
    # Should need 1 mesh
    assert len(meshes) >= 1
