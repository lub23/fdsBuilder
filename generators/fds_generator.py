#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@File  : fds_generator.py
@Author: Lubber
@Date  : 2026-02-27
@Version : 3.0
@Desc  : FDS file generator for boundary-based BuildingGroup model
"""

import re
import math
from collections import namedtuple
from models.building import (
    BuildingGroup,
    Building,
    Story,
    Opening,
    FireCompartment,
    Roof,
)
from models.geometry import (
    detect_coplanar_openings,
    wall_length_for_building,
    wall_length_for_fc,
    resolve_negative_offset,
    is_coplanar,
)
from models.materials import MATERIAL_LIBRARY, COMBUSTIBLE_LIBRARY
from models.combustibles import SPECIALIZED_COMPONENTS


# Result returned by FDSGenerator._compute_mesh.
#
# Fields
# ------
# domain : list[float]
#     Integer-rounded [x0, x1, y0, y1, z0, z1] in metres.
# grid_size : float
#     Default uniform cell size for the coarse meshes (metres).
# num_meshes : int
#     Total number of meshes emitted: 4 (no refinement) or 5 (with refinement).
# refinement : dict or None
#     None when refinement is disabled.  When enabled it carries:
#       rad_wall : str
#           Source-facing wall id ('x_min' | 'x_max' | 'y_min' | 'y_max').
#       grid_size : float
#           Cell size inside the refinement strip (metres).
#       depth : float
#           Refinement strip depth, rounded to a multiple of both grid sizes
#           so cell edges still align across the coarse/fine interface.
#       xb : list[float]
#           [x0, x1, y0, y1, z0, z1] bounding box of the refinement mesh.
#       ijk : tuple[int, int, int]
#           (nx_ref, ny_ref, nz_ref) cells for the refinement mesh.
MeshPlan = namedtuple(
    "MeshPlan",
    ["domain", "grid_size", "num_meshes", "refinement"],
)


# Minimum penetration of HOLE in the wall-normal direction.
# When ``THICKEN=.TRUE.`` is set on an OBST, FDS expands the OBST to at
# least one mesh cell thick — which can be much larger than the physical
# wall thickness (e.g. 0.3 m wall on a 1.5 m grid becomes 1.5 m thick).
# The HOLE must extend beyond the thickened OBST on both sides so that
# FDS removes enough solid cells to create a visible opening.  The
# penetration therefore needs to be at least one grid cell size in each
# wall-normal direction, beyond the OBST boundary.
#
# A conservative constant is used here (1.0 m) so the HOLE always
# punches through regardless of grid size.  This is safe because FDS
# only removes solid cells that overlap the HOLE volume — extending
# the HOLE into free gas does nothing harmful.
HOLE_PENETRATION = 1.0

# Stefan-Boltzmann constant in kW/m²/K⁴
SIGMA_SB = 5.670374419e-11

# External radiation source geometry.  The heat-source VENT sits exactly
# 1 m outside the nearest exterior wall / highest ceiling.  When a separate
# source-side mesh is carved out, it must be thicker than the physical gap:
# FDS 6.10 Poisson initialisation can fail for independent MPI meshes that are
# only 1-2 cells thick in one direction.
HEAT_SOURCE_GAP = 1.0
HEAT_SOURCE_MAX_GRID = 1.0
HEAT_FLUX_PROBE_WALL_OFFSET = 0.001
DEFAULT_DEVC_DT = 0.1
MIN_REFINED_MESH_CELLS = 3
DEFAULT_MPI_PROCESSES = 4


def _compute_sibling_overlaps(fc, siblings):
    """Return [(x1, x2, y1, y2), ...] exclusion boxes for *fc*.

    For each sibling compartment on the same story whose boundary area
    is strictly smaller than *fc*'s, build an exclusion rectangle that
    mirrors the sibling's interior **inflated outward by (firewall_t/2 + 0.25)**
    on every side.  A firewall occupying
    ``[boundary - t/2, boundary + t/2]`` straddles its centre line, so
    the unsafe zone extends ``firewall_t/2`` past the geometric
    sibling boundary.  Adding a 0.25 m buffer keeps items clear of
    both the firewall shell and any transverse surface backlog.

    The exclusion therefore is effectively
    ``sibling.boundary.padded_by(firewall_t/2 + 0.25)`` restricted to
    the part that lies inside *fc*.
    """
    def _area(b):
        return (b[1] - b[0]) * (b[3] - b[2])

    fx1, fx2, fy1, fy2 = fc.boundary
    fc_area = _area(fc.boundary)
    excl: list[tuple[float, float, float, float]] = []
    for sib in siblings:
        if sib is fc:
            continue
        if _area(sib.boundary) >= fc_area:
            continue
        # Firewall straddles its centre line, so it extends half its
        # thickness *outside* the sibling boundary.  Adding that half +
        # a small buffer avoids items landing on the firewall shell.
        wall_t = float(getattr(sib, "firewall_thickness", 0.5) or 0.5)
        inflate = wall_t / 2 + 0.25
        sx1, sx2, sy1, sy2 = sib.boundary
        # Inflate first, then intersect with the parent FC rectangle.
        ix1, ix2 = max(fx1, sx1 - inflate), min(fx2, sx2 + inflate)
        iy1, iy2 = max(fy1, sy1 - inflate), min(fy2, sy2 + inflate)
        if ix2 > ix1 + 1e-6 and iy2 > iy1 + 1e-6:
            excl.append((ix1, ix2, iy1, iy2))
    return excl


_LAUNCH_SITE_KEYS = (
    "发射场", "发射区", "发射台", "发射井", "发射塔",
    "Launch site", "Launch pad", "launchpad", "launch_site", "launchsite",
)
_ASSEMBLY_KEYS = (
    "总装", "部装", "装配", "组装", "装联",
    "主厂区", "装配区", "组装区", "总装区", "总装主厂区",
    "总装厂房", "装配车间", "组装车间", "部装车间", "总装车间",
    "Assembly", "Sub-assembly", "Subassembly",
)
_STORAGE_KEYS = (
    "存储区", "部件存储区", "仓库", "库房", "Storage", "stockroom",
)
_PROCESSING_KEYS = (
    "加工", "处理", "machining", "Processing", "Workshop",
    "加工作业", "原料", "废料", "化学品", "机加工",
)
_OFFICE_KEYS = (
    "办公", "控制", "指挥", "测控", "设备间", "设备机房",
    "Office", "Command", "Equipment",
)


def _fc_role(fc, story, building) -> str:
    """Classify a fire compartment by FC / story / building name.

    Returns one of:
        "launch"     - 发射场 / 发射区 / 发射台 (rockets upright).
        "assembly"   - 总装/部装/装配/组装车间 (rockets laid down).
                       Includes "部件装配区"-style sub-assembly cells, even
                       when the FC's name also contains "存储" (a buffer cell
                       that physically belongs to the assembly flow).
        "processing" - 加工厂房 / Workshop.
        "office"     - 办公 / 控制 / 测控 / 设备机房.
        "storage"    - Generic storage. Rockets are not placed here unless
                       the **building** is itself an assembly hall.

    Lookup is layered: FC name → story name → building name.  Each layer
    may override earlier choices if **building context** indicates otherwise.
    """

    fc_text = (getattr(fc, "name", "") or "").strip()
    story_text = (getattr(story, "name", "") or "").strip()
    building_text = " ".join(filter(None, [
        getattr(building, "cn_name", ""),
        getattr(building, "name", ""),
    ])).strip()

    building_is_assembly = any(k in building_text for k in _ASSEMBLY_KEYS)
    building_is_launch = any(k in building_text for k in _LAUNCH_SITE_KEYS)

    initial = "other"
    if any(k in fc_text for k in _LAUNCH_SITE_KEYS):
        initial = "launch"
    elif any(k in fc_text for k in _ASSEMBLY_KEYS):
        initial = "assembly"
    elif any(k in fc_text for k in _OFFICE_KEYS):
        initial = "office"
    elif any(k in fc_text for k in _PROCESSING_KEYS):
        initial = "processing"
    elif any(k in fc_text for k in _STORAGE_KEYS):
        initial = "storage"

    if story_text:
        if any(k in story_text for k in _LAUNCH_SITE_KEYS):
            initial = "launch"
        elif any(k in story_text for k in _ASSEMBLY_KEYS):
            initial = "assembly"

    if initial == "other":
        if any(k in building_text for k in _LAUNCH_SITE_KEYS):
            initial = "launch"
        elif building_is_assembly:
            initial = "assembly"
        elif any(k in building_text for k in _PROCESSING_KEYS):
            initial = "processing"

    if initial == "storage" and building_is_assembly:
        if any(k in fc_text for k in ("部件", "装配", "组装", "总装", "部装")):
            initial = "assembly"

    return initial


def _resolve_rocket_placement(fc, story, building) -> dict:
    """Decide, for a given fire compartment, whether to place rockets and how.

    Layout rule:
    * assembly cells place rockets horizontally, matching shop-floor assembly.
    * launch-site cells place rockets upright, matching pad/preparation scenes.

    * role="assembly" -> rockets laid-down horizontally.
    * role="launch"   -> rockets upright.
    * everything else  -> never place rockets.
    """
    role = _fc_role(fc, story, building)
    if role == "assembly":
        return {"allow_rockets": True, "horizontal": True, "role": role}
    if role == "launch":
        return {"allow_rockets": True, "horizontal": False, "role": role}
    return {"allow_rockets": False, "horizontal": False, "role": role}


def _warn_rocket_skipped(fc, key: str, count: int, role: str) -> None:
    """Print a single WARNING per (fc, key) describing skipped rockets."""
    print(
        f"WARNING: {fc.name} (role={role}): dropped {count}x {key} — "
        f"rockets only allowed in assembly or launch-site fire compartments."
    )


# ============================================================
# FDS Generator
# ============================================================
class FDSGenerator:
    """FDS file generator for BuildingGroup."""

    def __init__(self, building_group):
        """Accept a BuildingGroup directly, or a legacy model object.

        Legacy callers may pass an object with a ``building_group`` attribute;
        we extract the BuildingGroup from it.
        """
        if isinstance(building_group, BuildingGroup):
            self.bg = building_group
        elif hasattr(building_group, "building_group"):
            # Legacy compat: old callers pass a model with .building_group
            bg = building_group.building_group
            if isinstance(bg, BuildingGroup):
                self.bg = bg
            else:
                self.bg = BuildingGroup.from_dict(
                    bg if isinstance(bg, dict) else bg.to_dict()
                )
            # Copy top-level fields from legacy model if present
            if hasattr(building_group, "heat_source") and building_group.heat_source:
                self.bg.heat_source = building_group.heat_source
            if hasattr(building_group, "simulation_time"):
                self.bg.simulation_time = building_group.simulation_time
            if hasattr(building_group, "domain"):
                self.bg.domain = building_group.domain
            if hasattr(building_group, "output"):
                self.bg.output = building_group.output
            if hasattr(building_group, "materials"):
                self._materials_override = building_group.materials
        else:
            raise TypeError(f"Expected BuildingGroup, got {type(building_group)}")

        # Deduplication cache for noisy informational messages — multiple
        # ``_compute_mesh`` calls during a single ``generate()`` run would
        # otherwise reprint the same NOTE/WARNING warnings every time.
        # Keyed by message content + a caller-supplied tag so genuinely
        # different warnings still surface.
        self._warnings_seen: set[tuple] = set()
        # Cached by generate() after _compute_mesh.
        self._num_meshes: int = 0
        self._grid_size: float = 0.0
        self._hole_penetration: float = 0.0

    def _warn_once(self, message: str, key=None) -> None:
        """Print *message* once.  *key* disambiguates recurring warnings
        about different objects (e.g. different depths/grid_sizes)."""
        cache_key = key if key is not None else message
        if cache_key in self._warnings_seen:
            return
        self._warnings_seen.add(cache_key)
        print(message)

    # ------------------------------------------------------------------
    # Low-level emitters
    # ------------------------------------------------------------------
    def _emit_obst(self, lines, bounds, surf="WALL", comment="", thicken=False):
        """Append an &OBST line.  bounds = [x1, x2, y1, y2, z1, z2].

        Args:
            thicken: When ``True``, append ``THICKEN=.TRUE.`` so FDS forces the
                OBST to be at least one mesh cell thick.  Required for thin
                walls (< 1 grid cell) to ensure HOLEs cut through properly.
        """
        x1, x2, y1, y2, z1, z2 = bounds
        c = f"  ! {comment}" if comment else ""
        thick = ", THICKEN=.TRUE." if thicken else ""
        lines.append(
            f"&OBST XB={x1:.3f},{x2:.3f},{y1:.3f},{y2:.3f},{z1:.3f},{z2:.3f}, SURF_ID='{surf}'{thick} /{c}\n"
        )

    def _emit_hole(self, lines, bounds, comment=""):
        """Append a &HOLE line.  bounds = [x1, x2, y1, y2, z1, z2]."""
        x1, x2, y1, y2, z1, z2 = bounds
        c = f"  ! {comment}" if comment else ""
        lines.append(
            f"&HOLE XB={x1:.3f},{x2:.3f},{y1:.3f},{y2:.3f},{z1:.3f},{z2:.3f} /{c}\n"
        )

    def gen_box(self, x1, x2, y1, y2, z1, z2, surf="WALL"):
        """Compat helper returning a formatted &OBST string."""
        return f"&OBST XB={x1:.3f},{x2:.3f},{y1:.3f},{y2:.3f},{z1:.3f},{z2:.3f}, SURF_ID='{surf}' /\n"

    # ------------------------------------------------------------------
    # Radiation-source orientation helpers
    # ------------------------------------------------------------------
    def _source_orientation(self):
        """Unit vector pointing toward the external radiation source.

        Compass convention (clockwise from east, see models/heat_source.py):
        azimuth=0° -> +X (XMAX), 90° -> -Y (YMIN), 180° -> -X (XMIN),
        270° -> +Y (YMAX).  Elevation tilts the vector upward.
        """
        hs = self.bg.heat_source
        az = hs.get("azimuth", 0)
        el = hs.get("elevation", 0)
        from models.heat_source import source_orientation
        return source_orientation(az, el)

    def _source_horizontal_dir(self):
        """Dominant horizontal axis/sign of the source direction.

        Returns ``("x"|"y", +1|-1)`` — the axis a laid-down rocket lies along
        and the sign its nose points toward (toward the door/source).
        """
        from models.heat_source import horizontal_axis_sign
        az = self.bg.heat_source.get("azimuth", 0)
        return horizontal_axis_sign(az)

    @staticmethod
    def _part_box(item, part, ox, oy, z0):
        """World-space box + extents for one component part.

        Honours the item's lay-down orientation (``_horizontal`` / ``_axis`` /
        ``_sign``).  Vertical components keep the native part frame; horizontal
        rockets rotate their long (height) axis onto the chosen ground axis,
        with ``_sign`` < 0 mirroring the nose to the opposite end.

        Returns ``(px, py, pz, ext_x, ext_y, ext_z)``.
        """
        if not item.get("_horizontal"):
            if item.get("_rotate_xy"):
                comp = item["_comp"]
                px = ox + item["x"] + part.dy
                py = oy + item["y"] + comp.total_length - part.dx - part.length
                pz = z0 + part.dz
                return px, py, pz, part.width, part.length, part.height
            px = ox + item["x"] + part.dx
            py = oy + item["y"] + part.dy
            pz = z0 + part.dz
            return px, py, pz, part.length, part.width, part.height

        comp = item["_comp"]
        axis = item.get("_axis", "x")
        sign = item.get("_sign", 1)
        long_extent = comp.total_height  # rocket's vertical axis becomes ground length
        along = part.dz if sign >= 0 else (long_extent - part.dz - part.height)
        if axis == "x":
            px = ox + item["x"] + along
            py = oy + item["y"] + part.dy
            pz = z0 + part.dx
            return px, py, pz, part.height, part.width, part.length
        # axis == "y"
        py = oy + item["y"] + along
        px = ox + item["x"] + part.dy
        pz = z0 + part.dx
        return px, py, pz, part.width, part.height, part.length

    # ------------------------------------------------------------------
    # Materials & Surfaces
    # ------------------------------------------------------------------
    def _generate_materials(self, lines):
        """Generate &MATL and &SURF blocks."""
        bg = self.bg
        buildings = bg.buildings

        # Collect which MATL keys are referenced
        wall_matl_keys = set()
        combustible_keys = set()
        component_matl_keys = set()

        # Legacy materials override (for existing UI integration)
        materials_map = getattr(self, "_materials_override", None) or {}
        wall_matl_keys.update(materials_map.values())

        for b in buildings:
            for story in b.stories:
                # FC-level combustibles / components
                for fc in story.fire_compartments:
                    for cb in fc.combustibles:
                        key = cb.get("key", "")
                        if key:
                            combustible_keys.add(key)
                    for sc_info in fc.specialized_components:
                        comp = SPECIALIZED_COMPONENTS.get(sc_info.get("key", ""))
                        if comp:
                            for part in comp.parts:
                                if part.material_key:
                                    component_matl_keys.add(part.material_key)
                # Story-level combustibles / components
                for cb in story.combustibles:
                    key = cb.get("key", "")
                    if key:
                        combustible_keys.add(key)
                for sc_info in story.specialized_components:
                    comp = SPECIALIZED_COMPONENTS.get(sc_info.get("key", ""))
                    if comp:
                        for part in comp.parts:
                            if part.material_key:
                                component_matl_keys.add(part.material_key)

        lines.append("! ========== 追踪粒子 ==========\n")
        lines.append(
            "&PART ID='TRACER',\n"
            "      MASSLESS=.TRUE.,\n"
            "      MONODISPERSE=.TRUE.,\n"
            "      AGE=60.0,\n"
            "      SAMPLING_FACTOR=10 /\n\n"
        )

        lines.append("! ========== 材料定义 ==========\n")

        # Wall / structural materials
        all_structural = wall_matl_keys | component_matl_keys
        for mat_name in sorted(all_structural):
            mat = MATERIAL_LIBRARY.get(mat_name)
            if mat:
                lines.append(
                    f"&MATL ID='{mat_name}', DENSITY={mat['DENSITY']}, "
                    f"CONDUCTIVITY={mat['CONDUCTIVITY']}, SPECIFIC_HEAT={mat['SPECIFIC_HEAT']} /\n"
                )
            else:
                cb = COMBUSTIBLE_LIBRARY.get(mat_name)
                if cb and cb.get("matl"):
                    mt = cb["matl"]
                    hoc = mt.get("HEAT_OF_COMBUSTION", 0)
                    lines.append(
                        f"&MATL ID='{mat_name}', DENSITY={mt['DENSITY']}, "
                        f"CONDUCTIVITY={mt['CONDUCTIVITY']}, SPECIFIC_HEAT={mt['SPECIFIC_HEAT']}"
                        f"{f', HEAT_OF_COMBUSTION={hoc}' if hoc else ''} /\n"
                    )

        # Default structural materials (always need CONCRETE at minimum)
        for default_mat in ("CONCRETE",):
            if default_mat not in all_structural and default_mat in MATERIAL_LIBRARY:
                mat = MATERIAL_LIBRARY[default_mat]
                lines.append(
                    f"&MATL ID='{default_mat}', DENSITY={mat['DENSITY']}, "
                    f"CONDUCTIVITY={mat['CONDUCTIVITY']}, SPECIFIC_HEAT={mat['SPECIFIC_HEAT']} /\n"
                )

        lines.append("\n! ========== 表面定义 ==========\n")

        # Standard surfaces
        surfaces = {
            "WALL": ("walls", "墙体"),
            "FLOOR": ("floor", "地板"),
            "ROOF": ("roof", "屋顶"),
        }
        for surf_name, (mat_key, desc) in surfaces.items():
            mat_name = materials_map.get(mat_key, "CONCRETE")
            if mat_name in MATERIAL_LIBRARY:
                thick = MATERIAL_LIBRARY[mat_name]["THICKNESS"]
                lines.append(
                    f"&SURF ID='{surf_name}', MATL_ID='{mat_name}', THICKNESS={thick}, BACKING='VOID' /  ! {desc}\n"
                )

        comp_surfs_done = set()
        for mat_key in sorted(component_matl_keys):
            if mat_key in comp_surfs_done:
                continue
            if mat_key in COMBUSTIBLE_LIBRARY:
                # Component parts reference surf_id="{mat_key}_SURF" —
                # emit a SURF with HRRPUA/ignition from the combustible library
                cb_def = COMBUSTIBLE_LIBRARY[mat_key]
                surf_id = f"{mat_key}_SURF"
                if surf_id in comp_surfs_done:
                    continue
                hrrpua = cb_def.get("hrrpua", 300)
                ign_temp = cb_def.get("ignition_temp", 250)
                color = cb_def.get("color", "RED")
                lines.append(
                    f"&SURF ID='{surf_id}',\n"
                    f"      HRRPUA={hrrpua},\n"
                    f"      IGNITION_TEMPERATURE={ign_temp},\n"
                    f"      BURN_AWAY=.TRUE.,\n"
                    f"      THICKNESS=0.05,\n"
                    f"      PART_ID='TRACER',\n"
                    f"      COLOR='{color}' /\n\n"
                )
                comp_surfs_done.add(surf_id)
                continue
            surf_id = f"{mat_key}_SURF"
            mat = MATERIAL_LIBRARY.get(mat_key)
            if mat:
                thick = mat.get("THICKNESS", 0.1)
                lines.append(
                    f"&SURF ID='{surf_id}', MATL_ID='{mat_key}', THICKNESS={thick} /\n"
                )
                comp_surfs_done.add(surf_id)

        # Combustible SURF definitions
        if combustible_keys:
            lines.append("\n! ========== 可燃物燃烧表面 ==========\n")
            for ck in sorted(combustible_keys):
                if ck not in COMBUSTIBLE_LIBRARY:
                    continue
                cb_def = COMBUSTIBLE_LIBRARY[ck]
                mt = cb_def.get("matl", {})
                if not mt:
                    continue
                surf_id = f"SURF_{ck}"
                density = mt.get("DENSITY", 500)
                conductivity = mt.get("CONDUCTIVITY", 0.2)
                specific_heat = mt.get("SPECIFIC_HEAT", 1.0)
                color = cb_def.get("color", "RED")

                # Non-burnable items (e.g. metal goods) are inert radiation
                # targets: a plain MATL + a non-pyrolysing SURF, no IGNITION /
                # BURN_AWAY.  Their probe is a heat-flux gauge (see below).
                if not cb_def.get("burnable", True):
                    matl_id = f"INERT_{ck}"
                    lines.append(
                        f"&MATL ID='{matl_id}',\n"
                        f" DENSITY={density},\n"
                        f" CONDUCTIVITY={conductivity},\n"
                        f" SPECIFIC_HEAT={specific_heat} /\n\n"
                    )
                    lines.append(
                        f"&SURF ID='{surf_id}',\n"
                        f"      MATL_ID='{matl_id}',\n"
                        f"      THICKNESS=0.05,\n"
                        f"      COLOR='{color}' /\n\n"
                    )
                    continue

                matl_id = f"PYRO_{ck}"
                ignition_temp = cb_def.get("ignition_temp", 250.0)
                hrrpua = cb_def.get("hrrpua", 300)

                lines.append(
                    f"&MATL ID='{matl_id}',\n"
                    f" DENSITY={density},\n"
                    f" CONDUCTIVITY={conductivity},\n"
                    f" SPECIFIC_HEAT={specific_heat} /\n\n"
                )

                lines.append(
                    f"&SURF ID='{surf_id}',\n"
                    f"      MATL_ID='{matl_id}',\n"
                    f"      HRRPUA={hrrpua},\n"
                    f"      IGNITION_TEMPERATURE={ignition_temp:.1f},\n"
                    f"      THICKNESS=0.05,\n"
                    f"      BURN_AWAY=.TRUE.,\n"
                    f"      BACKING='VOID',\n"
                    f"      PART_ID='TRACER',\n"
                    f"      COLOR='{color}' /\n\n"
                )

            lines.append("\n")

    # ------------------------------------------------------------------
    # Exterior walls
    # ------------------------------------------------------------------
    def _generate_exterior_walls(self, building, story, story_index, lines):
        """Generate 4 exterior wall OBST + openings as HOLE."""
        walls = building.get_exterior_walls(story_index)

        # Merge story-level exterior openings + coplanar FC openings
        all_exterior_openings = list(story.openings)
        all_exterior_openings += detect_coplanar_openings(building, story)

        for wall_id, obst_bounds in walls.items():
            wall_openings = [o for o in all_exterior_openings if o.wall == wall_id]
            self._emit_obst(
                lines, obst_bounds, surf="WALL", comment=f"ext wall {wall_id}",
                thicken=True,
            )
            for opening in wall_openings:
                hole = self._opening_to_hole(wall_id, obst_bounds, opening, building)
                self._emit_hole(lines, hole, comment=f"{opening.type} on {wall_id}")

    def _opening_to_hole(self, wall_id, obst_bounds, opening, building):
        """Convert an Opening to a HOLE bounding box for an exterior wall."""
        ox, L, oy, W = building.boundary
        w_off, w, h_off, h = opening.boundary
        pen = self._hole_penetration

        # Resolve negative w_offset
        if wall_id in ("y_min", "y_max"):
            wall_len = L
        else:
            wall_len = W
        if w_off < 0:
            w_off = resolve_negative_offset(w_off, w, wall_len)

        z0 = obst_bounds[4]  # z_bottom of the wall

        if wall_id == "y_min":
            return [
                max(ox + w_off, obst_bounds[0]),
                min(ox + w_off + w, obst_bounds[1]),
                obst_bounds[2] - pen,
                obst_bounds[3] + pen,
                z0 + h_off,
                z0 + h_off + h,
            ]
        elif wall_id == "y_max":
            return [
                max(ox + w_off, obst_bounds[0]),
                min(ox + w_off + w, obst_bounds[1]),
                obst_bounds[2] - pen,
                obst_bounds[3] + pen,
                z0 + h_off,
                z0 + h_off + h,
            ]
        elif wall_id == "x_min":
            return [
                obst_bounds[0] - pen,
                obst_bounds[1] + pen,
                max(oy + w_off, obst_bounds[2]),
                min(oy + w_off + w, obst_bounds[3]),
                z0 + h_off,
                z0 + h_off + h,
            ]
        else:  # x_max
            return [
                obst_bounds[0] - pen,
                obst_bounds[1] + pen,
                max(oy + w_off, obst_bounds[2]),
                min(oy + w_off + w, obst_bounds[3]),
                z0 + h_off,
                z0 + h_off + h,
            ]

    # ------------------------------------------------------------------
    # Fire compartment walls (non-coplanar only)
    # ------------------------------------------------------------------
    def _generate_firewalls(self, building, story, lines):
        """Generate partition wall OBSTs for fire compartments."""
        ox, L, oy, W = building.boundary
        z0, z1 = story.z_bottom, story.z_top

        for fc in story.fire_compartments:
            if fc.firewall_thickness <= 0:
                continue
            x_min, x_max, y_min, y_max = fc.boundary
            ft = fc.firewall_thickness

            # Only non-coplanar boundaries get firewalls
            # x_min boundary
            if x_min > 0 and not is_coplanar(fc.boundary, L, W, "x_min"):
                self._emit_obst(
                    lines,
                    [
                        ox + x_min - ft / 2,
                        ox + x_min + ft / 2,
                        oy + y_min,
                        oy + y_max,
                        z0,
                        z1,
                    ],
                    surf="WALL",
                    comment=f"firewall {fc.name} x_min",
                    thicken=True,
                )
            # x_max boundary
            if abs(x_max - L) > 1e-6 and not is_coplanar(fc.boundary, L, W, "x_max"):
                self._emit_obst(
                    lines,
                    [
                        ox + x_max - ft / 2,
                        ox + x_max + ft / 2,
                        oy + y_min,
                        oy + y_max,
                        z0,
                        z1,
                    ],
                    surf="WALL",
                    comment=f"firewall {fc.name} x_max",
                    thicken=True,
                )
            # y_min boundary
            if y_min > 0 and not is_coplanar(fc.boundary, L, W, "y_min"):
                self._emit_obst(
                    lines,
                    [
                        ox + x_min,
                        ox + x_max,
                        oy + y_min - ft / 2,
                        oy + y_min + ft / 2,
                        z0,
                        z1,
                    ],
                    surf="WALL",
                    comment=f"firewall {fc.name} y_min",
                    thicken=True,
                )
            # y_max boundary
            if abs(y_max - W) > 1e-6 and not is_coplanar(fc.boundary, L, W, "y_max"):
                self._emit_obst(
                    lines,
                    [
                        ox + x_min,
                        ox + x_max,
                        oy + y_max - ft / 2,
                        oy + y_max + ft / 2,
                        z0,
                        z1,
                    ],
                    surf="WALL",
                    comment=f"firewall {fc.name} y_max",
                    thicken=True,
                )

            # Non-coplanar FC openings (not on exterior walls) -> HOLE on firewalls
            for opening in fc.openings:
                if not is_coplanar(fc.boundary, L, W, opening.wall):
                    hole = self._fc_opening_to_hole(fc, opening, building, story)
                    self._emit_hole(lines, hole, comment=f"FC opening {opening.type}")

    def _fc_opening_to_hole(self, fc, opening, building, story):
        """Convert a FireCompartment opening to a HOLE on the partition firewall."""
        ox, _L, oy, _W = building.boundary
        x_min, x_max, y_min, y_max = fc.boundary
        ft = fc.firewall_thickness
        w_off, w, h_off, h = opening.boundary
        z0 = story.z_bottom
        wall_id = opening.wall
        pen = self._hole_penetration

        # Determine wall length for negative offset resolution
        wl = wall_length_for_fc(fc.boundary, wall_id)
        if w_off < 0:
            w_off = resolve_negative_offset(w_off, w, wl)

        if wall_id == "x_min":
            wx = ox + x_min
            return [
                wx - ft / 2 - pen,
                wx + ft / 2 + pen,
                oy + y_min + w_off,
                oy + y_min + w_off + w,
                z0 + h_off,
                z0 + h_off + h,
            ]
        elif wall_id == "x_max":
            wx = ox + x_max
            return [
                wx - ft / 2 - pen,
                wx + ft / 2 + pen,
                oy + y_min + w_off,
                oy + y_min + w_off + w,
                z0 + h_off,
                z0 + h_off + h,
            ]
        elif wall_id == "y_min":
            wy = oy + y_min
            return [
                ox + x_min + w_off,
                ox + x_min + w_off + w,
                wy - ft / 2 - pen,
                wy + ft / 2 + pen,
                z0 + h_off,
                z0 + h_off + h,
            ]
        else:  # y_max
            wy = oy + y_max
            return [
                ox + x_min + w_off,
                ox + x_min + w_off + w,
                wy - ft / 2 - pen,
                wy + ft / 2 + pen,
                z0 + h_off,
                z0 + h_off + h,
            ]

    # ------------------------------------------------------------------
    # Roof
    # ------------------------------------------------------------------
    def _generate_roof(self, building, story, lines):
        """Generate roof OBST and its openings as HOLEs."""
        ox, L, oy, W = building.boundary
        t = building.wall_thickness
        z = story.z_top
        roof = story.roof

        # Roof slab OBST
        self._emit_obst(
            lines,
            [
                ox - t / 2,
                ox + L + t / 2,
                oy - t / 2,
                oy + W + t / 2,
                z,
                z + roof.thickness,
            ],
            surf="ROOF",
            comment="roof slab",
        )

        # Roof openings (HOLEs for stairwells, skylights, etc.)
        for ro in roof.openings:
            bnd = ro.get("boundary", ro.get("bnd", [0, 0, 0, 0]))
            self._emit_hole(
                lines,
                [
                    ox + bnd[0],
                    ox + bnd[0] + bnd[1],
                    oy + bnd[2],
                    oy + bnd[2] + bnd[3],
                    z - 0.05,
                    z + roof.thickness + 0.05,
                ],
                comment="roof opening",
            )

    # ------------------------------------------------------------------
    # Combustibles (from fire compartment data)
    # ------------------------------------------------------------------
    def _emit_heat_flux_devc(self, lines, cx, cy, cz, devc_id):
        """Emit a RADIATIVE HEAT FLUX GAS gauge facing the radiation source.

        Sits just above the target top; its ORIENTATION points toward the
        source/door.  Used for every combustible (burnable + metal) and for
        inert specialized components.
        """
        sx, sy, sz = self._source_orientation()
        sx = 0.0 if abs(sx) < 1e-9 else sx
        sy = 0.0 if abs(sy) < 1e-9 else sy
        sz = 0.0 if abs(sz) < 1e-9 else sz
        lines.append(
            f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz + 0.10:.2f},\n"
            f"      QUANTITY='RADIATIVE HEAT FLUX GAS',\n"
            f"      ORIENTATION={sx:.3f},{sy:.3f},{sz:.3f},\n"
            f"      ID='{devc_id}' /\n"
        )

    def _emit_temp_devc(self, lines, cx, cy, cz, devc_id):
        """Emit a gas TEMPERATURE point probe just above an item's top."""
        lines.append(
            f"&DEVC XYZ={cx:.2f},{cy:.2f},{cz + 0.10:.2f}, "
            f"QUANTITY='TEMPERATURE', ID='{devc_id}' /\n"
        )

    def _emit_item_probes(self, lines, cx, cy, cz, base):
        """Two probes above an item: gas temperature + radiative heat flux.

        Applied uniformly to every combustible (burnable and metal).  IDs are
        derived from the OBST base (name-based, unique).
        """
        self._emit_temp_devc(lines, cx, cy, cz, f"T_{base}")
        self._emit_heat_flux_devc(lines, cx, cy, cz, f"HF_{base}")

    def _emit_component(self, lines, item, ox, oy, z0, grid_size, base):
        """Emit one specialized component's OBSTs + its two probes.

        Components are inert single-metal targets; like combustibles they get
        two probes above the top: a gas ``TEMPERATURE`` point and a
        ``RADIATIVE HEAT FLUX GAS`` gauge facing the source.
        """
        subgrid_tol = 1e-6
        comp = item["_comp"]
        ci = item["_instance"]
        lines.append(f"! {comp.name} #{ci + 1}\n")
        bx_lo = by_lo = float("inf")
        bx_hi = by_hi = z_top = -float("inf")
        for pi, part in enumerate(comp.parts):
            px, py, pz, ex, ey, ez = self._part_box(item, part, ox, oy, z0)
            is_subgrid = (
                ex < grid_size - subgrid_tol
                or ey < grid_size - subgrid_tol
                or ez < grid_size - subgrid_tol
            )
            thicken_kv = "THICKEN=.TRUE., " if is_subgrid else ""
            surf = part.surf_id or "INERT"
            lines.append(
                f"&OBST XB={px:.2f},{px + ex:.2f},"
                f"{py:.2f},{py + ey:.2f},"
                f"{pz:.2f},{pz + ez:.2f},\n"
                f" {thicken_kv}SURF_ID='{surf}',\n"
                f" ID='{base}_{pi}' /\n"
            )
            bx_lo, by_lo = min(bx_lo, px), min(by_lo, py)
            bx_hi, by_hi = max(bx_hi, px + ex), max(by_hi, py + ey)
            z_top = max(z_top, pz + ez)
        self._emit_item_probes(
            lines, (bx_lo + bx_hi) / 2, (by_lo + by_hi) / 2, z_top, base
        )

    def _emit_combustible(self, lines, item, ox, oy, z0, grid_size, base):
        """Emit one combustible OBST + its two probes.

        Burnable items keep a pyrolysing surface; non-burnable (metal) items
        are inert blocks.  Either way, two probes are placed above the item:
        a gas ``TEMPERATURE`` point and a ``RADIATIVE HEAT FLUX GAS`` gauge
        facing the source.  Probe IDs are derived from the OBST ID.
        """
        subgrid_tol = 1e-6
        key = item["key"]
        surf_id = f"SURF_{key}"
        cb_def = COMBUSTIBLE_LIBRARY.get(key, {})
        burnable = cb_def.get("burnable", True)
        x1 = ox + item["x"]
        x2 = x1 + item["length"]
        y1 = oy + item["y"]
        y2 = y1 + item["width"]
        z1 = z0
        z2 = z0 + item["height"]
        is_subgrid = (
            item["length"] < grid_size - subgrid_tol
            or item["width"] < grid_size - subgrid_tol
            or item["height"] < grid_size - subgrid_tol
        )
        thicken_kv = "THICKEN=.TRUE., " if is_subgrid else ""
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        label = item.get("name", key)
        if burnable:
            bulk_density = cb_def.get("matl", {}).get("DENSITY", 500)
            lines.append(
                f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                f"{z1:.2f},{z2:.2f},\n"
                f" {thicken_kv}SURF_IDS='{surf_id}','INERT','INERT',\n"
                f" BULK_DENSITY={bulk_density},\n"
                f" ID='{base}' / ! {label}\n"
            )
        else:
            lines.append(
                f"&OBST XB={x1:.2f},{x2:.2f},{y1:.2f},{y2:.2f},"
                f"{z1:.2f},{z2:.2f},\n"
                f" {thicken_kv}SURF_ID='{surf_id}',\n"
                f" ID='{base}' / ! {label} (inert target)\n"
            )
        # Two probes above every combustible (burnable + metal).
        self._emit_item_probes(lines, cx, cy, z2, base)

    @staticmethod
    def _component_orientation_axis(orientation):
        if orientation is None:
            return "x"
        value = str(orientation).strip().lower()
        if value in {
            "y", "ns", "north_south", "north-south", "south-north", "南北", "南北向",
        }:
            return "y"
        return "x"

    def _component_item(self, comp, key, ci, horizontal, orientation=None):
        """Build a layout item dict for a specialized component instance.

        When *horizontal* (laid-down rocket), the footprint is rotated so the
        component's vertical (height) axis lies along the source/door axis and
        the layout reserves the correct ground area.
        """
        axis = sign = None
        rotate_xy = False
        if horizontal:
            axis, sign = self._source_horizontal_dir()
            if axis == "x":
                fl, fw, fh = comp.total_height, comp.total_width, comp.total_length
            else:
                fl, fw, fh = comp.total_width, comp.total_height, comp.total_length
        else:
            axis = self._component_orientation_axis(orientation)
            if axis == "y":
                fl, fw, fh = comp.total_width, comp.total_length, comp.total_height
                rotate_xy = True
            else:
                fl, fw, fh = comp.total_length, comp.total_width, comp.total_height
        return {
            "length": fl,
            "width": fw,
            "height": fh,
            "key": key,
            "_type": "component",
            "_comp": comp,
            "_instance": ci,
            "_horizontal": horizontal,
            "_rotate_xy": rotate_xy,
            "_axis": axis,
            "_sign": sign,
        }

    def _generate_combustibles(self, building, story, si, lines, grid_size: float = 0.1, bi: int = 0):
        """Generate combustible and specialized component OBSTs per FC.

        Layout: a *single* ``layout_items_in_fc_cached`` call packs the FC
        with ``specialized_components + every requested combustible type``
        in one pass, mirroring :func:`viewer_3d._collect_combustible_boxes`.
        The earlier per-type layout inflated already-placed items back into
        the exclusion chain, which silently dropped later types on tight FCs
        and made FDS/smokeview show fewer OBSTs than the preview. By handing
        the whole mixed list to the layout algorithm up front we keep every
        user-specified unit.

        Specialized components land compact + centered; combustibles spread
        around their bounding box (internal ``spec_bounds_internal``;
        do not compute one manually). External exclusions = sibling FC
        overlap only.

        Probe placement:
        - Burnable combustibles: a thermocouple (WALL TEMPERATURE) on top.
        - Non-burnable combustibles / specialized components (inert metal):
          a RADIATIVE HEAT FLUX GAS gauge facing the source.

        IDs are ``{key}_B{bi}S{si}_{seq}`` (name-based, per-story unique);
        probe IDs prefix ``TC_`` / ``HF_`` onto that base so they never
        collide with the OBST they belong to.

        *grid_size* is the FDS cell size used by the current MESH. OBSTs
        whose smallest dimension is below this size are emitted with
        ``THICKEN=.TRUE.`` so FDS keeps them as at least one cell instead
        of snapping them away.
        """
        from models.geometry import layout_items_in_fc_cached

        ox, L, oy, W = building.boundary
        z0 = story.z_bottom

        # Per-story sequence so IDs never collide across fire compartments.
        tag = f"B{bi}S{si}"
        seq = 0

        for fc in story.fire_compartments:
            if not fc.combustibles and not fc.specialized_components:
                continue

            rocket_placement = _resolve_rocket_placement(fc, story, building)
            sibling_excl = _compute_sibling_overlaps(fc, story.fire_compartments)

            sc_items: list[dict] = []
            for sc_info in fc.specialized_components:
                key = sc_info.get("key", "")
                comp = SPECIALIZED_COMPONENTS.get(key)
                if not comp:
                    continue
                is_rocket = key.startswith("ROCKET_VEHICLE")
                if is_rocket and not rocket_placement["allow_rockets"]:
                    _warn_rocket_skipped(fc, key, sc_info.get("count", 1), rocket_placement["role"])
                    continue
                horizontal = is_rocket and rocket_placement["horizontal"]
                orientation = sc_info.get("orientation")
                if orientation is None and sc_info.get("rotation") == 90:
                    orientation = "y"
                for ci in range(sc_info.get("count", 1)):
                    sc_items.append(self._component_item(comp, key, ci, horizontal, orientation))

            # Repeated entries for the same key accumulate the count.
            per_key_total: dict[str, int] = {}
            for cb_entry in fc.combustibles:
                key = cb_entry.get("key", "")
                if not key or key not in COMBUSTIBLE_LIBRARY:
                    continue
                per_key_total[key] = per_key_total.get(key, 0) + int(cb_entry.get("count", 0))

            comb_items: list[dict] = []
            for key, total_count in per_key_total.items():
                if total_count <= 0:
                    continue
                cb_def = COMBUSTIBLE_LIBRARY[key]
                for _ in range(total_count):
                    comb_items.append({
                        "key": key,
                        "name": cb_def.get("name", key),
                        "length": cb_def.get("length", 1.0),
                        "width": cb_def.get("width", 0.8),
                        "height": cb_def.get("height", 0.5),
                        "_type": "combustible",
                        "burnable": bool(cb_def.get("burnable", False)),
                    })

            all_items = sc_items + comb_items
            if not all_items:
                continue

            placed = layout_items_in_fc_cached(
                fc.boundary, all_items,
                margin=0.5, gap=1.5,
                exclusions=(sibling_excl if sibling_excl else None),
            )
            if not placed:
                continue

            lines.append(f"! -- 可燃物与组件 ({fc.name}) --\n")
            for item in placed:
                base = f"{item['key']}_{tag}_{seq:03d}".replace(" ", "_")
                if item.get("_type") == "component":
                    self._emit_component(lines, item, ox, oy, z0, grid_size, base)
                else:
                    self._emit_combustible(lines, item, ox, oy, z0, grid_size, base)
                seq += 1

    # ------------------------------------------------------------------
    # Story-level combustibles (with explicit boundary)
    # ------------------------------------------------------------------
    def _generate_story_combustibles(self, building, story, si, lines, grid_size: float = 0.1, bi: int = 0):
        """Generate *non-FC* area combustibles on this story.

        Older versions used a single big boundary + per-entry ``count`` from
        user input.  That approach was fragile: irregular floor plans
        don't carve into axis-aligned rectangles, so a single boundary
        overlapped nested FCs.

        The new flow (''chunked fill'') carves the building's free area
        into axis-aligned rectangles via
        :func:`models.geometry.partition_free_areas`, then picks the
        best-fitting burnable item for each rectangle via
        :func:`models.geometry.auto_fill_rect`, and finally calls
        :func:`models.geometry.layout_items_in_fc` per rectangle.
        Each item spec in :data:`story.combustibles` is interpreted as a
        *type preference* (``key`` field) — ``count`` and ``boundary``
        are ignored and computed by the algorithm.
        """
        from models.geometry import (
            layout_items_in_fc_cached, partition_free_areas, auto_fill_rect_cached,
        )

        ox, _L, oy, _W = building.boundary
        z0 = story.z_bottom

        if not story.combustibles and not story.specialized_components:
            return

        lines.append(f"! -- Story-level 可燃物与组件 ({story.name}) --\n")
        tag = f"B{bi}STORY{si}"
        seq = 0

        def _emit_placed(placed_items):
            nonlocal seq
            for item in placed_items:
                base = f"{item['key']}_{tag}_{seq:03d}".replace(" ", "_")
                if item.get("_type") == "component":
                    self._emit_component(lines, item, ox, oy, z0, grid_size, base)
                else:
                    self._emit_combustible(lines, item, ox, oy, z0, grid_size, base)
                seq += 1

        # 1. Story-level specialized_components: keep legacy behaviour —
        #    explicit boundary + per-entry count, no auto-partitioning
        #    (specialized components are usually big/fixed, like rockets).
        for sc_info in story.specialized_components:
            boundary = sc_info.get("boundary")
            if not boundary:
                continue
            sc_key = sc_info.get("key", "")
            comp = SPECIALIZED_COMPONENTS.get(sc_key)
            if not comp:
                continue
            horizontal = sc_key.startswith("ROCKET_VEHICLE")
            orientation = sc_info.get("orientation")
            if orientation is None and sc_info.get("rotation") == 90:
                orientation = "y"
            items = [
                self._component_item(comp, sc_key, ci, horizontal, orientation)
                for ci in range(sc_info.get("count", 1))
            ]
            placed = layout_items_in_fc_cached(boundary, items, margin=0.5, gap=0.6)
            _emit_placed(placed)

        # 2. Story-level combustibles — each entry's ``boundary`` is treated
        #    like a virtual fire compartment.  The rectangle receives ``count``
        #    copies of the specified ``key``, uniformly distributed with the
        #    standard margin (0.5 m) and gap (1.0 m).  When multiple entries
        #    share or overlap the same rectangle, items placed by earlier
        #    entries are recorded as exclusions so later entries stay clear.
        placed_excl: list[tuple[float, float, float, float]] = []
        for cb_entry in story.combustibles:
            boundary_raw = cb_entry.get("boundary")
            if not boundary_raw:
                continue
            key = cb_entry.get("key", "")
            count = int(cb_entry.get("count", 0))
            if key not in COMBUSTIBLE_LIBRARY or count <= 0:
                continue
            cb_def = COMBUSTIBLE_LIBRARY[key]
            length = cb_def.get("length", 1.0)
            width = cb_def.get("width", 0.8)
            height = cb_def.get("height", 0.5)
            items: list[dict] = []
            for _ in range(count):
                items.append({
                    "length": length,
                    "width": width,
                    "height": height,
                    "key": key,
                    "name": cb_def.get("name", key),
                    "_type": "combustible",
                })
            placed = layout_items_in_fc_cached(
                tuple(boundary_raw), items, margin=0.5, gap=1.5,
                exclusions=(placed_excl if placed_excl else None),
            )
            if placed:
                _emit_placed(placed)
                # Record placed rectangles (inflated by 1.0 m) so
                # subsequent entries in the same story stay at full
                # gap distance from already-placed items.
                for p in placed:
                    placed_excl.append((
                        p["x"] - 1.0,
                        p["x"] + p["length"] + 1.0,
                        p["y"] - 1.0,
                        p["y"] + p["width"] + 1.0,
                    ))

        lines.append("\n")


    # ------------------------------------------------------------------
    # Heat source
    # ------------------------------------------------------------------
    def _generate_heat_source(self, lines, timer_x: float, timer_y: float, timer_z: float,
                              mesh_domain=None, mesh_plan=None):
        """Generate heat source with RAMP-controlled per-face radiation SURF/VENT.

        net_heat_flux stores the UI target q_avg (kW/m2).  It is converted to
        the calibrated FDS source q_set before writing NET_HEAT_FLUX on the
        radiation SURF.  Azimuth/elevation decompose q_set across the exposed
        domain faces.

        *mesh_domain*: if supplied, the actual mesh bounding box (may extend
        beyond the original domain due to uniform cell alignment).  Used for
        VENT XB coordinates when refinement is disabled.

        *mesh_plan*: a MeshPlan namedtuple.  When present, the function emits
        per-mesh outer boundary VENTs so OPEN/MIRROR/PERIODIC VENTs never
        fall outside a mesh's exterior boundary (avoids FDS ERROR 819 caused
        by the refinement strip carving the source-facing side).  When None
        the legacy single-domain emission is used.
        """
        from models.heat_source import face_fluxes
        from models.temp_flux_formula import compute_top_face_bounds
        from models.window_flux_calibration import fit_for_duration, q_avg_to_q_set

        hs = self.bg.heat_source
        azimuth = float(hs.get("azimuth", 0))
        elevation = float(hs.get("elevation", 0))
        q_avg_target = float(hs.get("net_heat_flux", 1000))
        duration = float(hs.get("duration", 1.36))
        facility = getattr(self.bg, "name", None)
        q_set = q_avg_to_q_set(
            q_avg_target,
            duration,
            facility=facility,
            azimuth=azimuth,
        )
        fit = fit_for_duration(duration, facility=facility, azimuth=azimuth)

        # Determine which domain faces are active.  FDS receives q_set; the UI
        # value remains the target q_avg.
        fluxes = face_fluxes(azimuth, elevation, q_set)
        if not fluxes:
            return

        if mesh_domain is None:
            plan = self._compute_mesh()
            domain = plan.domain
            grid_size = plan.grid_size
        else:
            domain = list(mesh_domain)
            grid_size = 1.0  # unused here
        x0, x1, y0, y1, z0, z1 = domain

        q_avg_label = int(round(q_avg_target))
        q_set_label = int(round(q_set))
        lines.append(
            f"! ========== 外部强辐射热源 (q_avg_target={q_avg_label} kW/m2, "
            f"q_set={q_set_label} kW/m2, fit_duration={fit.duration:g}s, "
            f"azimuth={azimuth}°, elevation={elevation}°)"
        )
        lines.append(f" ==========\n")

        ramp_id = "radiation_timer"
        ramp_suffix = f", RAMP_Q='{ramp_id}'" if duration > 0 else ""
        if duration > 0:
            ramp_cutoff = duration + 0.001
            lines.append("! 辐射控制 RAMP\n")
            lines.append(f"&RAMP ID='{ramp_id}', T=0.000, F=1.0 /\n")
            lines.append(f"&RAMP ID='{ramp_id}', T={duration:.3f}, F=1.0 /\n")
            lines.append(f"&RAMP ID='{ramp_id}', T={ramp_cutoff:.3f}, F=0.0 /\n\n")

        lines.append("! Per-face radiation surfaces\n")
        face_xb = {
            "XMIN": (x0, x0, y0, y1, z0, z1),
            "XMAX": (x1, x1, y0, y1, z0, z1),
            "YMIN": (x0, x1, y0, y0, z0, z1),
            "YMAX": (x0, x1, y1, y1, z0, z1),
            "ZMIN": (x0, x1, y0, y1, z0, z0),
            "ZMAX": (x0, x1, y0, y1, z1, z1),
        }

        top_flux = fluxes.get("ZMAX")
        rad_faces = {f for f in fluxes if f not in ("ZMIN", "ZMAX")}
        for face_name in sorted(rad_faces):
            surf_id = f"radiation_{face_name}"
            face_flux = fluxes[face_name]
            lines.append(
                f"&SURF ID='{surf_id}', NET_HEAT_FLUX={face_flux:.0f}, "
                f"COLOR='ORANGE'{ramp_suffix} /\n\n"
            )

        # Top-face SURF (only when elevation > 0)
        if top_flux is not None:
            lines.append(
                f"&SURF ID='radiation_ZMAX_TOP', NET_HEAT_FLUX={top_flux:.0f}, "
                f"COLOR='ORANGE'{ramp_suffix} /\n\n"
            )

        lines.append("! Heat source boundary VENTs\n")
        has_timer = False
        has_elevation = top_flux is not None

        # Pre-compute ZMAX split when elevation > 0
        zmax_top_rect = None
        zmax_open_rects = None
        if has_elevation:
            buildings = self.bg.buildings
            xb_min = min(b.offset_x - b.wall_thickness / 2 for b in buildings)
            xb_max = max(b.offset_x + b.length + b.wall_thickness / 2 for b in buildings)
            yb_min = min(b.offset_y - b.wall_thickness / 2 for b in buildings)
            yb_max = max(b.offset_y + b.width + b.wall_thickness / 2 for b in buildings)
            tx1, tx2, ty1, ty2, _, _ = compute_top_face_bounds(
                azimuth, tuple(domain), xb_min, xb_max, yb_min, yb_max,
            )
            from models.temp_flux_formula import compute_zmax_open_rects
            zmax_top_rect = (tx1, tx2, ty1, ty2, z1, z1)
            zmax_open_rects = compute_zmax_open_rects(
                tuple(domain), tx1, tx2, ty1, ty2,
            )

        if mesh_plan is not None and mesh_plan.refinement is not None:
            self._emit_heat_source_vents_per_mesh(
                lines, mesh_plan, flux_label_rad_faces=rad_faces,
                azimuth=azimuth,
                has_timer=has_timer, has_elevation=has_elevation,
                zmax_top_rect=zmax_top_rect,
                zmax_open_rects=zmax_open_rects,
            )
        else:
            self._emit_heat_source_vents_legacy(
                lines, domain, rad_faces=rad_faces,
                has_timer=has_timer, has_elevation=has_elevation,
                zmax_top_rect=zmax_top_rect,
                zmax_open_rects=zmax_open_rects,
            )
        lines.append("\n")

    def _emit_heat_source_vents_legacy(
        self, lines, domain, rad_faces, has_timer, has_elevation,
        zmax_top_rect, zmax_open_rects,
        source_azimuth=None,
    ):
        """Emit domain-wide VENTs when there is no refinement strip.

        Each VENT spans the entire matching domain face.  This is the original
        behaviour from before the refinement zone was added; for a single
        MESH or a uniform 4-MESH layout every face IS the exterior boundary
        of every mesh, so this satisfies the FDS VENT-on-exterior rule.

        *source_azimuth*: when supplied (legacy call from a context that
        knows the source direction), this is used to compute top-strip
        bounds.  When None, the function derives them from ``self.bg``.
        """
        x0, x1, y0, y1, z0, z1 = domain
        if source_azimuth is None:
            source_azimuth = float(self.bg.heat_source.get("azimuth", 0))
        face_xb = {
            "XMIN": (x0, x0, y0, y1, z0, z1),
            "XMAX": (x1, x1, y0, y1, z0, z1),
            "YMIN": (x0, x1, y0, y0, z0, z1),
            "YMAX": (x0, x1, y1, y1, z0, z1),
            "ZMIN": (x0, x1, y0, y1, z0, z0),
            "ZMAX": (x0, x1, y0, y1, z1, z1),
        }

        def _emit(surf_id, xb, extra="", label=""):
            comment = f"  ! {label}" if label else ""
            lines.append(
                f"&VENT ID='Domain Vent {label}', SURF_ID='{surf_id}'{extra}, "
                f"XB={xb[0]:.2f},{xb[1]:.2f},{xb[2]:.2f},{xb[3]:.2f},"
                f"{xb[4]:.2f},{xb[5]:.2f} /{comment}\n"
            )

        all_domain_faces = ("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX")
        for face_name in all_domain_faces:
            if face_name == "ZMAX" and has_elevation:
                continue
            if face_name in rad_faces:
                surf_id = f"radiation_{face_name}"
                extra = ", DEVC_ID='TIMER->OUT'" if has_timer else ""
            else:
                surf_id = "OPEN"
                extra = ""
            _emit(surf_id, face_xb[face_name], extra, f"[{face_name}]")

        if has_elevation:
            extra = ", DEVC_ID='TIMER->OUT'" if has_timer else ""
            _emit(
                "radiation_ZMAX_TOP",
                zmax_top_rect,
                extra, "[ZMAX_TOP]",
            )
            for i, rect in enumerate(zmax_open_rects or []):
                _emit("OPEN", rect, "", f"[ZMAX_OPEN_{i}]")

    def _emit_heat_source_vents_per_mesh(
        self, lines, mesh_plan, flux_label_rad_faces, azimuth,
        has_timer, has_elevation, zmax_top_rect, zmax_open_rects,
    ):
        """Emit one VENT per mesh's outer face so OPEN/MIRROR/PERIODIC
        VENTs never fall off a mesh's exterior boundary (FDS ERROR 819).

        Strategy:
          MeshRefined and the 4 coarse meshes share interior faces at the
          coarse/fine interface — those faces are silently omitted because
          FDS already exchanges data across them via MPI.
          For each remaining outer face of each mesh we emit:
            * SURF_ID='radiation_<face>' on every exterior face that carries
              decomposed heat-source flux.
            * SURF_ID='OPEN' on every other genuine exterior face.
        """
        from models.heat_source import rad_wall_for_azimuth

        rad_wall = rad_wall_for_azimuth(azimuth)
        source_face_map = {
            "x_min": "XMIN",
            "x_max": "XMAX",
            "y_min": "YMIN",
            "y_max": "YMAX",
        }
        source_face = source_face_map.get(rad_wall)

        # Build the list of mesh XBs as [x0,x1,y0,y1,z0,z1].
        ref = mesh_plan.refinement
        if ref is None:
            mesh_xbs = [mesh_plan.domain]
        else:
            mesh_xbs = [ref["xb"]] + self._coarse_mesh_xbs(mesh_plan)

        # Collect set of shared face keys (axis + value) so we can omit
        # them — those are mesh-to-mesh interfaces, not exterior boundaries.
        shared_x = set()
        shared_y = set()
        shared_z = {0: set(), 1: set()}  # z0 shared but z1 is always top
        # A value is "shared" on an axis if it appears as an interior face
        # of at least one mesh AND as the outer face of another mesh.
        all_x = []
        all_y = []
        all_z = []
        for m in mesh_xbs:
            all_x.extend([m[0], m[1]])
            all_y.extend([m[2], m[3]])
            all_z.extend([m[4], m[5]])
        # The FULL domain's outer faces are always at min/max of all values;
        # any value strictly between min and max is an interface and must
        # be shared.
        for axis_vals, shared_set in (
            (all_x, shared_x),
            (all_y, shared_y),
        ):
            lo, hi = min(axis_vals), max(axis_vals)
            for v in axis_vals:
                if lo < v < hi:
                    shared_set.add(v)
        for v in all_z:
            lo, hi = min(all_z), max(all_z)
            if lo < v < hi:
                shared_z[0].add(v)
            elif lo < v:
                shared_z[1].add(v)

        def _is_shared_face(axis: str, value: float) -> bool:
            if axis == "x":
                return value in shared_x
            if axis == "y":
                return value in shared_y
            if axis == "z":
                if value in shared_z[0]:
                    return True
                if value in shared_z[1]:
                    return True
            return False

        def _emit_for_mesh(mesh_xb, mesh_id):
            x0, x1, y0, y1, z0, z1 = mesh_xb

            for axis, lo_face, hi_face, lo_idx, hi_idx in (
                ("x", "XMIN", "XMAX", 0, 1),
                ("y", "YMIN", "YMAX", 2, 3),
                ("z", "ZMIN", "ZMAX", 4, 5),
            ):
                for face_name, val, idx_lo, idx_hi, coords_lo, coords_hi in (
                    (lo_face, mesh_xb[lo_idx], lo_idx, lo_idx + 1,
                     mesh_xb[0], mesh_xb[1]),
                ):
                    if axis == "y":
                        coords_lo, coords_hi = mesh_xb[0], mesh_xb[1]
                    if axis == "z":
                        coords_lo, coords_hi = (mesh_xb[0], mesh_xb[1])
                    if _is_shared_face(axis, val):
                        continue
                    _emit_face(
                        lines, mesh_id, face_name, axis, val, mesh_xb,
                        source_face, flux_label_rad_faces,
                        has_timer, has_elevation, zmax_open_rects,
                    )

                # hi face
                if axis == "x":
                    face_name, val, idx_lo, idx_hi = hi_face, mesh_xb[1], 0, 1
                elif axis == "y":
                    face_name, val, idx_lo, idx_hi = hi_face, mesh_xb[3], 2, 3
                else:
                    face_name, val, idx_lo, idx_hi = hi_face, mesh_xb[5], 4, 5
                if _is_shared_face(axis, val):
                    continue
                _emit_face(
                    lines, mesh_id, face_name, axis, val, mesh_xb,
                    source_face, flux_label_rad_faces,
                    has_timer, has_elevation, zmax_open_rects,
                )

        mesh_entries = []
        for mi, m in enumerate(mesh_xbs):
            mesh_id = "MeshRefined" if (ref is not None and mi == 0) else f"Mesh{mi:02d}"
            mesh_entries.append((mesh_id, m))

        shared_faces = self._shared_mesh_faces(mesh_xbs)

        # Simpler: iterate the 6 faces for each mesh directly
        for mi, (mesh_id, m) in enumerate(mesh_entries):
            self._emit_face_vents(
                lines, mesh_id, m, shared_x, shared_y, source_face,
                rad_faces=flux_label_rad_faces,
                has_timer=has_timer, has_elevation=has_elevation,
                zmax_open_rects=zmax_open_rects,
                zmax_top_rect=zmax_top_rect,
                first_mesh_for_global_faces=(mi == 0),
                mesh_index=mi,
                shared_faces=shared_faces,
            )

    @staticmethod
    def _shared_mesh_faces(mesh_xbs, tol=1e-9):
        """Return {(mesh_index, FACE)} for faces shared by adjacent meshes."""

        def _overlap(a0, a1, b0, b1):
            return min(a1, b1) - max(a0, b0) > tol

        shared = set()
        for i, a in enumerate(mesh_xbs):
            ax0, ax1, ay0, ay1, az0, az1 = a
            for j, b in enumerate(mesh_xbs[i + 1:], start=i + 1):
                bx0, bx1, by0, by1, bz0, bz1 = b
                yz_overlap = _overlap(ay0, ay1, by0, by1) and _overlap(az0, az1, bz0, bz1)
                xz_overlap = _overlap(ax0, ax1, bx0, bx1) and _overlap(az0, az1, bz0, bz1)
                xy_overlap = _overlap(ax0, ax1, bx0, bx1) and _overlap(ay0, ay1, by0, by1)

                if yz_overlap:
                    if abs(ax1 - bx0) <= tol:
                        shared.add((i, "XMAX"))
                        shared.add((j, "XMIN"))
                    if abs(ax0 - bx1) <= tol:
                        shared.add((i, "XMIN"))
                        shared.add((j, "XMAX"))

                if xz_overlap:
                    if abs(ay1 - by0) <= tol:
                        shared.add((i, "YMAX"))
                        shared.add((j, "YMIN"))
                    if abs(ay0 - by1) <= tol:
                        shared.add((i, "YMIN"))
                        shared.add((j, "YMAX"))

                if xy_overlap:
                    if abs(az1 - bz0) <= tol:
                        shared.add((i, "ZMAX"))
                        shared.add((j, "ZMIN"))
                    if abs(az0 - bz1) <= tol:
                        shared.add((i, "ZMIN"))
                        shared.add((j, "ZMAX"))

        return shared

    def _emit_face_vents(
        self, lines, mesh_id, mesh_xb, shared_x, shared_y, source_face,
        rad_faces, has_timer, has_elevation, zmax_open_rects, zmax_top_rect,
        first_mesh_for_global_faces, mesh_index=None, shared_faces=None,
    ):
        """Emit exterior VENTs for one mesh's 6 outer faces.

        Each mesh emits VENTs only on faces that are **its own exterior
        boundary** (i.e. not a mesh-mesh interior face).  This guarantees
        every VENT lies on a valid mesh boundary and avoids FDS ERROR 819
        "VENT null is OPEN, MIRROR OR PERIODIC and must be on an exterior
        boundary".  When a face is shared by another mesh the VENT is the
        responsibility of the other mesh; FDS exchanges data across the
        interior face automatically via MPI.

        *first_mesh_for_global_faces* is reserved for future use — current
        version emits per-face per-mesh naturally because the carve itself
        makes faces ambiguous only on the source side.
        """
        x0, x1, y0, y1, z0, z1 = mesh_xb
        shared_faces = shared_faces or set()

        def _is_shared(face_name):
            return mesh_index is not None and (mesh_index, face_name) in shared_faces

        # XMIN / XMAX - skip shared interior faces. Only true exterior
        # boundaries may receive OPEN/MIRROR/PERIODIC VENTs in FDS.
        if not _is_shared("XMIN"):
            self._emit_one_vent(
                lines, mesh_id, "XMIN", source_face, rad_faces,
                has_timer=has_timer, has_elevation=has_elevation,
                xb=(x0, x0, y0, y1, z0, z1),
            )

        if not _is_shared("XMAX"):
            self._emit_one_vent(
                lines, mesh_id, "XMAX", source_face, rad_faces,
                has_timer=has_timer, has_elevation=has_elevation,
                xb=(x1, x1, y0, y1, z0, z1),
            )

        # YMIN / YMAX — same rule; skip shared interior faces.
        if not _is_shared("YMIN"):
            self._emit_one_vent(
                lines, mesh_id, "YMIN", source_face, rad_faces,
                has_timer=has_timer, has_elevation=has_elevation,
                xb=(x0, x1, y0, y0, z0, z1),
            )
        if not _is_shared("YMAX"):
            self._emit_one_vent(
                lines, mesh_id, "YMAX", source_face, rad_faces,
                has_timer=has_timer, has_elevation=has_elevation,
                xb=(x0, x1, y1, y1, z0, z1),
            )

        # ZMIN / ZMAX are exterior horizontal faces for this side-by-side mesh
        # layout, so emit them per mesh rather than only on the first mesh.
        if not _is_shared("ZMIN"):
            self._emit_one_vent(
                lines, mesh_id, "ZMIN", source_face, rad_faces,
                has_timer=has_timer, has_elevation=has_elevation,
                xb=(x0, x1, y0, y1, z0, z0),
            )
        if not _is_shared("ZMAX"):
            if has_elevation:
                self._emit_zmax_split(
                    lines, mesh_id, x0, x1, y0, y1, z0, z1,
                    zmax_top_rect, zmax_open_rects, has_timer,
                )
            else:
                self._emit_one_vent(
                    lines, mesh_id, "ZMAX", source_face, rad_faces,
                    has_timer=has_timer, has_elevation=has_elevation,
                    xb=(x0, x1, y0, y1, z1, z1),
                )

    def _emit_one_vent(
        self, lines, mesh_id, face_name, source_face, rad_faces,
        has_timer, has_elevation, xb,
    ):
        if face_name in rad_faces:
            surf_id = f"radiation_{face_name}"
            extra = ", DEVC_ID='TIMER->OUT'" if has_timer else ""
        else:
            surf_id = "OPEN"
            extra = ""
        lines.append(
            f"&VENT ID='{mesh_id} Vent [{face_name}]', "
            f"SURF_ID='{surf_id}'{extra}, "
            f"XB={xb[0]:.2f},{xb[1]:.2f},{xb[2]:.2f},{xb[3]:.2f},"
            f"{xb[4]:.2f},{xb[5]:.2f} /\n"
        )

    def _emit_zmax_split(
        self, lines, mesh_id, x0, x1, y0, y1, z0, z1,
        zmax_top_rect, zmax_open_rects, has_timer,
    ):
        # Emit the radiation strip first, then the remaining OPEN rectangles.
        rects = []
        if zmax_top_rect is not None:
            rects.append(("ZMAX_TOP", "radiation_ZMAX_TOP", zmax_top_rect, True))
        for i, rect in enumerate(zmax_open_rects or []):
            rects.append((f"ZMAX_OPEN_{i}", "OPEN", rect, False))

        for label, surf_id, rect, timed in rects:
            ox1, ox2, oy1, oy2, oz1, oz2 = rect
            # Only emit if this mesh covers the rect's x/y span
            if ox2 <= x0 or ox1 >= x1:
                continue
            if oy2 <= y0 or oy1 >= y1:
                continue
            cx1 = max(ox1, x0)
            cx2 = min(ox2, x1)
            cy1 = max(oy1, y0)
            cy2 = min(oy2, y1)
            extra = ", DEVC_ID='TIMER->OUT'" if timed and has_timer else ""
            lines.append(
                f"&VENT ID='{mesh_id} Vent [{label}]', "
                f"SURF_ID='{surf_id}'{extra}, "
                f"XB={cx1:.2f},{cx2:.2f},{cy1:.2f},{cy2:.2f},"
                f"{oz1:.2f},{oz2:.2f} /\n"
            )

    def _coarse_mesh_xbs(self, mesh_plan):
        """Reproduce the (x, y) 2x2 split of the reduced coarse domain.

        Returns a list of 4 XB tuples matching the order in which
        ``generate()`` emits Mesh01..Mesh04.
        """
        import math as _math

        ref = mesh_plan.refinement
        cd = ref["coarse_domain"]
        gx = mesh_plan.grid_size
        x0, x1, y0, y1, z0, z1 = cd
        nx = max(1, _math.ceil((x1 - x0) / gx))
        ny = max(1, _math.ceil((y1 - y0) / gx))
        nx_per = self._split_cell_counts(nx, 2)
        ny_per = self._split_cell_counts(ny, 2)
        x_edges = []
        pos = x0
        for i in range(2):
            pos += nx_per[i] * gx
            x_edges.append(pos)
        y_edges = []
        pos = y0
        for j in range(2):
            pos += ny_per[j] * gx
            y_edges.append(pos)
        out = []
        for jy, (yy1, yy2) in enumerate(
            zip([y0] + y_edges[:-1], y_edges)
        ):
            for ix, (xx1, xx2) in enumerate(
                zip([x0] + x_edges[:-1], x_edges)
            ):
                out.append([xx1, xx2, yy1, yy2, z0, z1])
        return out

    # ------------------------------------------------------------------
    # MESH computation
    # ------------------------------------------------------------------
    @staticmethod
    def _building_outer_extents(buildings):
        """Return exterior wall / ceiling extents used for heat-source gaps."""
        x_min = min(b.offset_x - b.wall_thickness / 2 for b in buildings)
        x_max = max(b.offset_x + b.length + b.wall_thickness / 2 for b in buildings)
        y_min = min(b.offset_y - b.wall_thickness / 2 for b in buildings)
        y_max = max(b.offset_y + b.width + b.wall_thickness / 2 for b in buildings)
        z_max = max(sum(s.height for s in b.stories) for b in buildings)
        return x_min, x_max, y_min, y_max, z_max

    @staticmethod
    def _align_away_from_anchor(anchor, desired, grid_size, side):
        """Align a non-source domain side while preserving padding.

        ``side='low'`` returns a coordinate <= desired such that
        ``anchor - coord`` is an integer multiple of ``grid_size``.
        ``side='high'`` returns a coordinate >= desired such that
        ``coord - anchor`` is an integer multiple of ``grid_size``.
        """
        if grid_size <= 0:
            return desired
        if side == "low":
            steps = max(1, math.ceil((anchor - desired) / grid_size))
            return anchor - steps * grid_size
        steps = max(1, math.ceil((desired - anchor) / grid_size))
        return anchor + steps * grid_size

    def _compute_mesh(self):
        """Compute the MESH layout (refinement-aware).

        Returns:
            MeshPlan namedtuple with:
              domain, grid_size, num_meshes, refinement

            The source-side refinement strip is enabled by default.  When the
            config is valid, ``num_meshes == 5`` and
            ``refinement`` carries the refinement mesh's bounding box, IJK,
            directional wall, grid size and rounded depth.  Otherwise
            ``refinement is None`` and ``num_meshes`` follows the legacy
            rule of 4 meshes in a 2×2 layout (or whatever
            ``bg.domain["num_meshes"]`` pins).
        """
        bg = self.bg
        buildings = bg.buildings

        if not buildings:
            return MeshPlan([0, 10, 0, 10, 0, 10], 1.0, 1, None)

        x_min, x_max, y_min, y_max, z_max = self._building_outer_extents(buildings)

        base_grid_size = bg.domain.get("grid_size", 1.0)
        if base_grid_size <= 0:
            base_grid_size = 1.0

        user_num_meshes = bg.domain.get("num_meshes")
        max_meshes = 4
        max_total_cells = 1000000

        grid_size = base_grid_size

        from models.heat_source import rad_wall_for_azimuth
        rad_wall = rad_wall_for_azimuth(float(bg.heat_source.get("azimuth", 0)))

        def _make_domain(g):
            """Build a domain with exact 1 m source/ceiling gaps."""
            desired_x0 = x_min - HEAT_SOURCE_GAP
            desired_x1 = x_max + HEAT_SOURCE_GAP
            desired_y0 = y_min - HEAT_SOURCE_GAP
            desired_y1 = y_max + HEAT_SOURCE_GAP

            if rad_wall == "x_max":
                dx1 = x_max + HEAT_SOURCE_GAP
                dx0 = self._align_away_from_anchor(x_max, desired_x0, g, "low")
            elif rad_wall == "x_min":
                dx0 = x_min - HEAT_SOURCE_GAP
                dx1 = self._align_away_from_anchor(x_min, desired_x1, g, "high")
            else:
                dx0 = math.floor(desired_x0 / g) * g
                dx1 = math.ceil(desired_x1 / g) * g

            if rad_wall == "y_max":
                dy1 = y_max + HEAT_SOURCE_GAP
                dy0 = self._align_away_from_anchor(y_max, desired_y0, g, "low")
            elif rad_wall == "y_min":
                dy0 = y_min - HEAT_SOURCE_GAP
                dy1 = self._align_away_from_anchor(y_min, desired_y1, g, "high")
            else:
                dy0 = math.floor(desired_y0 / g) * g
                dy1 = math.ceil(desired_y1 / g) * g

            return [dx0, dx1, dy0, dy1, 0, z_max + HEAT_SOURCE_GAP]

        domain = _make_domain(grid_size)
        domain_w = domain[1] - domain[0]
        domain_d = domain[3] - domain[2]
        domain_h = domain[5] - domain[4]

        def _cells(dx: float, dy: float, dz: float) -> tuple:
            return (
                max(1, math.ceil(dx / grid_size)),
                max(1, math.ceil(dy / grid_size)),
                max(1, math.ceil(dz / grid_size)),
            )

        nx, ny, nz = _cells(domain_w, domain_d, domain_h)
        total_cells = nx * ny * nz

        if user_num_meshes is None:
            while total_cells > max_total_cells and grid_size < 5.0:
                grid_size *= 1.5
                domain = _make_domain(grid_size)
                domain_w = domain[1] - domain[0]
                domain_d = domain[3] - domain[2]
                domain_h = domain[5] - domain[4]
                nx, ny, nz = _cells(domain_w, domain_d, domain_h)
                total_cells = nx * ny * nz

            num_meshes = max_meshes
        else:
            num_meshes = int(user_num_meshes)
            valid = {1, 2, 4, 6}
            if num_meshes not in valid:
                num_meshes = min(max(num_meshes, 1), max(num_meshes, max_meshes))
                if num_meshes not in valid:
                    num_meshes = max_meshes

        if grid_size > HEAT_SOURCE_MAX_GRID:
            integer_grid = round(grid_size / HEAT_SOURCE_MAX_GRID)
            if abs(integer_grid * HEAT_SOURCE_MAX_GRID - grid_size) > 1e-6:
                grid_size = math.ceil(grid_size / HEAT_SOURCE_MAX_GRID) * HEAT_SOURCE_MAX_GRID

        # Rebuild after the final coarse grid is known.  Do not align the
        # source-facing side or ZMAX away from the exact 1 m offsets.
        domain = _make_domain(grid_size)
        domain_w = domain[1] - domain[0]
        domain_d = domain[3] - domain[2]
        domain_h = domain[5] - domain[4]

        nx = max(1, math.ceil(domain_w / grid_size))
        ny = max(1, math.ceil(domain_d / grid_size))
        nz = max(1, math.ceil(domain_h / grid_size))

        # Refinement zone (mandatory by default; 5th mesh on the radiation side).
        refinement = self._build_refinement(domain, grid_size)
        total_meshes = 5 if refinement is not None else num_meshes
        return MeshPlan(domain, grid_size, total_meshes, refinement)

    # ------------------------------------------------------------------
    # Refinement zone
    # ------------------------------------------------------------------
    def _build_refinement(self, domain, grid_size):
        """Build the 5th refinement mesh info, or return None.

        The heat-source gap is physically fixed at 1 m.  When the coarse grid
        is larger than that, this method carves out a source-side refined mesh
        that contains the 1 m gap so the wall/source/probe relationship remains
        visible to FDS after meshing.  The mesh itself may be deeper than 1 m
        to avoid FDS Poisson failures from 1-2-cell-thick MPI meshes.
        """
        bg = self.bg
        rz = bg.domain.get("refinement_zone") if hasattr(bg, "domain") else None
        user_enabled = not isinstance(rz, dict) or bool(rz.get("enabled", True))
        if grid_size <= HEAT_SOURCE_MAX_GRID and not user_enabled:
            return None

        from models.heat_source import rad_wall_for_azimuth

        depth = HEAT_SOURCE_GAP
        requested_grid = (
            float(rz.get("grid_size", HEAT_SOURCE_MAX_GRID))
            if isinstance(rz, dict)
            else HEAT_SOURCE_MAX_GRID
        )
        refinement_grid_size = min(grid_size, requested_grid, HEAT_SOURCE_MAX_GRID)
        azimuth = float(bg.heat_source.get("azimuth", 0))
        rad_wall = rad_wall_for_azimuth(azimuth)

        if refinement_grid_size <= 0 or refinement_grid_size > grid_size:
            self._warn_once(
                f"WARNING: refinement_zone.grid_size={refinement_grid_size} "
                f"must be in (0, {grid_size}]; disabling refinement zone.",
                key=("refinement_gridsize_range", refinement_grid_size, grid_size),
            )
            return None

        # Integer ratio requirement: grid_size must be a multiple of the
        # source-strip grid so cell faces align at the interface.
        ratio = grid_size / refinement_grid_size
        if abs(ratio - round(ratio)) > 1e-6:
            self._warn_once(
                f"WARNING: refinement_zone.grid_size={refinement_grid_size} "
                f"does not divide grid_size={grid_size} evenly; disabling "
                "refinement zone to avoid FDS ERROR 873.",
                key=("refinement_gridsize_ratio", refinement_grid_size, grid_size),
            )
            return None

        source_gap_ratio = HEAT_SOURCE_GAP / refinement_grid_size
        if abs(source_gap_ratio - round(source_gap_ratio)) > 1e-6:
            self._warn_once(
                f"WARNING: refinement_zone.grid_size={refinement_grid_size} "
                f"does not resolve the required {HEAT_SOURCE_GAP:.1f} m heat-source gap; "
                "disabling refinement zone.",
                key=("refinement_source_gap_ratio", refinement_grid_size),
            )
            return None

        if depth <= 0:
            self._warn_once("WARNING: refinement_zone.depth must be > 0; disabling.")
            return None

        x0, x1, y0, y1, z0, z1 = domain

        min_mesh_depth = max(
            HEAT_SOURCE_GAP,
            MIN_REFINED_MESH_CELLS * refinement_grid_size,
        )
        # The source boundary is fixed at wall +/- 1 m.  To keep the coarse
        # interface on a coarse-grid face, refined depth must be
        # HEAT_SOURCE_GAP + N * grid_size.
        coarse_steps = max(0, math.ceil((min_mesh_depth - HEAT_SOURCE_GAP) / grid_size))
        mesh_depth = HEAT_SOURCE_GAP + coarse_steps * grid_size

        # Pick the strip orientation based on the source-facing wall.
        if rad_wall == "x_max":
            strip_x0, strip_x1 = x1 - mesh_depth, x1
            strip_y0, strip_y1 = y0, y1
        elif rad_wall == "x_min":
            strip_x0, strip_x1 = x0, x0 + mesh_depth
            strip_y0, strip_y1 = y0, y1
        elif rad_wall == "y_max":
            strip_x0, strip_x1 = x0, x1
            strip_y0, strip_y1 = y1 - mesh_depth, y1
        else:  # "y_min"
            strip_x0, strip_x1 = x0, x1
            strip_y0, strip_y1 = y0, y0 + mesh_depth

        strip_extent_x = strip_x1 - strip_x0
        strip_extent_y = strip_y1 - strip_y0

        # Number of cells inside the strip depends on its orientation:
        # for x_min/x_max the strip depth runs along x; for y_min/y_max
        # it runs along y.  The "perp" axis is the full domain extent.
        if rad_wall in ("x_min", "x_max"):
            along_extent = strip_extent_x
            perp_extent = strip_extent_y
        else:
            along_extent = strip_extent_y
            perp_extent = strip_extent_x
        cells_along_strip = max(1, int(round(along_extent / refinement_grid_size)))
        cells_perp = max(1, int(round(perp_extent / refinement_grid_size)))
        cells_z = max(1, int(round((z1 - z0) / refinement_grid_size)))

        actual_depth = along_extent

        # Recompute coarse domain: the original domain MINUS the strip.
        if rad_wall == "x_max":
            coarse_domain = [x0, strip_x0, y0, y1, z0, z1]
        elif rad_wall == "x_min":
            coarse_domain = [strip_x1, x1, y0, y1, z0, z1]
        elif rad_wall == "y_max":
            coarse_domain = [x0, x1, y0, strip_y0, z0, z1]
        else:  # "y_min"
            coarse_domain = [x0, x1, strip_y1, y1, z0, z1]

        return {
            "rad_wall": rad_wall,
            "grid_size": refinement_grid_size,
            "depth": actual_depth,
            "source_gap": HEAT_SOURCE_GAP,
            "xb": [strip_x0, strip_x1, strip_y0, strip_y1, z0, z1],
            # FDS IJK order is always (nx, ny, nz); map cell counts accordingly.
            "ijk": (
                cells_perp if rad_wall in ("y_min", "y_max") else cells_along_strip,
                cells_along_strip if rad_wall in ("y_min", "y_max") else cells_perp,
                cells_z,
            ),
            "coarse_domain": coarse_domain,
        }


    # ------------------------------------------------------------------
    # MESH layout
    # ------------------------------------------------------------------
    @staticmethod
    def _mesh_layout(num_meshes: int, nx: int, ny: int) -> tuple[int, int]:
        """Return ``(nx_seg, ny_seg)`` for a layout sized to ``num_meshes``.

        Picking rules
        -------------
        * ``1``  → ``(1, 1)``
        * ``2``  → ``(1, 2)`` along short axis (perpendicular to the long
                     side keeps the long slabs coherent, mirrors the old
                     behaviour and helps when boundaries on the long axis
                     are open).
        * ``4``  → ``(2, 2)`` square.
        * ``6``  → long axis × 3, short axis × 2 — produces the most
                     square-ish sub-meshes regardless of whether the domain
                     is wider in X or Y.

        Long/short is decided by cell counts (``nx`` vs ``ny``) so the
        layout follows geometry rather than hard-coding X = long axis.
        """
        if num_meshes == 1:
            return 1, 1
        if num_meshes == 2:
            return 1, 2
        if num_meshes == 4:
            return 2, 2
        # 6: long × 3, short × 2
        if nx >= ny:
            return 3, 2
        return 2, 3

    @staticmethod
    def _split_cell_counts(total_cells: int, segments: int) -> list[int]:
        """Split cells into integer chunks that sum exactly to total_cells."""
        segments = max(1, int(segments))
        total_cells = max(segments, int(total_cells))
        base = total_cells // segments
        remainder = total_cells % segments
        return [base + (1 if i < remainder else 0) for i in range(segments)]

    # ------------------------------------------------------------------
    # Main generate
    # ------------------------------------------------------------------
    def generate(self) -> str:
        """Generate the complete FDS input file as a string."""
        bg = self.bg
        buildings = bg.buildings

        # Ensure z_offsets are computed
        for b in buildings:
            b.update_z_offsets()

        # Determine CHID with工况信息
        chid = bg.name or "building"
        chid = chid.replace(" ", "_").replace(".", "_").replace("-", "_")
        chid = "".join(c for c in chid if ord(c) < 128) or "building"

        hs = bg.heat_source
        from models.window_flux_calibration import fit_for_duration, q_avg_to_q_set

        q_avg_kw = float(hs.get("net_heat_flux", 1000))
        duration_s = float(hs.get("duration", 0))
        azimuth = int(hs.get("azimuth", 0))
        facility = getattr(bg, "name", None)
        q_set_kw = q_avg_to_q_set(
            q_avg_kw,
            duration_s,
            facility=facility,
            azimuth=azimuth,
        )
        fit = fit_for_duration(duration_s, facility=facility, azimuth=azimuth)
        q_avg_label = int(round(q_avg_kw))
        q_set_label = int(round(q_set_kw))
        elevation = int(hs.get("elevation", 0))
        duration = int(duration_s * 1000)
        sim_time = int(bg.simulation_time)

        chid_suffix = f"q{q_avg_label}_a{azimuth}_e{elevation}_d{duration}_t{sim_time}"
        full_chid = f"{chid}_{chid_suffix}"

        title = (
            f"q_avg_target={q_avg_label} kW/m2, q_set={q_set_label} kW/m2, "
            f"fit_duration={fit.duration:g}s, Azimuth={azimuth}, Elevation={elevation}, "
            f"Duration={duration_s:g}s, SimTime={sim_time}s"
        )

        lines = []

        # HEAD
        lines.append(
            f"&HEAD CHID='{full_chid}', TITLE='{title}' /\n\n"
        )

        # REAC
        lines.append("! ========== 燃烧反应 ==========\n")
        lines.append("&REAC ID='METHANE', FUEL='METHANE', FORMULA='C1H4' /\n\n")

        # MESH
        plan = self._compute_mesh()
        domain = plan.domain
        refinement = plan.refinement
        grid_size = plan.grid_size
        self._num_meshes = plan.num_meshes
        self._grid_size = grid_size
        # Effective HOLE penetration — dynamic to outlast THICKEN-ed OBSTs
        # even when grid_size has been auto-grown (×1.5 loop).  The constant
        # HOLE_PENETRATION (1.0) is the floor; the actual grid cell size
        # may be larger and is the dominant term.
        self._hole_penetration = max(HOLE_PENETRATION, grid_size)

        if refinement is not None:
            coarse_domain = refinement["coarse_domain"]
            coarse_grid_size = grid_size
        else:
            coarse_domain = list(domain)
            coarse_grid_size = grid_size

        hover_domain_w = coarse_domain[1] - coarse_domain[0]
        hover_domain_d = coarse_domain[3] - coarse_domain[2]
        hover_domain_h = coarse_domain[5] - coarse_domain[4]
        nx = max(1, math.ceil(hover_domain_w / coarse_grid_size))
        ny = max(1, math.ceil(hover_domain_d / coarse_grid_size))
        nz = max(1, math.ceil(hover_domain_h / coarse_grid_size))
        if refinement is not None:
            ref_grid = refinement["grid_size"]
            max_ratio = max(1, int(math.floor(coarse_grid_size / ref_grid + 1e-9)))
            for ratio in range(max_ratio, 0, -1):
                dz = ratio * ref_grid
                cells = hover_domain_h / dz
                if abs(cells - round(cells)) < 1e-6:
                    nz = max(1, int(round(cells)))
                    break

        coarse_num_meshes = 4 if refinement is not None else plan.num_meshes

        lines.append("! ========== 计算域 ==========\n")
        timer_x = (coarse_domain[0] + coarse_domain[1]) / 2
        timer_z = max(1.0, coarse_domain[4] + 1.0)

        if refinement is not None:
            rx0, rx1, ry0, ry1, rz0, rz1 = refinement["xb"]
            rnix, rniy, rniz = refinement["ijk"]
            lines.append(
                f"! 细化网格带 (热源侧 {refinement['rad_wall']} 方向, "
                f"mesh深度 {refinement['depth']:.2f}m, "
                f"热源间距 {refinement.get('source_gap', HEAT_SOURCE_GAP):.2f}m, "
                f"grid={refinement['grid_size']:.2f}m)\n"
            )
            lines.append(
                f"&MESH ID='MeshRefined', "
                f"IJK={rnix},{rniy},{rniz}, "
                f"XB={rx0:.2f},{rx1:.2f},"
                f"{ry0:.2f},{ry1:.2f},"
                f"{rz0:.2f},{rz1:.2f}, MPI_PROCESS=0 /\n\n"
            )
            lines.append("! 粗网格区域 (4-meshes, 2x2 布局)\n")

        nx_seg, ny_seg = self._mesh_layout(coarse_num_meshes, nx, ny)
        if coarse_num_meshes == 1 and refinement is None:
            lines.append("! 单网格 (1MESH)\n")
            timer_y = (coarse_domain[2] + coarse_domain[3]) / 2
            lines.append(
                f"&MESH IJK={nx},{ny},{nz}, "
                f"XB={coarse_domain[0]:.2f},{coarse_domain[1]:.2f},"
                f"{coarse_domain[2]:.2f},{coarse_domain[3]:.2f},"
                f"{coarse_domain[4]:.2f},{coarse_domain[5]:.2f} /\n\n"
            )
            x_edges = [coarse_domain[1]]
            y_edges = [coarse_domain[3]]
        else:
            layout_desc = (
                f"分 {coarse_num_meshes} 个网格 ({nx_seg}×{ny_seg}) "
                "长轴切 3 段、短轴切 2 段"
                if coarse_num_meshes == 6
                else (
                    f"分 2 个网格 (Y 方向, 1×{ny_seg})"
                    if coarse_num_meshes == 2
                    else f"分 {coarse_num_meshes} 个网格 ({nx_seg}×{ny_seg} 双向分割)"
                )
            )
            lines.append(f"! {layout_desc} 以充分利用多核 MPI\n")

            # Split by integer cell counts, not by geometric midpoints.  This
            # keeps every sub-mesh at exactly coarse_grid_size while avoiding
            # extension into a neighbouring refinement strip.
            nx_per = self._split_cell_counts(nx, nx_seg)
            ny_per = self._split_cell_counts(ny, ny_seg)

            # Re-derive the XB coordinates from uniform cell counts so that
            # every mesh boundary falls on an exact cell edge.
            x_edges = []
            x_pos = coarse_domain[0]
            for i in range(nx_seg):
                x_pos += nx_per[i] * coarse_grid_size
                x_edges.append(x_pos)
            y_edges = []
            y_pos = coarse_domain[2]
            for j in range(ny_seg):
                y_pos += ny_per[j] * coarse_grid_size
                y_edges.append(y_pos)

            x_segments = list(zip([coarse_domain[0]] + x_edges[:-1], x_edges))
            y_segments = list(zip([coarse_domain[2]] + y_edges[:-1], y_edges))

            timer_x = (coarse_domain[0] + x_edges[0]) / 2
            timer_y = (coarse_domain[2] + y_edges[0]) / 2
            mesh_idx = 0
            for jy, (y1, y2) in enumerate(y_segments):
                for ix, (x1, x2) in enumerate(x_segments):
                    mesh_idx += 1
                    lines.append(
                        f"&MESH ID='Mesh{mesh_idx:02d}', "
                        f"IJK={nx_per[ix]},{ny_per[jy]},{nz}, "
                        f"XB={x1:.2f},{x2:.2f},"
                        f"{y1:.2f},{y2:.2f},"
                        f"{coarse_domain[4]:.2f},{coarse_domain[5]:.2f}"
                        f"{', MPI_PROCESS=' + str(min(mesh_idx - 1, DEFAULT_MPI_PROCESSES - 1)) if refinement is not None else ''} /\n"
                    )
            lines.append("\n")

        # TIME
        lines.append(f"&TIME T_END={bg.simulation_time:.1f} /\n\n")

        # DUMP
        lines.append(f"&DUMP DT_RESTART=300.0, DT_DEVC={DEFAULT_DEVC_DT:.2f} /\n\n")
        lines.append("&CLIP MINIMUM_TEMPERATURE=20, MAXIMUM_TEMPERATURE=10000 /\n\n")

        # Heat source (SURF + VENT) - 前置方便手动调整
        if refinement is None and plan.num_meshes == 1:
            mesh_domain = list(domain)
            mesh_domain_timer_y = (domain[2] + domain[3]) / 2
        else:
            mesh_domain = list(domain)
            timer_x = (coarse_domain[0] + coarse_domain[1]) / 2
            timer_y = (coarse_domain[2] + coarse_domain[3]) / 2
        # Always pass the MeshPlan so VENT emission can decide whether to
        # use per-mesh boundary splitting (refinement active) or the
        # legacy domain-wide emission (single MESH).
        self._generate_heat_source(
            lines, timer_x, timer_y, timer_z,
            mesh_domain=mesh_domain, mesh_plan=plan,
        )

        # Keep the wall heat-flux probe next to the heat source so it becomes
        # the first device column after Time in *_devc.csv.
        self._generate_window_flux_probe(lines)

        # Output: measurement devices - 前置方便手动调整
        self._generate_devices(lines)

        # Materials & Surfaces
        self._generate_materials(lines)

        # For each building: geometry
        for bi, b in enumerate(buildings):
            bld_label = (
                f"建筑{bi + 1}: {b.name or b.cn_name}" if len(buildings) > 1 else ""
            )
            if bld_label:
                lines.append(
                    f"\n! ########## {bld_label} (offset={b.offset_x:.1f},{b.offset_y:.1f}) ##########\n"
                )

            # Ground floor slab
            ox, L, oy, W = b.boundary
            t = b.wall_thickness
            lines.append("! ========== 地板 ==========\n")
            lines.append(
                self.gen_box(
                    ox - t / 2,
                    ox + L + t / 2,
                    oy - t / 2,
                    oy + W + t / 2,
                    0,
                    t,
                    "FLOOR",
                )
            )
            lines.append("\n")

            for si, story in enumerate(b.stories):
                z0 = story.z_bottom
                lines.append(
                    f"\n! ========== {story.name} (z={z0:.2f}~{story.z_top:.2f}) ==========\n"
                )

                # Exterior walls + openings
                lines.append("! -- 外墙 --\n")
                self._generate_exterior_walls(b, story, si, lines)

                # Fire compartment walls
                if story.fire_compartments:
                    lines.append("! -- 防火墙 --\n")
                    self._generate_firewalls(b, story, lines)

                # Combustibles (FC-level + story-level)
                self._generate_combustibles(b, story, si, lines, grid_size=grid_size, bi=bi)
                self._generate_story_combustibles(b, story, si, lines, grid_size=grid_size, bi=bi)

            # Roof: use the last story's roof
            if b.stories:
                last_story = b.stories[-1]
                lines.append("\n! ========== 屋顶 ==========\n")
                self._generate_roof(b, last_story, lines)
            lines.append("\n")

        # Per-story 2D slices (TEMPERATURE + HRRPUV at 2m above each floor)
        # are emitted AFTER the geometry so they can hit the MESH partition
        # boundaries cleanly.
        self._generate_per_story_slices(lines)

        # TAIL
        lines.append("&TAIL /\n")

        return "".join(lines)

    # ------------------------------------------------------------------
    # Window heat flux probe (nearest wall to radiation source)
    # ------------------------------------------------------------------
    def _generate_per_story_slices(self, lines):
        """Emit one TEMPERATURE + one HRRPUV SLCF per story, at z = z_bottom + 2 m.

        Each slice spans the entire facility MESH domain so the user can
        visualize horizontal heat-flow patterns across all buildings on a
        single plane.  Slice PBZ uses story-local elevations, FGIs are
        story-tagged so Smokeview labels stay human-readable.

        Skipped stories
        ---------------
        * Domain cells where 2 m above floor would fall outside the story
          (i.e.  z_bottom + 2 m >= z_top - 0.2 m) — the slice would land in
          the slab/roof and is meaningless for fire spread.
        * Same ``(PBZ, quantity)`` already emitted by an earlier story in the
          facility (dedup).  Only the first occurrence wins; later stories
          with identical elevation/orientation are skipped so the FDS output
          does not pile redundant SLCFs on a single plane.  This commonly
          happens when two buildings share their 1F / 2F elevations.
        * No buildings (handled by outer guard).
        """
        if not self.bg.buildings:
            return
        if not self.bg.output.get("slices", True):
            return

        domain, grid_size, _, _ = self._compute_mesh()
        x0, x1, y0, y1, _z0, _z1 = domain

        slice_height_above_floor = 2.0
        slice_min_clearance_under_roof = 0.2

        emitted_t: set[float] = set()
        emitted_hf: set[float] = set()
        emitted = 0
        lines.append("! ========== 每层切片 (TEMPERATURE + HRRPUV @ z_story+2m) ==========\n")
        for bi, b in enumerate(self.bg.buildings):
            ox, L, oy, W = b.boundary
            for si, s in enumerate(b.stories):
                plane_z = s.z_bottom + slice_height_above_floor
                if plane_z >= s.z_top - slice_min_clearance_under_roof:
                    print(
                        f"WARNING: skipping story slice for {b.cn_name}/{s.name}: "
                        f"z={plane_z:.2f}m is too close to roof z={s.z_top:.2f}m"
                    )
                    continue
                pz_key = round(plane_z, 2)

                fyi_t = f"T_b{bi}s{si}_{b.cn_name or b.name or ''}_{s.name}".replace(" ", "_")[:60]
                fyi_h = f"HF_b{bi}s{si}_{b.cn_name or b.name or ''}_{s.name}".replace(" ", "_")[:60]

                emitted_this = 0
                if pz_key not in emitted_t:
                    lines.append(
                        f"&SLCF PBZ={plane_z:.2f}, QUANTITY='TEMPERATURE', "
                        f"FYI='{fyi_t}' /\n"
                    )
                    emitted_t.add(pz_key)
                    emitted_this += 1
                if pz_key not in emitted_hf:
                    lines.append(
                        f"&SLCF PBZ={plane_z:.2f}, QUANTITY='HRRPUV', "
                        f"FYI='{fyi_h}' /\n"
                    )
                    emitted_hf.add(pz_key)
                    emitted_this += 1
                if emitted_this == 0:
                    # Already emitted earlier in the facility (same PBZ, same
                    # quantity).  Silently skip — the dedup pass is the
                    # expected behaviour when multiple buildings share a
                    # floor elevation (e.g. Buffalo主厂房 vs 西侧仓库 1F).
                    pass
                emitted += emitted_this
        if emitted == 0:
            lines.append("! (no per-story slices — all stories too short)\n")
        lines.append("\n")

    def _generate_window_flux_probe(self, lines):
        """Place the incident heat-flux probe just off the source-facing wall.

        Compass convention: az=0°  -> XMAX,  90° -> YMIN,  180° -> XMIN, 270° -> YMAX.
        """
        from models.heat_source import rad_wall_for_azimuth

        hs = self.bg.heat_source
        azimuth = hs.get("azimuth", 0)
        if not self.bg.buildings:
            return

        rad_wall = rad_wall_for_azimuth(azimuth)
        plan = self._compute_mesh()
        domain = plan.domain
        x0, x1, y0, y1, z0, z1 = domain
        wall_orientation = {
            "x_max": (1.0, 0.0, 0.0),
            "x_min": (-1.0, 0.0, 0.0),
            "y_min": (0.0, -1.0, 0.0),
            "y_max": (0.0, 1.0, 0.0),
        }
        sx, sy, sz = wall_orientation[rad_wall]

        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        cz = (z0 + z1) / 2
        eps = HEAT_FLUX_PROBE_WALL_OFFSET
        if rad_wall == "x_max":
            px, py, pz = x1 - HEAT_SOURCE_GAP + eps, cy, cz
        elif rad_wall == "x_min":
            px, py, pz = x0 + HEAT_SOURCE_GAP - eps, cy, cz
        elif rad_wall == "y_max":
            px, py, pz = cx, y1 - HEAT_SOURCE_GAP + eps, cz
        else:  # y_min
            px, py, pz = cx, y0 + HEAT_SOURCE_GAP - eps, cz

        lines.append("! ========== 入射热通量探针 (radiative gas heat flux near wall nearest to source) ==========\n")
        lines.append(
            f"&DEVC XYZ={px:.3f},{py:.3f},{pz:.3f},\n"
            f"      QUANTITY='RADIATIVE HEAT FLUX GAS',\n"
            f"      ORIENTATION={sx:.3f},{sy:.3f},{sz:.3f},\n"
            f"      ID='incident_heat_flux' /  ! source-aligned probe (azimuth={azimuth}°, wall={rad_wall})\n\n"
        )

    # ------------------------------------------------------------------
    # Measurement devices (extracted for prepending)
    # ------------------------------------------------------------------
    def _generate_devices(self, lines):
        """Generate facility-wide measurement devices (DEVC).

        The legacy ``center_temp`` and ``radiation_loss`` aggregates were
        removed because the only facility-scoped summary that matters for
        users is the per-story 2D slice already emitted by
        ``_generate_per_story_slices``.  Per-fuel DEVC probes are still
        emitted inline at the combustible / component placements.

        ``bg.output['devices']`` is kept as a no-op knob so the UI toggle
        does not error — any future aggregate device can land here.
        """
        if not self.bg.output.get("devices", True):
            return
        lines.append("! ========== 测量点 ==========\n")
        lines.append("! (facility-aggregate devices removed; per-story SLCFs cover the gap)\n\n")


