# UI / 3D 刷新 / 热源重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor 3D preview from full-refresh to incremental-by-group + mesh bundle cache, redesign heat source to render on MESH faces with multi-face flux decomposition, and fix 5 specific UI bugs (defaults, combustible dialog, button layout, toolbar removal, door/window height).

**Architecture:** (1) New `models/heat_source.py` encapsulates flux-per-face math. (2) `Viewer3D` gains per-group actor management (`buildings`, `combustibles`, `heat_source`, `slices`, `devices`) and three fine-grained update entry points. (3) Per-building `pv.PolyData` bundles are cached in-memory keyed by a geometry signature. (4) `SimulationControlPanel.parameters_changed` becomes `Signal(str)` so `MainWindow` can route to the right 3D update path, eliminating double refresh.

**Tech Stack:** PySide6, PyVista, pytest. Python 3.10+.

**Spec reference:** `docs/superpowers/specs/2026-04-19-ui-3d-perf-refactor-design.md`

**Pre-existing test failures (out of scope):** `tests/test_parameter_engine.py::TestDistributeExteriorOpenings::{test_windows_on_x_walls,test_window_spacing}` — ignore them; do not try to fix.

---

## Task 1: `models/heat_source.face_fluxes` module + tests

**Files:**
- Create: `models/heat_source.py`
- Create: `tests/test_heat_source.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_heat_source.py`:

```python
"""Tests for models.heat_source.face_fluxes."""
import math
import pytest
from models.heat_source import face_fluxes


def _close(d1, d2, tol=1e-6):
    """Dict float-compare."""
    if set(d1) != set(d2):
        return False
    return all(abs(d1[k] - d2[k]) < tol for k in d1)


class TestFaceFluxes:
    def test_azimuth_0_elevation_0_single_face_ymax(self):
        assert _close(face_fluxes(0, 0, 20.0), {"YMAX": 20.0})

    def test_azimuth_90_single_face_xmax(self):
        assert _close(face_fluxes(90, 0, 20.0), {"XMAX": 20.0})

    def test_azimuth_180_single_face_ymin(self):
        assert _close(face_fluxes(180, 0, 20.0), {"YMIN": 20.0})

    def test_azimuth_270_single_face_xmin(self):
        assert _close(face_fluxes(270, 0, 20.0), {"XMIN": 20.0})

    def test_azimuth_360_wraps_to_ymax(self):
        assert _close(face_fluxes(360, 0, 20.0), {"YMAX": 20.0})

    def test_azimuth_45_splits_ymax_xmax_equally(self):
        result = face_fluxes(45, 0, 20.0)
        expected = 20.0 * math.cos(math.radians(45))
        assert set(result) == {"YMAX", "XMAX"}
        assert abs(result["YMAX"] - expected) < 1e-6
        assert abs(result["XMAX"] - expected) < 1e-6

    def test_azimuth_135_splits_xmax_ymin(self):
        result = face_fluxes(135, 0, 20.0)
        expected = 20.0 * math.cos(math.radians(45))
        assert set(result) == {"XMAX", "YMIN"}
        assert abs(result["XMAX"] - expected) < 1e-6
        assert abs(result["YMIN"] - expected) < 1e-6

    def test_azimuth_225_splits_ymin_xmin(self):
        result = face_fluxes(225, 0, 20.0)
        assert set(result) == {"YMIN", "XMIN"}

    def test_azimuth_315_splits_xmin_ymax(self):
        result = face_fluxes(315, 0, 20.0)
        assert set(result) == {"XMIN", "YMAX"}

    def test_elevation_adds_zmax(self):
        result = face_fluxes(0, 30, 20.0)
        assert "ZMAX" in result
        assert abs(result["ZMAX"] - 20.0 * math.sin(math.radians(30))) < 1e-6
        assert abs(result["YMAX"] - 20.0 * math.cos(math.radians(30))) < 1e-6

    def test_elevation_60_distributes(self):
        result = face_fluxes(45, 60, 20.0)
        cos_e = math.cos(math.radians(60))
        sin_e = math.sin(math.radians(60))
        cos_a = math.cos(math.radians(45))
        sin_a = math.sin(math.radians(45))
        assert abs(result["ZMAX"] - 20.0 * sin_e) < 1e-6
        assert abs(result["YMAX"] - 20.0 * cos_e * cos_a) < 1e-6
        assert abs(result["XMAX"] - 20.0 * cos_e * sin_a) < 1e-6

    def test_zero_flux(self):
        assert face_fluxes(0, 0, 0.0) == {}

    def test_azimuth_wraps_negative(self):
        # -5° should behave like 355°
        r1 = face_fluxes(-5, 0, 20.0)
        r2 = face_fluxes(355, 0, 20.0)
        assert _close(r1, r2)

    def test_primary_secondary_energy_conservation(self):
        # primary^2 + secondary^2 + zmax^2 == Q^2
        r = face_fluxes(37, 23, 20.0)
        total = sum(v**2 for v in r.values())
        assert abs(total - 20.0**2) < 1e-4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_heat_source.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models.heat_source'`

- [ ] **Step 3: Implement `models/heat_source.py`**

Create `models/heat_source.py`:

```python
"""Heat source flux decomposition: map (azimuth, elevation, Q) → per-face flux dict.

Convention:
    azimuth = 0°  → YMAX (north)
    azimuth = 90° → XMAX (east)
    azimuth = 180° → YMIN (south)
    azimuth = 270° → XMIN (west)
    elevation > 0 → portion of Q tilts onto ZMAX (top)

For azimuths between cardinal directions, flux splits between the two adjacent
side faces using cos(remainder) / sin(remainder) where remainder = azimuth % 90.
"""
from __future__ import annotations

import math


_QUADRANT_FACES = [
    ("YMAX", "XMAX"),   # 0..90
    ("XMAX", "YMIN"),   # 90..180
    ("YMIN", "XMIN"),   # 180..270
    ("XMIN", "YMAX"),   # 270..360
]


def face_fluxes(azimuth: float, elevation: float, Q: float) -> dict[str, float]:
    """Decompose a radiation Q across MESH faces.

    Args:
        azimuth: 0-360° (wraps). 0 = north = YMAX.
        elevation: 0-90° (typically one of {0, 30, 45, 60}).
        Q: Total heat flux in kW/m².

    Returns:
        Dict mapping face name ("XMIN"/"XMAX"/"YMIN"/"YMAX"/"ZMAX") to
        its flux component (kW/m²). Faces with ~0 flux are omitted.
    """
    if Q <= 0:
        return {}

    a = azimuth % 360
    quadrant = int(a // 90) % 4
    primary_face, secondary_face = _QUADRANT_FACES[quadrant]

    rem = math.radians(a - quadrant * 90)
    e = math.radians(elevation)
    cos_e = math.cos(e)
    sin_e = math.sin(e)

    primary = Q * cos_e * math.cos(rem)
    secondary = Q * cos_e * math.sin(rem)
    top = Q * sin_e

    result: dict[str, float] = {}
    tol = 1e-9
    if primary > tol:
        result[primary_face] = primary
    if secondary > tol:
        # If a=90 exact, secondary accumulates to same face as primary of next
        # quadrant — handled because primary ~= 0 and secondary ~= Q*cos_e.
        # Guard against primary_face == secondary_face collision (possible at
        # exact 90-degree boundary due to floating point).
        if secondary_face in result:
            result[secondary_face] += secondary
        else:
            result[secondary_face] = secondary
    if top > tol:
        result["ZMAX"] = top
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_heat_source.py -v`
Expected: all 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add -f models/heat_source.py tests/test_heat_source.py
git commit -m "feat(models): add heat_source.face_fluxes for multi-face flux decomposition"
```

---

## Task 2: `BuildingGroup` defaults + heat_source migration

**Files:**
- Modify: `models/building.py:300-403` (BuildingGroup dataclass + from_dict)
- Modify: `tests/test_models.py` (add migration tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_models.py`:

```python
class TestBuildingGroupHeatSourceMigration:
    def test_default_heat_source_structure(self):
        bg = BuildingGroup()
        assert bg.heat_source == {
            "azimuth": 0,
            "elevation": 0,
            "net_heat_flux": 20.0,
            "duration": 1.36,
        }

    def test_default_simulation_time_600(self):
        bg = BuildingGroup()
        assert bg.simulation_time == 600

    def test_default_domain_grid_size_1(self):
        bg = BuildingGroup()
        assert bg.domain == {"padding": 5.0, "grid_size": 1.0}

    def test_from_dict_migrates_w_per_m2_to_kw(self):
        # Old value 3000 W/m² should migrate to 3.0 kW/m²
        data = {
            "buildings": [],
            "heat_source": {
                "enabled": True,
                "distance": 5.0,
                "azimuth": 90,
                "elevation": 30,
                "net_heat_flux": 3000,
                "duration": 2.0,
                "width_ratio": 1.5,
                "height_ratio": 1.0,
            },
        }
        bg = BuildingGroup.from_dict(data)
        assert bg.heat_source["net_heat_flux"] == 3.0
        assert bg.heat_source["azimuth"] == 90
        assert bg.heat_source["elevation"] == 30
        assert bg.heat_source["duration"] == 2.0
        # Dropped fields
        assert "enabled" not in bg.heat_source
        assert "distance" not in bg.heat_source
        assert "width_ratio" not in bg.heat_source
        assert "height_ratio" not in bg.heat_source

    def test_from_dict_keeps_kw_value_under_1000(self):
        data = {
            "buildings": [],
            "heat_source": {"net_heat_flux": 20.0, "azimuth": 0, "elevation": 0, "duration": 1.36},
        }
        bg = BuildingGroup.from_dict(data)
        assert bg.heat_source["net_heat_flux"] == 20.0

    def test_from_dict_fills_missing_heat_source_fields(self):
        data = {"buildings": []}
        bg = BuildingGroup.from_dict(data)
        assert bg.heat_source == {
            "azimuth": 0, "elevation": 0, "net_heat_flux": 20.0, "duration": 1.36,
        }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_models.py::TestBuildingGroupHeatSourceMigration -v`
