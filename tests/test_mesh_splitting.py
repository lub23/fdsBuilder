"""Unit tests for FDSGenerator._compute_mesh.

``_compute_mesh`` returns a ``MeshPlan`` namedtuple ``(domain, grid_size,
num_meshes, refinement)``:
- ``domain``: integer-rounded ``[x0, x1, y0, y1, z0, z1]`` bounding box (m).
- ``grid_size``: cell size (m); auto-grows only when the cell count would
  otherwise exceed the 1M budget.
- ``num_meshes``: defaults to **5**: one source-side strip + 4 coarse meshes.
- ``refinement``: a dict by default with
  the refinement mesh's bounding box, IJK, grid_size, depth and source wall.

The source-side refinement zone is enabled by default and adds a 5th mesh on
the radiation-facing side.
The actual ``&MESH`` blocks are emitted inline by ``generate()``.
"""
from generators.fds_generator import FDSGenerator
from models.building import BuildingGroup, Building, Story, FireCompartment


def _gen(boundary, height, grid_size, num_meshes=None, refinement=None):
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
    if refinement is not None:
        domain["refinement_zone"] = refinement
    return FDSGenerator(BuildingGroup(buildings=[b], domain=domain))


def test_default_has_refinement_strip():
    """With no override, defaults to 1 source-side strip + 4 coarse meshes."""
    plan = _gen([0, 10, 0, 10], 5, 1.0)._compute_mesh()
    assert plan.num_meshes == 5
    assert plan.grid_size == 1.0  # small domain → grid preserved
    assert len(plan.domain) == 6
    assert plan.refinement is not None
    assert plan.refinement["grid_size"] == 1.0


def test_refinement_overrides_single_mesh_pin():
    """The mandatory refinement strip takes precedence over num_meshes."""
    plan = _gen([0, 10, 0, 10], 5, 1.0, num_meshes=1)._compute_mesh()
    assert plan.num_meshes == 5


def test_large_domain_still_four_meshes():
    """A large domain keeps 4 coarse meshes plus the mandatory 1 m source strip."""
    plan = _gen([0, 200, 0, 200], 10, 0.5)._compute_mesh()
    assert plan.num_meshes == 5
    assert plan.refinement is not None
    assert plan.refinement["source_gap"] == 1.0
    assert plan.refinement["depth"] >= 3 * plan.refinement["grid_size"]


def test_refinement_overrides_four_mesh_pin():
    """The source strip remains active even when num_meshes is pinned."""
    plan = _gen([0, 30, 0, 30], 10, 0.5, num_meshes=4)._compute_mesh()
    assert plan.num_meshes == 5


def test_compute_mesh_grid_size_preserved():
    """When the cell count fits the budget, the user grid_size is kept as-is."""
    plan = _gen([0, 30, 0, 30], 10, 0.5)._compute_mesh()
    assert plan.grid_size == 0.5
    assert plan.num_meshes == 5


def test_mesh_layout_long_axis_x_yields_two():
    """Domain wider in X than Y: layout is 2 × 2 for 4 meshes."""
    plan = _gen([0, 40, 0, 10], 10, 1.0)._compute_mesh()
    nx = max(10, int(round((plan.domain[1] - plan.domain[0]) / plan.grid_size)))
    ny = max(10, int(round((plan.domain[3] - plan.domain[2]) / plan.grid_size)))
    assert nx > ny, f"sanity: nx={nx} should exceed ny={ny}"
    nx_seg, ny_seg = FDSGenerator._mesh_layout(4, nx, ny)
    assert nx_seg == 2 and ny_seg == 2


def test_mesh_layout_long_axis_y_yields_three():
    """Domain taller in Y than X must split Y into 3."""
    plan = _gen([0, 10, 0, 40], 10, 1.0)._compute_mesh()
    nx = max(10, int(round((plan.domain[1] - plan.domain[0]) / plan.grid_size)))
    ny = max(10, int(round((plan.domain[3] - plan.domain[2]) / plan.grid_size)))
    nx_seg, ny_seg = FDSGenerator._mesh_layout(6, nx, ny)
    assert (nx_seg, ny_seg) == (2, 3)  # long=Y ⇒ Y×3