# ============================================================
# FDS Validation
# ============================================================
def validate_fds(fds_text: str) -> list:
    """Validate FDS text and return list of warning/error strings."""
    warnings = []
    # Check for required namelists
    required = ["HEAD", "MESH", "TIME", "REAC", "TAIL"]
    for nml in required:
        if f"&{nml}" not in fds_text:
            warnings.append(f"缺少必需的 &{nml} 名称列表")
    # Check T_END > 0
    t_end_match = re.search(r"T_END\s*=\s*([\d.]+)", fds_text)
    if t_end_match:
        if float(t_end_match.group(1)) <= 0:
            warnings.append("T_END 应大于 0")
    # Check XB coordinate ordering (x1 < x2, y1 < y2, z1 < z2)
    xb_pattern = re.compile(
        r"XB\s*=\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)"
    )
    for match in xb_pattern.finditer(fds_text):
        coords = [float(match.group(i)) for i in range(1, 7)]
        if coords[0] > coords[1]:
            warnings.append(f"XB坐标错误: X1({coords[0]:.2f}) > X2({coords[1]:.2f})")
        if coords[2] > coords[3]:
            warnings.append(f"XB坐标错误: Y1({coords[2]:.2f}) > Y2({coords[3]:.2f})")
        if coords[4] > coords[5]:
            warnings.append(f"XB坐标错误: Z1({coords[4]:.2f}) > Z2({coords[5]:.2f})")

    # Check SURF_ID references exist
    surf_defs = set(re.findall(r"&SURF\s+ID='([^']+)'", fds_text))
    surf_refs = set(re.findall(r"SURF_ID='([^']+)'", fds_text))
    # Also collect from SURF_IDS
    for m in re.finditer(
        r"SURF_IDS='([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'", fds_text
    ):
        for g in m.groups():
            surf_refs.add(g)
    # Remove built-in surfaces
    builtin_surfs = {"INERT", "OPEN", "MIRROR", "PERIODIC"}
    missing_surfs = surf_refs - surf_defs - builtin_surfs
    for s in missing_surfs:
        warnings.append(f"引用了未定义的 SURF_ID: '{s}'")

    # Check MATL_ID references
    matl_defs = set(re.findall(r"&MATL\s+ID='([^']+)'", fds_text))
    matl_refs = set(re.findall(r"MATL_ID='([^']+)'", fds_text))
    missing_matls = matl_refs - matl_defs
    for m in missing_matls:
        warnings.append(f"引用了未定义的 MATL_ID: '{m}'")

    # Check duplicate IDs (skip RAMP entries which share IDs by design)
    id_pattern = re.compile(r"&(?!RAMP)\w+[^/]*\bID='([^']+)'")
    all_ids = id_pattern.findall(fds_text)
    seen = set()
    for id_val in all_ids:
        if id_val in seen:
            warnings.append(f"重复的 ID: '{id_val}'")
        seen.add(id_val)
    # Check namelist closure (every & has matching /)
    open_count = fds_text.count("&")
    close_count = fds_text.count(" /")
    if open_count > close_count + 2:  # allow some tolerance
        warnings.append(
            f"可能存在未闭合的名称列表 (& 数量: {open_count}, / 数量约: {close_count})"
        )
    return warnings
