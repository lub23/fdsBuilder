"""Unit tests for FDSGenerator._compute_mesh.

``_compute_mesh`` returns ``(domain, grid_size, num_meshes)``:
- ``domain``: integer-rounded ``[x0, x1, y0, y1, z0, z1]`` bounding box (m).
- ``grid_size``: cell size (m); auto-grows only when the cell count would
  otherwise exceed the 1M budget.
- ``num_meshes``: defaults to **4** (2×2) for MPI parallel execution; a user
  may still pin ``domain["num_meshes"]`` to 1/2/4.  The actual ``&MESH``
  blocks are emitted inline by ``generate()``.
"""
from generators.fds_generator import FDSGenerator
from models.building import BuildingGroup, Building, Story, FireCompartment


def _gen(boundary, height, grid_size, num_meshes=None):
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
    domain = {"grid_size": grid_size}
    if num_meshes is not None:
        domain["num_meshes"] = num_meshes
    return FDSGenerator(BuildingGroup(buildings=[b], domain=domain))


def test_default_is_four_meshes():
    """With no override, runs default to 4 meshes for MPI parallelism."""
    domain, grid_size, num_meshes = _gen([0, 10, 0, 10], 5, 1.0)._compute_mesh()
    assert num_meshes == 4
    assert grid_size == 1.0  # small domain → grid preserved
    assert len(domain) == 6


def test_user_can_pin_single_mesh():
    """An explicit num_meshes override is honoured."""
    _, _, num_meshes = _gen([0, 10, 0, 10], 5, 1.0, num_meshes=1)._compute_mesh()
    assert num_meshes == 1


def test_large_domain_still_four_meshes():
    """A large domain stays at 4 meshes (and the grid may grow)."""
    domain, grid_size, num_meshes = _gen([0, 200, 0, 200], 10, 0.5)._compute_mesh()
    assert num_meshes == 4


def test_compute_mesh_grid_size_preserved():
    """When the cell count fits the budget, the user grid_size is kept as-is."""
    domain, grid_size, num_meshes = _gen([0, 30, 0, 30], 10, 0.5)._compute_mesh()
    assert grid_size == 0.5
    assert num_meshes in (1, 2, 4)