Expected: all 5 tests FAIL.

- [ ] **Step 3: Update `models/building.py` BuildingGroup**

Replace lines 300-403 in `models/building.py`. Key changes: default `simulation_time=600`, default `domain={"padding": 5.0, "grid_size": 1.0}`, default `heat_source={"azimuth": 0, "elevation": 0, "net_heat_flux": 20.0, "duration": 1.36}`, and `from_dict` migration.

```python
@dataclass
class BuildingGroup:
    """A group of buildings for a single simulation scenario.

    Attributes:
        buildings:       List of Building instances.
        heat_source:     Heat source configuration dict:
                         {azimuth(°), elevation(°), net_heat_flux(kW/m²), duration(s)}.
        simulation_time: Total simulation time in seconds.
        domain:          Computational domain settings.
        output:          Output control settings.
    """

    buildings: list[Building] = field(default_factory=list)
    heat_source: dict = field(default_factory=lambda: {
        "azimuth": 0,
        "elevation": 0,
        "net_heat_flux": 20.0,
        "duration": 1.36,
    })
    simulation_time: float = 600
    domain: dict = field(
        default_factory=lambda: {"padding": 5.0, "grid_size": 1.0}
    )
    output: dict = field(default_factory=lambda: {"slices": True, "devices": True})

    # -- convenience properties -----------------------------------------------

    @property
    def building_group(self) -> BuildingGroup:
        """Compat: let code that does ``model.building_group`` work when model IS a BuildingGroup."""
        return self

    @property
    def total_height(self) -> float:
        """Max height across all buildings (sum of story heights)."""
        if not self.buildings:
            return 0.0
        return max(sum(s.height for s in b.stories) for b in self.buildings)

    @property
    def chid(self) -> str:
        """Derive a CHID from the first building name."""
        if self.buildings and self.buildings[0].name:
            return self.buildings[0].name
        return "building"

    @property
    def num_stories(self) -> int:
        """Number of stories in the first building."""
        if self.buildings:
            return len(self.buildings[0].stories)
        return 0

    @property
    def length(self) -> float:
        """Length of the first building (compat)."""
        if self.buildings:
            return self.buildings[0].length
        return 0.0

    @property
    def width(self) -> float:
        """Width of the first building (compat)."""
        if self.buildings:
            return self.buildings[0].width
        return 0.0

    # -- runtime helpers ------------------------------------------------------

    def update_z_offsets(self) -> None:
        """Compute cumulative z_bottom for every story in every building."""
        for b in self.buildings:
            b.update_z_offsets()

    def add_building(self, building: Building) -> None:
        """Append a building to the group."""
        self.buildings.append(building)

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "buildings": [b.to_dict() for b in self.buildings],
            "heat_source": dict(self.heat_source),
            "simulation_time": self.simulation_time,
            "domain": dict(self.domain),
            "output": dict(self.output),
        }

    @classmethod
    def from_dict(cls, data: dict) -> BuildingGroup:
        """Deserialize from dict, migrating legacy heat_source fields.

        Migration:
          - ``net_heat_flux`` > 1000: treated as legacy W/m², divided by 1000.
          - Legacy fields ``enabled``, ``distance``, ``width_ratio``,
            ``height_ratio``, ``location``, ``use_ramp`` are dropped.
          - Missing fields get 2026-04-19 defaults.
        """
        if "building_group" in data:
            data = data["building_group"]

        raw_hs = data.get("heat_source", {}) or {}
        flux = raw_hs.get("net_heat_flux", 20.0)
        if flux > 1000:
            flux = flux / 1000.0  # W/m² → kW/m²
        hs = {
            "azimuth": raw_hs.get("azimuth", 0),
            "elevation": raw_hs.get("elevation", 0),
            "net_heat_flux": float(flux),
            "duration": raw_hs.get("duration", 1.36),
        }

        domain = data.get("domain", {"padding": 5.0, "grid_size": 1.0})
        # Legacy configs may have mesh_cells; drop it in favor of grid_size.
        if "grid_size" not in domain:
            domain = {"padding": domain.get("padding", 5.0), "grid_size": 1.0}

        return cls(
            buildings=[Building.from_dict(b) for b in data.get("buildings", [])],
            heat_source=hs,
            simulation_time=data.get("simulation_time", 600),
            domain=domain,
            output=data.get("output", {"slices": True, "devices": True}),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: all new migration tests PASS; previously-passing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add models/building.py tests/test_models.py
git commit -m "feat(models): BuildingGroup defaults 600s/1m grid + heat_source kW/m² migration"
```

---

## Task 3: FDS generator — heat source multi-face emission

**Files:**
- Modify: `generators/fds_generator.py` (`_generate_heat_source`, `_compute_mesh`, CHID)

- [ ] **Step 1: Write failing integration tests**

Append to `tests/test_models.py` (or create `tests/test_fds_heat_source.py`):

Create `tests/test_fds_heat_source.py`:

```python
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
    """Return list of (face_name, flux) tuples extracted from &VENT lines
    that are part of the heat source (carrying HEAT_SOURCE_ SURF_ID)."""
    matches = []
    for m in re.finditer(r"SURF_ID='HEAT_SOURCE_(\w+)'[^&]*NET_HEAT_FLUX=([\d\.\-]+)", fds):
        matches.append((m.group(1), float(m.group(2))))
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fds_heat_source.py -v`
Expected: all 4 tests FAIL (old generator emits a single VENT or uses old enabled check).

- [ ] **Step 3: Rewrite `_generate_heat_source` in `generators/fds_generator.py`**

Read current content first:

```bash
sed -n '590,720p' generators/fds_generator.py
```

Replace the `_generate_heat_source` method (and any pre-VENT OBST emission in it) with the implementation below. Locate by method name — the method starts with `def _generate_heat_source(self, lines):` and runs until the next `def `.

```python
# ------------------------------------------------------------------
# Heat source
# ------------------------------------------------------------------
def _generate_heat_source(self, lines):
    """Emit one &VENT per MESH face that receives a share of the heat flux.

    Flux is decomposed by models.heat_source.face_fluxes.
    """
    from models.heat_source import face_fluxes

    hs = self.bg.heat_source
    azimuth = hs.get("azimuth", 0)
    elevation = hs.get("elevation", 0)
    Q_kw = hs.get("net_heat_flux", 20.0)
    duration = hs.get("duration", 1.36)

    fluxes = face_fluxes(azimuth, elevation, Q_kw)
    if not fluxes:
        return

    domain, grid_size, num_meshes = self._compute_mesh()
    x0, x1, y0, y1, z0, z1 = domain

    lines.append(f"! ========== 外部热源 (azimuth={azimuth}°, elevation={elevation}°) ==========\n")

    # One SURF per face with its own NET_HEAT_FLUX.
    # Use T_END = duration (0 = forever if duration is 0).
    for face_name, face_flux in fluxes.items():
        surf_id = f"HEAT_SOURCE_{face_name}"
        ramp_clause = ""
        if duration > 0:
            # Constant flux up to T_END, then zero — encoded via a simple RAMP_Q.
            ramp_clause = f", RAMP_Q='RAMP_{face_name}'"
        lines.append(
            f"&SURF ID='{surf_id}', NET_HEAT_FLUX={face_flux:.2f}, "
            f"COLOR='ORANGE'{ramp_clause} /\n"
        )
        if duration > 0:
            lines.append(
                f"&RAMP ID='RAMP_{face_name}', T=0.00, F=1.0 /\n"
                f"&RAMP ID='RAMP_{face_name}', T={duration:.2f}, F=1.0 /\n"
                f"&RAMP ID='RAMP_{face_name}', T={duration + 0.01:.2f}, F=0.0 /\n"
            )

    face_xb = {
        "XMIN": (x0, x0, y0, y1, z0, z1),
        "XMAX": (x1, x1, y0, y1, z0, z1),
        "YMIN": (x0, x1, y0, y0, z0, z1),
        "YMAX": (x0, x1, y1, y1, z0, z1),
        "ZMAX": (x0, x1, y0, y1, z1, z1),
    }
    for face_name in fluxes:
        xb = face_xb[face_name]
        lines.append(
            f"&VENT XB={xb[0]:.2f},{xb[1]:.2f},"
            f"{xb[2]:.2f},{xb[3]:.2f},"
            f"{xb[4]:.2f},{xb[5]:.2f}, "
            f"SURF_ID='HEAT_SOURCE_{face_name}' /\n"
        )
    lines.append("\n")
```

- [ ] **Step 4: Remove heat-source-driven domain expansion in `_compute_mesh`**

In `generators/fds_generator.py`, locate the block starting `if bg.heat_source.get("enabled", False):` (around line 778) and extending through `domain[3] = max(domain[3], source_oy + 5)` (around line 791). Delete that entire block — domain is now strictly buildings + padding.

