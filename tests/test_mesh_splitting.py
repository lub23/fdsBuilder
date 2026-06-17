"""Unit tests for FDSGenerator._compute_mesh.

``_compute_mesh`` returns ``(domain, grid_size, num_meshes)``:
- ``domain``: integer-rounded ``[x0, x1, y0, y1, z0, z1]`` bounding box (m).
- ``grid_size``: cell size (m); auto-grows only when the user did not pin
  ``num_meshes`` AND the cell count would otherwise exceed the 1M budget.
- ``num_meshes``: one of ``{1, 2, 4}``; the actual ``&MESH`` blocks are emitted
  inline by ``generate()``.
"""
from generators.fds_generator import FDSGenerator
from models.building import BuildingGroup, Building, Story, FireCompartment


def _gen(boundary, height, grid_size):
    b = Building(
        name="B",
        boundary=boundary,  # [offset_x, length, offset_y, width]
        wall_thickness=0.3,
        stories=[
            Story(
                name="1F",
                height=height,
                fire_compartments=[
                    FireCompartment(name="FC", boundary=[0, boundary[1], 0, boundary[3]])
                ],
            )
        ],
    )
    return FDSGenerator(BuildingGroup(buildings=[b], domain={"grid_size": grid_size}))


def test_compute_mesh_single_when_small():
    """A small domain fits the cell budget in a single mesh."""
    domain, grid_size, num_meshes = _gen([0, 10, 0, 10], 5, 1.0)._compute_mesh()
    assert num_meshes == 1
    assert grid_size == 1.0  # small domain → grid preserved
    assert len(domain) == 6


def test_compute_mesh_splits_when_large():
    """A large domain splits into multiple meshes (2 or 4)."""
    domain, grid_size, num_meshes = _gen([0, 200, 0, 200], 10, 0.5)._compute_mesh()
    assert num_meshes > 1
    assert num_meshes in (2, 4)


def test_compute_mesh_grid_size_preserved():
    """When the cell count fits the budget, the user grid_size is kept as-is."""
    domain, grid_size, num_meshes = _gen([0, 30, 0, 30], 10, 0.5)._compute_mesh()
    assert grid_size == 0.5
    assert num_meshes in (1, 2, 4)