def test_multimesh_uniform_cell_size():
    """The mandatory source strip is emitted in addition to 4 coarse meshes."""
    gen = _gen([0, 120, 0, 210], 10, 2.0)
    output = gen.generate()

    mesh_lines = [l for l in output.splitlines() if l.startswith("&MESH")]
    assert len(mesh_lines) == 5
    assert "'MeshRefined'" in mesh_lines[0]

    cell_sizes = set()
    for line in mesh_lines[1:]:
        import re
        m_ijk = re.search(r"IJK=(\d+),(\d+),(\d+)", line)
        m_xb = re.search(r"XB=([^,]+),([^,]+),([^,]+),([^,]+),([^,]+),([^,]+)", line)
        assert m_ijk and m_xb, f"cannot parse MESH line: {line}"
        nx, ny, nz = int(m_ijk.group(1)), int(m_ijk.group(2)), int(m_ijk.group(3))
        x0, x1, y0, y1 = (float(m_xb.group(i)) for i in range(1, 5))
        dx = (x1 - x0) / nx
        dy = (y1 - y0) / ny
        cell_sizes.add((round(dx, 6), round(dy, 6)))

    assert len(cell_sizes) == 1, (
        f"expected uniform cell size across all meshes, got {cell_sizes}"
    )


# ============================================================
# Refinement zone (5th mesh on the radiation-facing side)
# ============================================================
def test_refinement_enabled_by_default():
    """No refinement_zone still enables the 1 m source-side mesh."""
    plan = _gen([0, 30, 0, 30], 5, 1.0)._compute_mesh()
    assert plan.refinement is not None
    assert plan.refinement["grid_size"] == 1.0
    assert plan.num_meshes == 5


def test_refinement_enabled_yields_5_meshes():
    """Enabled refinement adds a stable source-side mesh containing the 1 m gap."""
    rz = {"enabled": True, "depth": 1.0, "grid_size": 0.5}
    plan = _gen(
        [0, 30, 0, 30], 5, 1.0, refinement=rz,
    )._compute_mesh()
    assert plan.num_meshes == 5
    assert plan.refinement is not None
    assert plan.refinement["grid_size"] == 0.5
    assert plan.refinement["source_gap"] == 1.0
    assert plan.refinement["depth"] == 2.0
    assert plan.refinement["grid_size"] < plan.grid_size


def test_refinement_carved_on_source_facing_side():
    """azimuth=0 → XMAX side gets carved for the refinement mesh."""
    rz = {"enabled": True, "depth": 2.0, "grid_size": 0.5}
    gen = _gen([0, 20, 0, 20], 5, 1.0, refinement=rz)
    gen.bg.heat_source["azimuth"] = 0
    plan = gen._compute_mesh()
    rx0, rx1, *_ = plan.refinement["xb"]
    full_x_max = plan.domain[1]
    assert abs(rx1 - full_x_max) < 1e-9


def test_refinement_rejects_non_dividing_grid_size():
    """refinement.grid_size must divide coarse grid_size evenly."""
    rz = {"enabled": True, "depth": 1.0, "grid_size": 0.3}
    plan = _gen([0, 20, 0, 20], 5, 1.0, refinement=rz)._compute_mesh()
    assert plan.refinement is None, (
        "non-integer cell ratio must be rejected to avoid FDS ERROR 873"
    )
    assert plan.num_meshes == 4


def test_refinement_fds_output_alignment():
    """Refined mesh + coarse meshes share a cell-aligned interface."""
    rz = {"enabled": True, "depth": 2.0, "grid_size": 0.5}
    gen = _gen([0, 30, 0, 30], 5, 1.0, refinement=rz)
    gen.bg.heat_source["azimuth"] = 0
    output = gen.generate()

    mesh_lines = [
        l for l in output.splitlines() if l.startswith("&MESH")
    ]
    assert len(mesh_lines) == 5, (
        f"expected 5 &MESH lines (1 refined + 4 coarse), got {len(mesh_lines)}"
    )
    assert "'MeshRefined'" in mesh_lines[0]


def test_refinement_depth_rounded_up():
    """User depth no longer changes the physical 1 m heat-source gap."""
    rz = {"enabled": True, "depth": 1.3, "grid_size": 0.5}
    plan = _gen([0, 30, 0, 30], 5, 1.0, refinement=rz)._compute_mesh()
    assert plan.refinement["source_gap"] == 1.0
    assert plan.refinement["depth"] == 2.0


def test_refinement_depth_does_not_expand_to_ten_fine_cells():
    """The mesh may deepen for Poisson stability while source gap stays 1 m."""
    rz = {"enabled": True, "depth": 1.0, "grid_size": 0.5}
    gen = _gen([0, 30, 0, 30], 5, 1.5, refinement=rz)
    gen.bg.heat_source["azimuth"] = 0
    plan = gen._compute_mesh()
    rx0, rx1, *_ = plan.refinement["xb"]

    assert plan.grid_size == 2.0
    assert plan.refinement["source_gap"] == 1.0
    assert plan.refinement["depth"] == 3.0
    assert abs((rx1 - rx0) - 3.0) < 1e-9
    assert plan.refinement["ijk"][0] == 6