Also change `base_grid_size = bg.domain.get("grid_size", 0.5)` to `base_grid_size = bg.domain.get("grid_size", 1.0)`.

- [ ] **Step 5: Update CHID suffix (kW/m² unit)**

In `generators/fds_generator.py`, locate where `chid_suffix` is built (around line 829). Update:

```python
hs = bg.heat_source
heat_flux_kw = int(round(hs.get("net_heat_flux", 20.0)))
azimuth = int(hs.get("azimuth", 0))
elevation = int(hs.get("elevation", 0))
duration = int(hs.get("duration", 0) * 100)
sim_time = int(bg.simulation_time)

chid_suffix = f"q{heat_flux_kw}_a{azimuth}_e{elevation}_d{duration}_t{sim_time}"
full_chid = f"{chid}_{chid_suffix}"

title = f"Heat Flux={heat_flux_kw}kW/m2, Azimuth={azimuth}, Elevation={elevation}, Duration={hs.get('duration',0)}s, SimTime={sim_time}s"
```

(Remove the `if heat_enabled` branches since heat is now always active.)

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_fds_heat_source.py tests/test_models.py -v`
Expected: all new and existing tests PASS. (`pytest tests/` as a whole will still show 2 pre-existing ParameterEngine failures — ignore them.)

- [ ] **Step 7: Commit**

```bash
git add generators/fds_generator.py tests/test_fds_heat_source.py
git commit -m "feat(fds): heat source emits one VENT per MESH face with flux split"
```

---

## Task 4: SimulationControlPanel heat section rewrite

**Files:**
- Modify: `ui/simulation_control_panel.py:71-172` (`_build_heat_section`)
- Modify: `ui/simulation_control_panel.py:823-896` (`sync_ui_from_model`, `sync_model_from_ui`)

- [ ] **Step 1: Replace `_build_heat_section` method**

Delete lines 71-172 and replace with:

```python
# ── 热源 ────────────────────────────────────────
def _build_heat_section(self):
    from models.heat_source import face_fluxes
    self._face_fluxes = face_fluxes  # bound for label updates

    grp = CollapsibleGroup("外部热源")

    form = QGridLayout()
    form.setContentsMargins(0, 2, 0, 0)
    form.setSpacing(4)
    form.setColumnStretch(1, 1)
    form.setColumnStretch(3, 1)

    # Row 0: Azimuth slider | Elevation snap
    form.addWidget(QLabel("方位角:"), 0, 0)
    az_row = QHBoxLayout()
    az_row.setSpacing(4)
    self.heat_azimuth_slider = QSlider(Qt.Horizontal)
    self.heat_azimuth_slider.setRange(0, 360)
    self.heat_azimuth_slider.setValue(0)
    self.heat_azimuth_slider.setSingleStep(5)
    self.heat_azimuth_slider.setPageStep(45)
    self.heat_azimuth_slider.setTickPosition(QSlider.TicksBelow)
    self.heat_azimuth_slider.setTickInterval(45)
    self.heat_azimuth_slider.valueChanged.connect(self._on_azimuth_label_update)
    self.heat_azimuth_slider.sliderReleased.connect(self._on_azimuth_committed)
    az_row.addWidget(self.heat_azimuth_slider)
    self.azimuth_label = QLabel("0° (北)")
    self.azimuth_label.setFixedWidth(140)
    self.azimuth_label.setStyleSheet("color:#89b4fa;font-weight:bold;font-size:11px;")
    az_row.addWidget(self.azimuth_label)
    form.addLayout(az_row, 0, 1)

    form.addWidget(QLabel("俯仰角:"), 0, 2)
    elev_row = QHBoxLayout()
    elev_row.setSpacing(4)
    self.heat_elevation_slider = QSlider(Qt.Horizontal)
    self.heat_elevation_slider.setRange(0, 3)
    self.heat_elevation_slider.setValue(0)
    self.heat_elevation_slider.setTickPosition(QSlider.TicksBelow)
    self.heat_elevation_slider.setTickInterval(1)
    self.heat_elevation_slider.valueChanged.connect(self._on_elevation_changed)
    self.heat_elevation_slider.sliderReleased.connect(self._on_azimuth_committed)
    elev_row.addWidget(self.heat_elevation_slider)
    self.elevation_label = QLabel("0°")
    self.elevation_label.setFixedWidth(40)
    self.elevation_label.setStyleSheet("color:#89b4fa;font-weight:bold;")
    elev_row.addWidget(self.elevation_label)
    form.addLayout(elev_row, 0, 3)

    # Row 1: Flux (kW/m²) | Duration (s)
    form.addWidget(QLabel("热通量:"), 1, 0)
    self.heat_flux_spin = QDoubleSpinBox()
    self.heat_flux_spin.setRange(0.05, 20.0)
    self.heat_flux_spin.setValue(20.0)
    self.heat_flux_spin.setDecimals(2)
    self.heat_flux_spin.setSingleStep(0.5)
    self.heat_flux_spin.setSuffix(" kW/m²")
    self.heat_flux_spin.valueChanged.connect(self._on_flux_changed)
    form.addWidget(self.heat_flux_spin, 1, 1)

    form.addWidget(QLabel("持续:"), 1, 2)
    self.heat_duration_spin = QDoubleSpinBox()
    self.heat_duration_spin.setRange(0, 36000)
    self.heat_duration_spin.setValue(1.36)
    self.heat_duration_spin.setDecimals(2)
    self.heat_duration_spin.setSuffix(" s")
    self.heat_duration_spin.valueChanged.connect(self._on_flux_changed)
    form.addWidget(self.heat_duration_spin, 1, 3)

    grp.content_layout.addLayout(form)
    return grp

_ELEV_VALUES = [0, 30, 45, 60]
```

- [ ] **Step 2: Update event handlers**

Find the existing `_on_azimuth_label_update`, `_on_azimuth_committed`, `_on_elevation_changed`, `_on_param_changed_debounced`, `_on_debounce_timeout`, `on_param_changed` methods (around lines 505-535). Replace with:

```python
def _on_azimuth_label_update(self, value):
    """Snap to 5° and update label (no model refresh)."""
    snapped = round(value / 5) * 5
    if self.heat_azimuth_slider.value() != snapped:
        self.heat_azimuth_slider.setValue(snapped)
        return
    self._refresh_azimuth_label(snapped, self._current_elevation())

def _current_elevation(self) -> int:
    return self._ELEV_VALUES[min(self.heat_elevation_slider.value(), 3)]

def _refresh_azimuth_label(self, azimuth: int, elevation: int):
    directions = {0: "北", 90: "东", 180: "南", 270: "西", 360: "北"}
    closest = min(directions.keys(), key=lambda k: abs(k - azimuth))
    dir_suffix = f" ({directions[closest]})" if abs(closest - azimuth) <= 15 else ""
    fluxes = self._face_fluxes(azimuth, elevation, 1.0)
    if len(fluxes) <= 1:
        detail = ""
    else:
        parts = [f"{k}:{int(v*100)}%" for k, v in fluxes.items()]
        detail = " " + "+".join(parts)
    self.azimuth_label.setText(f"{azimuth}°{dir_suffix}{detail}")

def _on_azimuth_committed(self):
    """Slider released — emit heat_geom event."""
    self.on_param_changed("heat_geom")

def _on_elevation_changed(self, index):
    val = self._ELEV_VALUES[min(index, len(self._ELEV_VALUES) - 1)]
    self.elevation_label.setText(f"{val}°")
    self._refresh_azimuth_label(self.heat_azimuth_slider.value(), val)
    # Release-only commit is handled by sliderReleased; keyboard arrow still triggers here
    self.on_param_changed("heat_geom")

def _on_flux_changed(self):
    """Flux / duration — FDS-only, no 3D refresh."""
    self._debounce_kind = "heat_flux"
    self._debounce_timer.start(500)

def _on_param_changed_debounced(self, kind: str = "sim"):
    self._debounce_kind = kind
    self._debounce_timer.start(500)

def _on_debounce_timeout(self):
    self.on_param_changed(getattr(self, "_debounce_kind", "sim"))

def on_param_changed(self, kind: str = "sim"):
    if not self._syncing:
        self.sync_model_from_ui()
        self.parameters_changed.emit(kind)
```

- [ ] **Step 3: Update `parameters_changed` signal type**

In `ui/simulation_control_panel.py`, at the class level (around line 39) change:

```python
parameters_changed = Signal()
```

to:

```python
parameters_changed = Signal(str)  # kind: "heat_geom" | "heat_flux" | "sim" | "slice_device"
```

- [ ] **Step 4: Update `sync_ui_from_model` / `sync_model_from_ui`**

Replace `sync_ui_from_model` body (around lines 823-875) with:

```python
def sync_ui_from_model(self, model):
    self._syncing = True
    try:
        hs = model.heat_source
        self.heat_flux_spin.setValue(hs.get("net_heat_flux", 20.0))
        self.heat_azimuth_slider.setValue(hs.get("azimuth", 0))
        elev = hs.get("elevation", 0)
        elev_idx = {0: 0, 30: 1, 45: 2, 60: 3}.get(elev, 0)
        self.heat_elevation_slider.setValue(elev_idx)
        self.heat_duration_spin.setValue(hs.get("duration", 1.36))
        self.elevation_label.setText(f"{elev}°")
        self._refresh_azimuth_label(hs.get("azimuth", 0), elev)

        self.sim_time_spin.setValue(model.simulation_time)
        self.grid_size_spin.setValue(model.domain.get("grid_size", 1.0))
        self.output_slices_check.setChecked(model.output.get("slices", True))
        self.output_devices_check.setChecked(model.output.get("devices", True))

        self._clear_custom_rows(self._slice_rows, self._slice_container)
        for s in model.output.get("custom_slices", []):
            self._add_slice_row()
            entry = self._slice_rows[-1]
            entry["axis"].setCurrentText(s.get("axis", "PBX"))
            entry["pos"].setValue(s.get("position", 0))
            entry["qty"].setCurrentText(s.get("quantity", "TEMPERATURE"))

        self._clear_custom_rows(self._device_rows, self._device_container)
        for d in model.output.get("custom_devices", []):
            self._add_device_row()
            entry = self._device_rows[-1]
            entry["x"].setValue(d.get("x", 0))
            entry["y"].setValue(d.get("y", 0))
            entry["z"].setValue(d.get("z", 0))
            entry["qty"].setCurrentText(d.get("quantity", "TEMPERATURE"))
    finally:
        self._syncing = False
```

Replace `sync_model_from_ui` body (around lines 882-926) with:

```python
def sync_model_from_ui(self):
    if not hasattr(self, "model"):
        return
    m = self.model
    m.heat_source = {
        "azimuth": self.heat_azimuth_slider.value(),
        "elevation": self._ELEV_VALUES[min(self.heat_elevation_slider.value(), 3)],
        "net_heat_flux": self.heat_flux_spin.value(),
        "duration": self.heat_duration_spin.value(),
    }
    m.simulation_time = self.sim_time_spin.value()
    m.domain["grid_size"] = self.grid_size_spin.value()
    m.output["slices"] = self.output_slices_check.isChecked()
    m.output["devices"] = self.output_devices_check.isChecked()

    m.output["custom_slices"] = [
        {"axis": e["axis"].currentText(), "position": e["pos"].value(),
         "quantity": e["qty"].currentText()}
        for e in self._slice_rows
    ]
    m.output["custom_devices"] = [
        {"x": e["x"].value(), "y": e["y"].value(), "z": e["z"].value(),
         "quantity": e["qty"].currentText()}
        for e in self._device_rows
    ]
```

- [ ] **Step 5: Commit**

```bash
git add ui/simulation_control_panel.py
git commit -m "feat(ui): heat-source panel — flux kW/m², drop enable/distance/ratios"
```

---

## Task 5: SimulationControlPanel — defaults 600/1m + slice_device signal

**Files:**
- Modify: `ui/simulation_control_panel.py` (_build_simulation_section defaults, _add_slice_row/_add_device_row connections)

- [ ] **Step 1: Update simulation section defaults**

In `_build_simulation_section` (around lines 176-211), change defaults:

Find:
```python
self.sim_time_spin.setValue(60)
```
Replace:
```python
self.sim_time_spin.setValue(600)
```

Find:
```python
self.grid_size_spin.setValue(0.5)
```
Replace:
```python
self.grid_size_spin.setValue(1.0)
```

Wire the existing `valueChanged.connect(self._on_param_changed_debounced)` calls to pass `"sim"`:

```python
self.sim_time_spin.valueChanged.connect(lambda v: self._on_param_changed_debounced("sim"))
self.grid_size_spin.valueChanged.connect(lambda v: self._on_param_changed_debounced("sim"))
```

For the two checkboxes below:
```python
self.output_slices_check.stateChanged.connect(lambda _: self.on_param_changed("slice_device"))
self.output_devices_check.stateChanged.connect(lambda _: self.on_param_changed("slice_device"))
```

- [ ] **Step 2: Update slice row / device row signal emission**

In `_add_slice_row` (around lines 285-340), replace every `self.on_param_changed()` / `.connect(self.on_param_changed)` call site with:

```python
pos_spin.valueChanged.connect(lambda v: self.on_param_changed("slice_device"))
qty_combo.currentIndexChanged.connect(lambda _: self.on_param_changed("slice_device"))
axis_combo.currentIndexChanged.connect(lambda _: self.on_param_changed("slice_device"))
```

Near the end of `_add_slice_row`:
```python
if not default:
    self.on_param_changed("slice_device")
```

In `_add_device_row` / `_remove_device_row` / `_remove_slice_row` — replace `self.on_param_changed()` with `self.on_param_changed("slice_device")`.

- [ ] **Step 3: Manual smoke check**

```bash
python main.py
```

Verify panel loads with default sim time 600s, grid 1.0 m, and heat panel shows "0° (北)".

- [ ] **Step 4: Commit**

```bash
git add ui/simulation_control_panel.py
git commit -m "feat(ui): default sim time 600s / grid 1m + slice_device signal kind"
```

---

## Task 6: FDS-run section — 4-button compact layout

**Files:**
- Modify: `ui/simulation_control_panel.py` (`_build_simulation_run_section`)

- [ ] **Step 1: Replace `_build_simulation_run_section`**

Delete lines 417-484 and replace with:

```python
# ── FDS仿真执行 ─────────────────────────────────
def _build_simulation_run_section(self):
    grp = CollapsibleGroup("🔥 FDS仿真执行")
    layout = QVBoxLayout()
    layout.setSpacing(4)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(4)

    def _mkbtn(text, bg_color, tooltip=""):
        btn = QPushButton(text)
        btn.setFixedHeight(30)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setStyleSheet(
            f"QPushButton{{background:{bg_color};color:#1e1e2e;font-weight:bold;"
            f"padding:3px 6px;border-radius:3px;font-size:12px}}"
            f"QPushButton:disabled{{background:#45475a;color:#6c7086}}"
        )
        if tooltip:
            btn.setToolTip(tooltip)
        return btn

    self.run_fds_btn = _mkbtn("▶️ 运行", "#a6e3a1", "运行FDS仿真")
    self.run_fds_btn.clicked.connect(self.run_fds_simulation)
    btn_row.addWidget(self.run_fds_btn)

    self.stop_fds_btn = _mkbtn("⏹️ 停止", "#f38ba8", "停止当前仿真")
    self.stop_fds_btn.setEnabled(False)
    self.stop_fds_btn.clicked.connect(self.stop_fds_simulation)
    btn_row.addWidget(self.stop_fds_btn)

    self.smv_btn = _mkbtn("🔍 查看", "#89b4fa", "用Smokeview打开仿真结果")
    self.smv_btn.setEnabled(False)
    self.smv_btn.clicked.connect(self.open_smokeview)
    btn_row.addWidget(self.smv_btn)

    self.predict_btn = _mkbtn("⚡ 预测", "#f9e2af", "工程快速预测(毁伤代理模型)")
    self.predict_btn.clicked.connect(self.run_predict)
    btn_row.addWidget(self.predict_btn)

    layout.addLayout(btn_row)

    self.progress_label = QLabel("就绪")
    self.progress_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
    layout.addWidget(self.progress_label)

    self.output_text = QLabel("")
    self.output_text.setStyleSheet("color: #cdd6f4; font-size: 11px;")
    self.output_text.setWordWrap(True)
    self.output_text.setMaximumHeight(40)
    layout.addWidget(self.output_text)

    grp.content_layout.addLayout(layout)
    return grp
```

- [ ] **Step 2: Manual smoke test**

```bash
python main.py
```

Verify 4 buttons (运行/停止/查看/预测) appear on a single row with equal width, and stop/smv start disabled.

- [ ] **Step 3: Commit**

```bash
git add ui/simulation_control_panel.py
git commit -m "feat(ui): compact FDS run section — 4 buttons on single row"
```

---

## Task 7: facility_panel — door/window panel height

**Files:**
- Modify: `ui/facility_panel.py:208` (`_door_win_tabs.setFixedHeight`)
- Modify: `ui/facility_panel.py:112-132` (_dsp, _isp spinbox height)

- [ ] **Step 1: Reduce tab height**

In `ui/facility_panel.py`, find:

```python
self._door_win_tabs.setFixedHeight(180)
```

Replace with:

```python
self._door_win_tabs.setMaximumHeight(130)
```

- [ ] **Step 2: Reduce spinbox height in `_dsp` / `_isp`**

In the helper functions `_dsp` and `_isp` (around lines 112-132), change:

```python
s.setFixedHeight(30)
```

to:

```python
s.setFixedHeight(26)
```

(Both occurrences — in `_dsp` and `_isp`.)

Also reduce the combo box height for wall-selection combos. Find:
```python
self.cb_dwall.setFixedHeight(30)
```
and
```python
self.cb_wwall.setFixedHeight(30)
```
Replace both `30` with `26`.

- [ ] **Step 3: Manual smoke test**

```bash
python main.py
```

Select any facility → any equivalent building. Verify "门窗设置" tab area is visibly shorter (~125px) and parameters still readable.

- [ ] **Step 4: Commit**

```bash
git add ui/facility_panel.py
git commit -m "style(ui): compact door/window panel height"
```

---

## Task 8: facility_panel — combustible dialog fire_compartments

**Files:**
- Modify: `ui/facility_panel.py:648-662` (`_open_combustible_dialog`)

- [ ] **Step 1: Replace method body**

Replace `_open_combustible_dialog` with:

```python
def _open_combustible_dialog(self):
    """Open combustible management with the current building's FC list."""
    if not self._params:
        return

    facility = self._params.get("facility")
    building_name = self._params.get("building")
    ftype = self._params.get("type")
    if not facility or not building_name:
        return

    # Collect fire_compartments as plain dicts for the dialog.
    fcs: list[dict] = []
    if ftype == "specialized":
        bdata = self.facility_manager.get_building_data(facility, building_name)
        for story in bdata.get("stories", []):
            for fc in story.get("fire_compartments", []):
                fcs.append(fc)
    else:
        params_full = self.facility_manager.default_params(facility, building_name)
        bld = self.facility_manager.load_equivalent(facility, building_name, params_full)
        for story in bld.stories:
            for fc in story.fire_compartments:
                fcs.append(fc.to_dict())

    from ui.dialogs import CombustibleSelectionDialog

    current_sel = self._params.get("combustible_selections", {})
    dlg = CombustibleSelectionDialog(
        self,
        current_sel,
        fire_compartments=fcs,
    )
    if dlg.exec() == QDialog.Accepted:
        self._params["combustible_selections"] = dlg.get_selections()