def test_refinement_depth_alignment_is_silent_and_persisted(capsys):
    """The strict 1 m source strip should not rewrite user depth settings."""
    rz = {"enabled": True, "depth": 1.0, "grid_size": 0.5}
    gen = _gen([0, 30, 0, 30], 5, 1.5, refinement=rz)
    gen.bg.heat_source["azimuth"] = 0

    gen.generate()
    captured = capsys.readouterr()

    assert "refinement_zone.depth" not in captured.out
    assert gen.bg.domain["refinement_zone"]["depth"] == 1.0


def test_refinement_vents_skip_shared_mesh_faces_at_grid_1p5():
    """OPEN VENTs must not be emitted on coarse/refined or coarse/coarse interfaces."""
    rz = {"enabled": True, "depth": 1.0, "grid_size": 0.5}
    gen = _gen([0, 30, 0, 30], 5, 1.5, refinement=rz)
    gen.bg.heat_source["azimuth"] = 0
    output = gen.generate()

    assert "MeshRefined Vent [XMIN]" not in output
    assert "Mesh02 Vent [XMIN]" not in output
    assert "Mesh04 Vent [XMIN]" not in output


def test_refinement_coarse_z_cells_keep_grid_size_at_grid_1p5():
    """Non-integer coarse grid >1m is promoted for 1m source-grid alignment."""
    import re

    rz = {"enabled": True, "depth": 1.0, "grid_size": 0.5}
    gen = _gen([0, 30, 0, 30], 12.0, 1.5, refinement=rz)
    gen.bg.heat_source["azimuth"] = 0
    output = gen.generate()

    coarse_line = next(
        l for l in output.splitlines()
        if l.startswith("&MESH") and "Mesh01" in l
    )
    m_ijk = re.search(r"IJK=(\d+),(\d+),(\d+)", coarse_line)
    m_xb = re.search(
        r"XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)",
        coarse_line,
    )
    nz = int(m_ijk.group(3))
    z0 = float(m_xb.group(5))
    z1 = float(m_xb.group(6))

    assert gen._compute_mesh().grid_size == 2.0
    assert z1 == 13.0


def test_refinement_depth_expands_when_only_two_fine_cells():
    """A separate refined mesh is kept at least 3 cells thick."""
    rz = {"enabled": True, "depth": 2.0, "grid_size": 1.0}
    gen = _gen([0, 30, 0, 30], 12.0, 2.0, refinement=rz)
    gen.bg.heat_source["azimuth"] = 0
    plan = gen._compute_mesh()
    rx0, rx1, *_ = plan.refinement["xb"]

    assert plan.refinement["source_gap"] == 1.0
    assert plan.refinement["depth"] == 3.0
    assert abs((rx1 - rx0) - 3.0) < 1e-9
    assert plan.refinement["ijk"][0] == 3


def test_refinement_cell_size_matches_xb():
    """The refinement mesh's IJK / XB must give 0.5m cells on every axis.

    This guards against orientation-dependent bug where ``cells_along_strip``
    was assigned to the wrong axis (x vs y) for y_min/y_max walls.
    """
    import re

    def _run(az):
        rz = {"enabled": True, "depth": 2.0, "grid_size": 0.5}
        gen = _gen([0, 20, 0, 20], 5, 1.0, refinement=rz)
        gen.bg.heat_source["azimuth"] = az
        text = gen.generate()

        refined_line = [
            l for l in text.splitlines()
            if l.startswith("&MESH") and "MeshRefined" in l
        ][0]
        m_ijk = re.search(r"IJK=(\d+),(\d+),(\d+)", refined_line)
        m_xb = re.search(
            r"XB=([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+),([\d.\-]+)",
            refined_line,
        )
        nb = [float(m_xb.group(i)) for i in range(1, 7)]
        ijk = [int(m_ijk.group(i)) for i in range(1, 4)]
        for label, ext, nb_cells in (
            ("x", nb[1] - nb[0], ijk[0]),
            ("y", nb[3] - nb[2], ijk[1]),
            ("z", nb[5] - nb[4], ijk[2]),
        ):
            cell_size = ext / nb_cells
            assert abs(cell_size - 0.5) < 1e-9, (
                f"az={az}: {label}-axis cell size {cell_size} != 0.5"
            )

    for az in (0, 90, 180, 270):
        _run(az)