```

- [ ] **Step 2: Manual smoke test**

```bash
python main.py
```

Select an equivalent building (e.g. 航空航天→某建筑) → click 可燃物管理… → dialog should now show combustible rows per fire compartment, not blank.

Select a specialized building (e.g. alcoa→某建筑) → same check.

- [ ] **Step 3: Commit**

```bash
git add ui/facility_panel.py
git commit -m "fix(ui): combustible dialog — wire fire_compartments from FacilityManager"
```

---

## Task 9: mainwindow — remove quick-access toolbar

**Files:**
- Modify: `ui/mainwindow.py:62-63, 252-287` (`__init__` call, `setup_toolbar`)
- Modify: `ui/mainwindow.py:28-34` (unused imports)

- [ ] **Step 1: Remove `setup_toolbar()` call**

In `ui/mainwindow.py`, in `__init__`, delete the line:

```python
self.setup_toolbar()
```

- [ ] **Step 2: Delete `setup_toolbar` method**

Delete the entire `setup_toolbar` method (lines 252-287).

- [ ] **Step 3: Remove unused imports**

In the `PySide6.QtWidgets` import block at the top, remove `QToolBar` and `QToolButton`. In the `PySide6.QtCore` import block, remove `QSize` (it was only used for toolbar icon size). In `PySide6.QtGui`, keep `QAction, QKeySequence` — they're still used in `setup_menu`.

After changes, the imports should be:

```python
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QCheckBox,
    QPushButton,
    QTabWidget,
    QFileDialog,
    QMessageBox,
    QSplitter,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
```

- [ ] **Step 4: Manual smoke test**

```bash
python main.py
```

Verify main window has menu bar at top and NO second toolbar row below it. 3D viewer and left panel should fill more vertical space.

- [ ] **Step 5: Commit**

```bash
git add ui/mainwindow.py
git commit -m "style(ui): remove quick-access toolbar (duplicates menu)"
```

---

## Task 10: Viewer3D — actor groups + split update methods (no cache yet)

**Files:**
- Modify: `ui/viewer_3d.py`

- [ ] **Step 1: Add `_actor_groups` initialization**

In `Viewer3D.__init__` (around line 44-62), add after `self._pending_update = False`:

```python
self._actor_groups: dict[str, list] = {
    "buildings": [],
    "combustibles": [],
    "heat_source": [],
    "slices": [],
    "devices": [],
    "origin": [],
}
```

- [ ] **Step 2: Add helper for group-managed add/remove**

After `setup_ui`, add:

```python
def _add_to_group(self, group: str, actor):
    if actor is None:
        return
    self._actor_groups.setdefault(group, []).append(actor)

def _clear_group(self, group: str):
    actors = self._actor_groups.get(group, [])
    for a in actors:
        try:
            self.plotter.remove_actor(a)
        except Exception:
            pass
    self._actor_groups[group] = []
```

- [ ] **Step 3: Split `_do_full_render` into sub-renders**

Replace the existing `_do_full_render` method with three smaller methods plus a dispatcher.

```python
def _do_full_render(self):
    """Full render: buildings + combustibles + heat source + slices + origin + camera."""
    self.wall_actors.clear()
    self.opening_actors.clear()
    for g in list(self._actor_groups):
        self._clear_group(g)
    self.plotter.clear()  # safety net until caching is in place

    bg = self._bg
    if bg is None:
        return

    bbox = self._render_buildings_group(bg)
    if bbox is None:
        return
    global_min_x, global_max_x, global_min_y, global_max_y, global_max_z = bbox

    self._render_heat_source_group(bg, bbox)
    self._render_slices_devices_group(bg, bbox)
    self._render_origin(bg)
    self._finalize_camera(bbox)

def _render_buildings_group(self, bg):
    """Render walls/openings/roofs/firewalls/combustibles. Returns bbox tuple."""
    buildings = bg.buildings
    global_max_x = global_max_y = global_max_z = -float("inf")
    global_min_x = global_min_y = float("inf")

    for bi, building in enumerate(buildings):
        ox, L, oy, W = building.boundary
        t = building.wall_thickness

        is_highlighted = bi == self._highlighted_building
        wall_opacity = 1.0 if is_highlighted else 0.6
        edge_color = "#f97316" if is_highlighted else "#45475a"
        edge_width = 3 if is_highlighted else 1

        global_min_x = min(global_min_x, ox - t)
        global_max_x = max(global_max_x, ox + L + t)
        global_min_y = min(global_min_y, oy - t)
        global_max_y = max(global_max_y, oy + W + t)

        total_h = 0.0
        for s in building.stories:
            total_h = max(total_h, s.z_bottom + s.height)
        if total_h == 0.0:
            total_h = building.height
        global_max_z = max(global_max_z, total_h)

        for si, story in enumerate(building.stories):
            if not self._is_story_visible(bi, si):
                continue
            z0 = story.z_bottom
            z1 = story.z_top

            self._draw_exterior_walls(ox, L, oy, W, t, z0, z1,
                                      wall_opacity=wall_opacity,
                                      edge_color=edge_color, edge_width=edge_width)

            all_ext_openings = list(story.openings)
            all_ext_openings += detect_coplanar_openings(building, story)
            for opening in all_ext_openings:
                actor = self._draw_opening(opening, building, z0, is_exterior=True)
                if actor:
                    self.opening_actors.append(((bi, si), actor))
                    self._add_to_group("buildings", actor)

            for fc in story.fire_compartments:
                self._draw_firewalls(fc, building, z0, z1)
                for opening in fc.openings:
                    if not is_coplanar(fc.boundary, L, W, opening.wall):
                        a = self._draw_opening(opening, building, z0,
                                               is_exterior=False,
                                               fc_boundary=fc.boundary)
                        if a:
                            self._add_to_group("buildings", a)

            if self.show_roof:
                self._draw_roof(story.roof, ox, L, oy, W, z1)

            for fc in story.fire_compartments:
                self._draw_combustibles(fc, ox, oy, z0)

    if global_min_x == float("inf"):
        if buildings:
            b0 = buildings[0]
            ox0, L0, oy0, W0 = b0.boundary
            global_min_x, global_max_x = ox0, ox0 + L0
            global_min_y, global_max_y = oy0, oy0 + W0
        else:
            return None

    if global_max_z == -float("inf"):
        global_max_z = 3.0

    return (global_min_x, global_max_x, global_min_y, global_max_y, global_max_z)

def _render_heat_source_group(self, bg, bbox):
    self._clear_group("heat_source")
    self._add_heat_source(bg, *bbox)

def _render_slices_devices_group(self, bg, bbox):
    self._clear_group("slices")
    self._clear_group("devices")
    self._draw_slices_and_devices(bg, bg.buildings, *bbox)

def _render_origin(self, bg):
    self._clear_group("origin")
    self._draw_origin_marker(bg.buildings)

def _finalize_camera(self, bbox):
    xmin, xmax, ymin, ymax, zmax = bbox
    bbox_w = xmax - xmin
    bbox_d = ymax - ymin
    self.max_dim = max(bbox_w, bbox_d, zmax)
    self.cx = (xmin + xmax) / 2
    self.cy = (ymin + ymax) / 2
    self.cz = zmax / 2
    if self._first_render:
        self.plotter.reset_camera()
        self.setup_camera()
        self._first_render = False
    else:
        self.plotter.reset_camera_clipping_range()

# ── Public partial-update API ─────────────────────────────
def update_buildings(self, model):
    self.model = model
    self._bg = self._resolve_building_group(model)
    if not HAS_PYVISTA or model is None:
        return
    # For now, full-render path (cache comes in Task 11).
    self._do_full_render()

def update_heat_source(self, model):
    self.model = model
    self._bg = self._resolve_building_group(model)
    if not HAS_PYVISTA or model is None:
        return
    bbox = self._compute_bbox_only()
    if bbox is None:
        return
    self._render_heat_source_group(self._bg, bbox)
    self.plotter.render()

def update_slices_devices(self, model):
    self.model = model
    self._bg = self._resolve_building_group(model)
    if not HAS_PYVISTA or model is None:
        return
    bbox = self._compute_bbox_only()
    if bbox is None:
        return
    self._render_slices_devices_group(self._bg, bbox)
    self.plotter.render()

def _compute_bbox_only(self):
    """Compute (xmin, xmax, ymin, ymax, zmax) without drawing."""
    bg = self._bg
    if bg is None or not bg.buildings:
        return None
    xmin = ymin = float("inf")
    xmax = ymax = zmax = -float("inf")
    for b in bg.buildings:
        ox, L, oy, W = b.boundary
        t = b.wall_thickness
        xmin = min(xmin, ox - t); xmax = max(xmax, ox + L + t)
        ymin = min(ymin, oy - t); ymax = max(ymax, oy + W + t)
        total_h = 0.0
        for s in b.stories:
            total_h = max(total_h, s.z_bottom + s.height)
        if total_h == 0:
            total_h = b.height
        zmax = max(zmax, total_h)
    if xmin == float("inf"):
        return None
    if zmax == -float("inf"):
        zmax = 3.0
    return (xmin, xmax, ymin, ymax, zmax)
```

- [ ] **Step 4: Rewrite `_add_heat_source` to paint MESH faces**

Replace the existing `_add_heat_source` method (around lines 720-803) with:

```python
def _add_heat_source(self, bg, g_xmin, g_xmax, g_ymin, g_ymax, g_zmax):
    """Paint MESH boundary faces with heat-flux-weighted colors."""
    from models.heat_source import face_fluxes

    hs = bg.heat_source or {}
    Q = hs.get("net_heat_flux", 20.0)
    azimuth = hs.get("azimuth", 0)
    elevation = hs.get("elevation", 0)
    fluxes = face_fluxes(azimuth, elevation, Q)
    if not fluxes:
        return

    # MESH domain = building bbox + padding
    pad = bg.domain.get("padding", 5.0)
    x0 = g_xmin - pad
    x1 = g_xmax + pad
    y0 = g_ymin - pad
    y1 = g_ymax + pad
    z0 = 0.0
    z1 = max(g_zmax + pad, g_zmax + 1.0)

    Q_ref = max(20.0, Q)  # normalize to 20 kW/m² for consistent color scale

    def flux_color(f):
        # yellow → red ramp
        t = max(0.0, min(1.0, f / Q_ref))
        r = 255
        g = int(255 * (1 - t))
        b = 0
        return (r / 255, g / 255, b / 255)

    dx = x1 - x0
    dy = y1 - y0
    dz = z1 - z0

    face_params = {
        "XMIN": (((x0, (y0 + y1) / 2, (z0 + z1) / 2)), (1, 0, 0), dy, dz),
        "XMAX": (((x1, (y0 + y1) / 2, (z0 + z1) / 2)), (1, 0, 0), dy, dz),
        "YMIN": ((((x0 + x1) / 2, y0, (z0 + z1) / 2)), (0, 1, 0), dx, dz),
        "YMAX": ((((x0 + x1) / 2, y1, (z0 + z1) / 2)), (0, 1, 0), dx, dz),
        "ZMAX": ((((x0 + x1) / 2, (y0 + y1) / 2, z1)), (0, 0, 1), dx, dy),
    }
    for face_name, flux_val in fluxes.items():
        center, direction, i_size, j_size = face_params[face_name]
        plane = pv.Plane(center=center, direction=direction,
                         i_size=i_size, j_size=j_size)
        actor = self.plotter.add_mesh(
            plane,
            color=flux_color(flux_val),
            opacity=0.35,
            show_edges=True,
            edge_color="#f97316",
        )
        self._add_to_group("heat_source", actor)
```

- [ ] **Step 5: Wrap existing `_draw_*` actor returns to groups**

In `_draw_exterior_walls`, each `self.plotter.add_mesh(...)` returns `actor`; replace `self.wall_actors.append(actor)` with:

```python
self.wall_actors.append(actor)
self._add_to_group("buildings", actor)
```

In `_draw_firewalls`, each of the 4 `self.plotter.add_mesh(box, ...)` calls currently has no return capture. Change each to:

```python
fw_actor = self.plotter.add_mesh(box, color=fw_color, opacity=fw_opacity,
                                 show_edges=True, edge_color="#45475a", line_width=1)
self._add_to_group("buildings", fw_actor)
```

In `_draw_roof`, change:
```python
self.plotter.add_mesh(slab, color="#888888", opacity=0.4)
```
to:
```python
actor = self.plotter.add_mesh(slab, color="#888888", opacity=0.4)
self._add_to_group("buildings", actor)
```

In `_draw_combustibles`, wrap every `self.plotter.add_mesh(box, color=color, opacity=0.8)` as:
```python
actor = self.plotter.add_mesh(box, color=color, opacity=0.8)
self._add_to_group("combustibles", actor)
```
(Both the specialized-component branch and the combustible branch.)

In `_draw_origin_marker`, wrap each `self.plotter.add_mesh(...)` call:
```python
a = self.plotter.add_mesh(...)
self._add_to_group("origin", a)
```

In `_draw_slices_and_devices`:
- 3 slice planes (`sx`, `sy`, `sz`): wrap each actor into `self._add_to_group("slices", actor)`.
- Every device sphere: wrap into `self._add_to_group("devices", actor)`.

- [ ] **Step 6: Quick smoke test**

```bash
python main.py
```

Load a facility (e.g. alcoa) — verify 3D renders as before (no visual regression), heat source shows colored planes on outer domain faces.

- [ ] **Step 7: Commit**

```bash
git add ui/viewer_3d.py
git commit -m "feat(viewer): actor groups + per-group update methods + MESH-face heat source"
```

---

## Task 11: MainWindow — signal routing + remove double refresh

**Files:**
- Modify: `ui/mainwindow.py`

- [ ] **Step 1: Update signal connection**

In `ui/mainwindow.py` `setup_ui` (around line 151), change:

```python
self.simulation_control.parameters_changed.connect(self._on_sim_param_changed)
```

(The signal now carries a `str` but the slot already exists; we need to accept a kind.)

- [ ] **Step 2: Rewrite `_on_sim_param_changed` to dispatch by kind**

Replace the existing `_on_sim_param_changed` method (around lines 190-193):

```python
def _on_sim_param_changed(self, kind: str = "sim"):
    """Dispatch 3D update by event kind; FDS text always refreshes."""
    self.update_preview()
    if kind == "heat_geom":
        self.viewer_3d.update_heat_source(self.model)
    elif kind == "slice_device":
        self.viewer_3d.update_slices_devices(self.model)
    # "heat_flux" and "sim" do not touch 3D
```

- [ ] **Step 3: Drop `viewer_3d.update_model` from `update_preview`**

In `update_preview` (around lines 289-330), delete the line:

```python
self.viewer_3d.update_model(model)
```

`update_preview` now only generates FDS text + updates status bar.

- [ ] **Step 4: Audit callers of `update_preview` + `refresh_3d`**

The following sites currently call both `update_preview()` and `refresh_3d()` in sequence. After removing the redundant `update_model` from `update_preview`, both calls are needed (one renders FDS text, the other renders 3D). Leave them as-is but document the pattern.

Sites (grep confirmed):
- `_apply_ocr_result` (L172-177): keeps both
- `new_project` (L343-344): keeps both
- `open_config` (L358-359): keeps both
- `_on_facility_selected` (L405): has `update_preview` only — keep, then add `self.refresh_3d(first_render=True)` after. Full-render is needed after facility swap.
- `_on_building_added` (L438): same — add `self.refresh_3d(first_render=True)`.
- `_on_scene_building_removed` (L488-489): keeps both
- `_on_scene_building_offset_changed` (L508-509): keeps both

Make those two additions:

In `_on_facility_selected`, after `self.update_preview()`:

```python
self.refresh_3d(first_render=True)
```

In `_on_building_added`, after `self.update_preview()`:

```python
self.refresh_3d(first_render=True)
```

- [ ] **Step 5: Manual smoke test — verify no double refresh**

```bash
python main.py
```

Steps:
1. Select an equivalent building, change azimuth slider and release → 3D heat source color changes, building mesh does NOT visibly flicker (should be instant).
2. Change flux spinbox → 3D does not flicker at all (only FDS text updates).
3. Toggle 切片输出 checkbox → slices appear/disappear, building does not flicker.
4. Load warrick (全部建筑) → 3D renders once.

- [ ] **Step 6: Commit**

```bash
git add ui/mainwindow.py
git commit -m "refactor(mainwindow): route sim params by kind, drop double 3D refresh"
```

---

## Task 12: Viewer3D — Building mesh bundle cache

**Files:**
- Modify: `ui/viewer_3d.py`

- [ ] **Step 1: Add `BuildingMeshBundle` dataclass + signature function**

At the top of `ui/viewer_3d.py`, after imports, add:

```python
from dataclasses import dataclass, field

@dataclass
class BuildingMeshBundle:
    """Precomputed PyVista meshes for a single building, keyed by signature."""
    walls: "pv.PolyData | None" = None
    openings: "pv.PolyData | None" = None
    firewalls: "pv.PolyData | None" = None
    roofs: "pv.PolyData | None" = None
    combustibles_per_material: dict = field(default_factory=dict)  # color → PolyData
    actors: dict = field(default_factory=dict)


def _signature(building):
    """Build a stable geometry signature for cache keying."""

    def _opening_sig(o):
        return (o.wall, o.type, tuple(o.boundary))

    def _fc_sig(fc):
        return (
            fc.name, tuple(fc.boundary), fc.firewall_thickness,
            tuple(_opening_sig(o) for o in fc.openings),
            tuple(
                (c.get("key", ""), c.get("count", 1), c.get("rotation", 0))
                for c in fc.combustibles if isinstance(c, dict)
            ),
            tuple(
                (sc.get("key", ""), sc.get("count", 1))
                for sc in fc.specialized_components if isinstance(sc, dict)
            ),
        )

    def _story_sig(s):
        return (
            s.name, round(s.height, 4),
            tuple(_opening_sig(o) for o in s.openings),
            tuple(_fc_sig(fc) for fc in s.fire_compartments),
            (round(s.roof.thickness, 4), s.roof.material),
        )

    return (
        building.name,
        round(building.length, 4),
        round(building.width, 4),
        round(building.height, 4),
        round(building.wall_thickness, 4),
        round(building.offset_x, 4),
        round(building.offset_y, 4),
        tuple(_story_sig(s) for s in building.stories),
    )
```

- [ ] **Step 2: Add cache to `Viewer3D.__init__`**

In `__init__`, after `self._actor_groups = {...}` initialization, add:

```python
self._building_cache: dict = {}  # sig → BuildingMeshBundle
self._cache_max = 100            # simple bound
```

- [ ] **Step 3: Add `_build_bundle` method**

Append to `Viewer3D` class (keep existing methods):

```python
def _build_bundle(self, building) -> BuildingMeshBundle:
    """Build a BuildingMeshBundle from a Building object.

    Combines the per-story geometry into per-type PolyData meshes.
    """
    bundle = BuildingMeshBundle()
    ox, L, oy, W = building.boundary
    t = building.wall_thickness

    def _box(bounds):
        return pv.Box(bounds=bounds)

    wall_boxes: list = []
    opening_boxes: list = []
    firewall_boxes: list = []
    roof_boxes: list = []
    combust_per_color: dict[str, list] = {}

    for story in building.stories:
        z0 = story.z_bottom
        z1 = story.z_top

        wall_boxes.extend([
            _box([ox - t/2, ox + L + t/2, oy - t, oy, z0, z1]),
            _box([ox - t/2, ox + L + t/2, oy + W, oy + W + t, z0, z1]),
            _box([ox - t, ox, oy - t/2, oy + W + t/2, z0, z1]),
            _box([ox + L, ox + L + t, oy - t/2, oy + W + t/2, z0, z1]),
        ])

        # External openings
        all_ext = list(story.openings) + detect_coplanar_openings(building, story)
        for op in all_ext:
            box = self._opening_box(op, building, z0, is_exterior=True)
            if box is not None:
                opening_boxes.append(box)

        # Firewalls + internal openings
        for fc in story.fire_compartments:
            firewall_boxes.extend(self._firewall_boxes(fc, building, z0, z1))
            for op in fc.openings:
                if not is_coplanar(fc.boundary, L, W, op.wall):
                    box = self._opening_box(op, building, z0,
                                            is_exterior=False, fc_boundary=fc.boundary)
                    if box is not None:
                        opening_boxes.append(box)

        if self.show_roof:
            roof_boxes.append(
                _box([ox, ox + L, oy, oy + W, z1, z1 + story.roof.thickness])
            )

        for fc in story.fire_compartments:
            self._collect_combustible_boxes(fc, ox, oy, z0, combust_per_color)

    def _combine(boxes):
        if not boxes:
            return None
        m = boxes[0].copy()
        for b in boxes[1:]:
            m = m.merge(b)
        return m

    bundle.walls = _combine(wall_boxes)
    bundle.openings = _combine(opening_boxes)
    bundle.firewalls = _combine(firewall_boxes)
    bundle.roofs = _combine(roof_boxes)
    bundle.combustibles_per_material = {
        color: _combine(boxes) for color, boxes in combust_per_color.items()
    }
    return bundle
```

- [ ] **Step 4: Add geometry-extraction helpers**

These return `pv.Box` objects without calling `add_mesh`. Append:

```python
def _opening_box(self, opening, building, z0, is_exterior=True, fc_boundary=None):
    """Return a pv.Box for an opening, or None if inputs invalid."""
    ox, L, oy, W = building.boundary
    w_off, w, h_off, h = opening.boundary

    if is_exterior:
        if opening.wall == "y_min":
            b = [ox + w_off, ox + w_off + w, oy - 0.05, oy + 0.05,
                 z0 + h_off, z0 + h_off + h]
        elif opening.wall == "y_max":
            b = [ox + w_off, ox + w_off + w, oy + W - 0.05, oy + W + 0.05,
                 z0 + h_off, z0 + h_off + h]
        elif opening.wall == "x_min":
            b = [ox - 0.05, ox + 0.05, oy + w_off, oy + w_off + w,
                 z0 + h_off, z0 + h_off + h]
        else:  # x_max
            b = [ox + L - 0.05, ox + L + 0.05, oy + w_off, oy + w_off + w,
                 z0 + h_off, z0 + h_off + h]
    else:
        if fc_boundary is None:
            return None
        fx_min, fx_max, fy_min, fy_max = fc_boundary
        if opening.wall == "y_min":
            b = [ox + fx_min + w_off, ox + fx_min + w_off + w,
                 oy + fy_min - 0.05, oy + fy_min + 0.05,
                 z0 + h_off, z0 + h_off + h]
        elif opening.wall == "y_max":
            b = [ox + fx_min + w_off, ox + fx_min + w_off + w,
                 oy + fy_max - 0.05, oy + fy_max + 0.05,
                 z0 + h_off, z0 + h_off + h]
        elif opening.wall == "x_min":
            b = [ox + fx_min - 0.05, ox + fx_min + 0.05,
                 oy + fy_min + w_off, oy + fy_min + w_off + w,
                 z0 + h_off, z0 + h_off + h]
        else:  # x_max
            b = [ox + fx_max - 0.05, ox + fx_max + 0.05,
                 oy + fy_min + w_off, oy + fy_min + w_off + w,
                 z0 + h_off, z0 + h_off + h]
    return pv.Box(bounds=b)


def _firewall_boxes(self, fc, building, z0, z1):
    """Return list of pv.Box for a fire compartment's interior firewalls."""
    ox, L, oy, W = building.boundary
    x_min, x_max, y_min, y_max = fc.boundary
    t = fc.firewall_thickness
    boxes = []
    if t <= 0:
        return boxes
    if x_min > 0 and not is_coplanar(fc.boundary, L, W, "x_min"):
        boxes.append(pv.Box(bounds=[
            ox + x_min - t/2, ox + x_min + t/2,
            oy + y_min, oy + y_max, z0, z1,
        ]))
    if x_max < L and not is_coplanar(fc.boundary, L, W, "x_max"):
        boxes.append(pv.Box(bounds=[
            ox + x_max - t/2, ox + x_max + t/2,
            oy + y_min, oy + y_max, z0, z1,
        ]))
    if y_min > 0 and not is_coplanar(fc.boundary, L, W, "y_min"):
        boxes.append(pv.Box(bounds=[
            ox + x_min, ox + x_max,
            oy + y_min - t/2, oy + y_min + t/2, z0, z1,
        ]))
    if y_max < W and not is_coplanar(fc.boundary, L, W, "y_max"):
        boxes.append(pv.Box(bounds=[
            ox + x_min, ox + x_max,
            oy + y_max - t/2, oy + y_max + t/2, z0, z1,
        ]))
    return boxes


def _collect_combustible_boxes(self, fc, ox, oy, z_offset, per_color: dict):
    """Populate per_color dict: {hex_color: [pv.Box, ...]}."""
    from models.materials import COMBUSTIBLE_LIBRARY
    from models.combustibles import SPECIALIZED_COMPONENTS
    from models.geometry import layout_items_in_fc

    colors = {
        "BROWN": "#8B4513", "RED": "#CD5C5C", "SALMON": "#FA8072",
        "GRAY": "#808080", "KHAKI": "#BDB76B", "IVORY": "#FFFFF0",
        "MAGENTA": "#FF00FF", "ORANGE": "#FFA500",
    }
    material_colors = {
        "ALUMINUM": "#c0c0c0", "STEEL": "#4a5568",
        "JET_FUEL": "#b45309", "SOLID_PROPELLANT": "#dc2626",
        "GASOLINE": "#f59e0b", "ELECTROLYTE": "#06b6d4",
        "WOOD": "#92400e",
    }

    all_items = []

    for sc in fc.specialized_components:
        if isinstance(sc, dict) and "key" in sc and "x" not in sc:
            comp = SPECIALIZED_COMPONENTS.get(sc["key"])
            if not comp:
                continue
            for ci in range(sc.get("count", 1)):
                all_items.append({
                    "length": comp.total_length,
                    "width": comp.total_width,
                    "height": comp.total_height,
                    "color": "GRAY",
                    "component_key": sc["key"],
                    "_comp": comp,
                    "_instance": ci,
                })

    for cb in fc.combustibles:
        if isinstance(cb, dict) and "key" in cb and "x" not in cb:
            cb_def = COMBUSTIBLE_LIBRARY.get(cb["key"], {})
            if not cb_def:
                continue
            length = cb_def.get("length", 1.0)
            width = cb_def.get("width", 0.8)
            rotation = cb.get("rotation", 0)
            if rotation == 90:
                length, width = width, length
            for _ in range(cb.get("count", 1)):
                all_items.append({
                    "length": length, "width": width,
                    "height": cb_def.get("height", 0.5),
                    "color": cb_def.get("color", "BROWN"),
                    "component_key": None,
                })

    placed = layout_items_in_fc(fc.boundary, all_items, margin=1.0, gap=0.5)

    for item in placed:
        comp_key = item.get("component_key")
        comp = item.get("_comp")
        if comp_key and comp:
            for part in comp.parts:
                col = material_colors.get(part.material_key, "#CD853F")
                box = pv.Box(bounds=(
                    ox + item["x"] + part.dx,
                    ox + item["x"] + part.dx + part.length,
                    oy + item["y"] + part.dy,
                    oy + item["y"] + part.dy + part.width,
                    part.dz + z_offset,
                    part.dz + part.height + z_offset,
                ))
                per_color.setdefault(col, []).append(box)
        else:
            col = colors.get(item.get("color", "BROWN"), "#CD853F")
            box = pv.Box(bounds=(
                ox + item["x"], ox + item["x"] + item["length"],
                oy + item["y"], oy + item["y"] + item["width"],
                item.get("z", 0) + z_offset,
                item.get("z", 0) + item["height"] + z_offset,
            ))
            per_color.setdefault(col, []).append(box)
```

- [ ] **Step 5: Swap `_render_buildings_group` to cache path**

Replace `_render_buildings_group` with the cached version:

```python
def _render_buildings_group(self, bg):
    """Render building bundles from cache; returns bbox tuple."""
    buildings = bg.buildings
    global_max_x = global_max_y = global_max_z = -float("inf")
    global_min_x = global_min_y = float("inf")

    active_sigs = set()
    for bi, building in enumerate(buildings):
        ox, L, oy, W = building.boundary
        t = building.wall_thickness
        is_highlighted = bi == self._highlighted_building
        wall_opacity = 1.0 if is_highlighted else 0.6
        edge_color = "#f97316" if is_highlighted else "#45475a"
        edge_width = 3 if is_highlighted else 1

        global_min_x = min(global_min_x, ox - t)
        global_max_x = max(global_max_x, ox + L + t)
        global_min_y = min(global_min_y, oy - t)
        global_max_y = max(global_max_y, oy + W + t)
        total_h = 0.0
        for s in building.stories:
            total_h = max(total_h, s.z_bottom + s.height)
        if total_h == 0.0:
            total_h = building.height
        global_max_z = max(global_max_z, total_h)

        sig = _signature(building)
        active_sigs.add(sig)
        bundle = self._building_cache.get(sig)
        if bundle is None:
            bundle = self._build_bundle(building)
            self._building_cache[sig] = bundle
            if len(self._building_cache) > self._cache_max:
                oldest = next(iter(self._building_cache))
                self._building_cache.pop(oldest)

        self._attach_bundle(bundle, wall_opacity, edge_color, edge_width)

    # Detach stale bundles (present in cache but not in current scene)
    for sig, bundle in list(self._building_cache.items()):
        if sig not in active_sigs and bundle.actors:
            for a in bundle.actors.values():
                try:
                    self.plotter.remove_actor(a)
                except Exception:
                    pass
            bundle.actors.clear()

    if global_min_x == float("inf"):
        return None
    if global_max_z == -float("inf"):
        global_max_z = 3.0
    return (global_min_x, global_max_x, global_min_y, global_max_y, global_max_z)

def _attach_bundle(self, bundle: BuildingMeshBundle,
                   wall_opacity: float, edge_color: str, edge_width: int):
    """Ensure bundle meshes are visible in the plotter; add to buildings group."""
    # If already attached, just update visual props for highlight state.
    if bundle.actors:
        for key, actor in bundle.actors.items():
            if key == "walls" or key == "firewalls":
                actor.prop.opacity = wall_opacity
                actor.prop.edge_color = edge_color
                actor.prop.line_width = edge_width
            self._add_to_group("buildings", actor)
        return

    if bundle.walls is not None:
        a = self.plotter.add_mesh(bundle.walls, color="#808080",
                                  opacity=wall_opacity, show_edges=True,
                                  edge_color=edge_color, line_width=edge_width)
        bundle.actors["walls"] = a
        self._add_to_group("buildings", a)
    if bundle.firewalls is not None:
        a = self.plotter.add_mesh(bundle.firewalls, color="#808080",
                                  opacity=0.6, show_edges=True,
                                  edge_color="#45475a", line_width=1)
        bundle.actors["firewalls"] = a
        self._add_to_group("buildings", a)
    if bundle.openings is not None:
        a = self.plotter.add_mesh(bundle.openings, color="#4CAF50", opacity=0.8)
        bundle.actors["openings"] = a
        self._add_to_group("buildings", a)
    if bundle.roofs is not None:
        a = self.plotter.add_mesh(bundle.roofs, color="#888888", opacity=0.4)
        bundle.actors["roofs"] = a
        self._add_to_group("buildings", a)
    for color, mesh in bundle.combustibles_per_material.items():
        if mesh is None:
            continue
        a = self.plotter.add_mesh(mesh, color=color, opacity=0.8)
        bundle.actors[f"comb_{color}"] = a
        self._add_to_group("combustibles", a)
```

- [ ] **Step 6: Update `_do_full_render` to not `plotter.clear()`**

The old safety-net `self.plotter.clear()` inside `_do_full_render` (Task 10, Step 3) now defeats the cache. Change:

```python
def _do_full_render(self):
    self.wall_actors.clear()
    self.opening_actors.clear()
    # Clear non-building groups; buildings handled by cache attach/detach.
    self._clear_group("combustibles")
    self._clear_group("heat_source")
    self._clear_group("slices")
    self._clear_group("devices")
    self._clear_group("origin")
    # NOTE: do NOT call self.plotter.clear() — it wipes cached building actors.

    bg = self._bg
    if bg is None:
        return

    # Detach all buildings first (so _attach_bundle re-adds cleanly in new order)
    for bundle in self._building_cache.values():
        if bundle.actors:
            for a in bundle.actors.values():
                try:
                    self.plotter.remove_actor(a)
                except Exception:
                    pass
            bundle.actors.clear()
    self._clear_group("buildings")

    bbox = self._render_buildings_group(bg)
    if bbox is None:
        return

    self._render_heat_source_group(bg, bbox)
    self._render_slices_devices_group(bg, bbox)
    self._render_origin(bg)
    self._finalize_camera(bbox)
```

- [ ] **Step 7: Add `clear_cache` method + wire to `new_project`**

Append to `Viewer3D`:

```python
def clear_cache(self):
    """Drop all cached bundles and their actors."""
    for bundle in self._building_cache.values():
        for a in bundle.actors.values():
            try:
                self.plotter.remove_actor(a)
            except Exception:
                pass
    self._building_cache.clear()
```

In `ui/mainwindow.py`, in `new_project`, after creating the new `BuildingGroup`:

```python
self.viewer_3d.clear_cache()
```

(Insert it before `self._refresh_scene_list()`.)

- [ ] **Step 8: Smoke test — cache hit benchmark**

```bash
python main.py
```

Steps:
1. Select warrick_power_plant → 生成设施全部建筑. Observe initial render time (expect ~0.5-1s).
2. Click again on the same facility. Re-render should be noticeably faster (bundles cached).
3. Move one building (edit offset). Only that building rebuilds; others stay smooth.
4. Change heat source azimuth. Building meshes do not re-build.

- [ ] **Step 9: Commit**

```bash
git add ui/viewer_3d.py ui/mainwindow.py
git commit -m "feat(viewer): in-memory mesh bundle cache for fast re-renders"
```

---

## Task 13: End-to-end smoke test (all 7 bugs)

**Files:** none (manual verification)

- [ ] **Step 1: Full regression smoke**

```bash
python main.py
```

Run through the 7-bug checklist:

1. **3D double refresh**: Change azimuth slider → observe log (no second 3D render in terminal output). Building does not flicker. ✓ if smooth.
2. **Heat source on face**: Default model shows a semi-transparent colored plane on YMAX face (north). Set azimuth=45° → two planes split across YMAX + XMAX; elevation=30° adds ZMAX plane. Buildings still visible through planes. ✓
3. **Defaults**: Start fresh → 模拟时间 = 600s, 网格 = 1.0m. ✓
4. **Slice/device partial update**: Toggle 切片输出 checkbox → slice planes appear/disappear, buildings do not flicker. ✓
5. **Combustible dialog**: Pick any equivalent or specialized building → 可燃物管理… → dialog shows populated FC rows. ✓
6. **Toolbar gone**: No row of 新建/打开/保存/导出 buttons below the menu. Door/window tab height visibly reduced. ✓
7. **Generation speed**: Select warrick + 生成全部建筑 twice in a row. Second time obviously faster (cache hit). ✓

- [ ] **Step 2: Run full unit test suite**

```bash
pytest tests/ -q
```

Expected: all green except 2 pre-existing `test_parameter_engine.py::TestDistributeExteriorOpenings` failures (not in scope).

- [ ] **Step 3: Final commit (if any dangling formatting)**

```bash
git status
# If clean, nothing to commit. Otherwise:
git add -A
git commit -m "chore: smoke-test cleanup"
```

---

## Rollout note

All tasks touch isolated files with no schema migration beyond `BuildingGroup.from_dict`, which is backward-compatible. Existing saved `.json` configs will auto-migrate on load.

Pre-existing test failures in `test_parameter_engine.py` are unrelated and left alone.
