#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for models.geometry (shared geometry utility functions)."""

import pytest
from models.building import Opening, FireCompartment, Story, Building
from models.geometry import (
    wall_length_for_fc,
    wall_length_for_building,
    is_coplanar,
    fc_wall_start_offset,
    detect_coplanar_openings,
    resolve_negative_offset,
    opening_to_world_coords,
    validate_opening_bounds,
    validate_building,
)


# ============================================================
# wall_length_for_fc
# ============================================================
class TestWallLengthForFC:
    """fc_boundary = [x_min, x_max, y_min, y_max].
    x walls (x_min, x_max) -> y_max - y_min.
    y walls (y_min, y_max) -> x_max - x_min.
    """

    def test_x_min_wall(self):
        assert wall_length_for_fc([0, 10, 0, 5], "x_min") == 5.0

    def test_x_max_wall(self):
        assert wall_length_for_fc([0, 10, 0, 5], "x_max") == 5.0

    def test_y_min_wall(self):
        assert wall_length_for_fc([0, 10, 0, 5], "y_min") == 10.0

    def test_y_max_wall(self):
        assert wall_length_for_fc([0, 10, 0, 5], "y_max") == 10.0

    def test_asymmetric_boundary(self):
        # boundary [2, 12, 3, 8] -> x_range=10, y_range=5
        assert wall_length_for_fc([2, 12, 3, 8], "x_min") == 5.0
        assert wall_length_for_fc([2, 12, 3, 8], "y_min") == 10.0

    def test_zero_size(self):
        assert wall_length_for_fc([5, 5, 3, 3], "x_min") == 0.0
        assert wall_length_for_fc([5, 5, 3, 3], "y_min") == 0.0

    def test_invalid_wall_id(self):
        with pytest.raises(ValueError):
            wall_length_for_fc([0, 10, 0, 5], "z_min")


# ============================================================
# wall_length_for_building
# ============================================================
class TestWallLengthForBuilding:
    """building_boundary = [offset_x, length, offset_y, width].
    y walls (y_min, y_max) -> length.
    x walls (x_min, x_max) -> width.
    """

    def test_y_min_wall(self):
        assert wall_length_for_building([0, 20, 0, 10], "y_min") == 20.0

    def test_y_max_wall(self):
        assert wall_length_for_building([0, 20, 0, 10], "y_max") == 20.0

    def test_x_min_wall(self):
        assert wall_length_for_building([0, 20, 0, 10], "x_min") == 10.0

    def test_x_max_wall(self):
        assert wall_length_for_building([0, 20, 0, 10], "x_max") == 10.0

    def test_with_offset(self):
        # offset doesn't affect length/width
        assert wall_length_for_building([5, 30, 10, 15], "y_min") == 30.0
        assert wall_length_for_building([5, 30, 10, 15], "x_min") == 15.0

    def test_invalid_wall_id(self):
        with pytest.raises(ValueError):
            wall_length_for_building([0, 20, 0, 10], "top")


# ============================================================
# is_coplanar
# ============================================================
class TestIsCoplanar:
    """FC boundary edge on building boundary means coplanar.
    x_min==0, x_max==building_length, y_min==0, y_max==building_width.
    """

    def test_x_min_coplanar(self):
        # fc boundary x_min == 0
        assert is_coplanar([0, 10, 0, 5], 20, 10, "x_min") is True

    def test_x_min_not_coplanar(self):
        # fc boundary x_min == 5 != 0
        assert is_coplanar([5, 10, 0, 5], 20, 10, "x_min") is False

    def test_x_max_coplanar(self):
        # fc boundary x_max == 20 == building_length
        assert is_coplanar([10, 20, 0, 5], 20, 10, "x_max") is True

    def test_x_max_not_coplanar(self):
        # fc boundary x_max == 15 != 20
        assert is_coplanar([10, 15, 0, 5], 20, 10, "x_max") is False

    def test_y_min_coplanar(self):
        assert is_coplanar([0, 10, 0, 5], 20, 10, "y_min") is True

    def test_y_min_not_coplanar(self):
        assert is_coplanar([0, 10, 2, 5], 20, 10, "y_min") is False

    def test_y_max_coplanar(self):
        # fc boundary y_max == 10 == building_width
        assert is_coplanar([0, 10, 5, 10], 20, 10, "y_max") is True

    def test_y_max_not_coplanar(self):
        assert is_coplanar([0, 10, 5, 8], 20, 10, "y_max") is False

    def test_full_building_fc_all_walls_coplanar(self):
        # FC spans entire building
        assert is_coplanar([0, 20, 0, 10], 20, 10, "x_min") is True
        assert is_coplanar([0, 20, 0, 10], 20, 10, "x_max") is True
        assert is_coplanar([0, 20, 0, 10], 20, 10, "y_min") is True
        assert is_coplanar([0, 20, 0, 10], 20, 10, "y_max") is True

    def test_tolerance(self):
        # Within default tolerance
        assert is_coplanar([1e-7, 10, 0, 5], 20, 10, "x_min") is True
        # Barely outside tolerance
        assert is_coplanar([1e-5, 10, 0, 5], 20, 10, "x_min") is False

    def test_custom_tolerance(self):
        assert is_coplanar([0.01, 10, 0, 5], 20, 10, "x_min", tol=0.1) is True
        assert is_coplanar([0.01, 10, 0, 5], 20, 10, "x_min", tol=0.001) is False

    def test_invalid_wall_id(self):
        with pytest.raises(ValueError):
            is_coplanar([0, 10, 0, 5], 20, 10, "z_max")


# ============================================================
# fc_wall_start_offset
# ============================================================
class TestFcWallStartOffset:
    """y_min/y_max walls: return x_min. x_min/x_max walls: return y_min."""

    def test_y_min_wall(self):
        assert fc_wall_start_offset([5, 15, 0, 10], "y_min") == 5.0

    def test_y_max_wall(self):
        assert fc_wall_start_offset([5, 15, 0, 10], "y_max") == 5.0

    def test_x_min_wall(self):
        assert fc_wall_start_offset([0, 10, 3, 8], "x_min") == 3.0

    def test_x_max_wall(self):
        assert fc_wall_start_offset([0, 10, 3, 8], "x_max") == 3.0

    def test_zero_offset(self):
        assert fc_wall_start_offset([0, 10, 0, 5], "y_min") == 0.0
        assert fc_wall_start_offset([0, 10, 0, 5], "x_min") == 0.0

    def test_invalid_wall_id(self):
        with pytest.raises(ValueError):
            fc_wall_start_offset([0, 10, 0, 5], "north")


# ============================================================
# detect_coplanar_openings
# ============================================================
class TestDetectCoplanarOpenings:
    """Detect FC openings on coplanar walls.
    Shift boundary[0] += fc_wall_start_offset. Return list[Opening].
    """

    def _make_building_and_story(self):
        """Helper: building 20x10 with one story,
        two fire compartments: FC-A [0,10,0,10] and FC-B [10,20,0,10].
        FC-A has an opening on x_max wall (coplanar with FC-B x_min, but NOT with building).
        FC-A has an opening on x_min wall (coplanar with building x_min).
        """
        fc_a = FireCompartment(
            name="FC-A",
            boundary=[0, 10, 0, 10],
            openings=[
                Opening(wall="x_max", type="door", boundary=[2, 3, 0, 3]),  # internal wall
                Opening(wall="x_min", type="window", boundary=[1, 2, 1, 1.5]),  # exterior wall
            ],
        )
        fc_b = FireCompartment(
            name="FC-B",
            boundary=[10, 20, 0, 10],
            openings=[
                Opening(wall="x_min", type="door", boundary=[2, 3, 0, 3]),  # internal wall
                Opening(wall="y_max", type="window", boundary=[3, 2, 1, 1.5]),  # exterior wall
            ],
        )
        story = Story(
            name="1F",
            height=4.0,
            fire_compartments=[fc_a, fc_b],
        )
        building = Building(
            name="test",
            boundary=[0, 20, 0, 10],
            wall_thickness=0.24,
            stories=[story],
        )
        building.update_z_offsets()
        return building, story

    def test_detects_coplanar_openings(self):
        building, story = self._make_building_and_story()
        results = detect_coplanar_openings(building, story)
        # FC-A x_min is coplanar (x_min==0), opening: wall="x_min", boundary=[1,2,1,1.5]
        # FC-B y_max is coplanar (y_max==10==building_width), opening: wall="y_max", boundary=[3,2,1,1.5]
        #   shifted: boundary[0] += fc_wall_start_offset([10,20,0,10], "y_max") = 10
        #   -> boundary=[13, 2, 1, 1.5]
        assert len(results) >= 2

    def test_shifts_offset_for_coplanar(self):
        building, story = self._make_building_and_story()
        results = detect_coplanar_openings(building, story)
        # Find the shifted FC-B y_max opening
        y_max_openings = [o for o in results if o.wall == "y_max"]
        assert len(y_max_openings) == 1
        # Original w_offset=3, fc_wall_start_offset for y_max returns x_min=10
        assert y_max_openings[0].boundary[0] == pytest.approx(13.0)

    def test_unshifted_at_origin(self):
        building, story = self._make_building_and_story()
        results = detect_coplanar_openings(building, story)
        # FC-A x_min opening: fc_wall_start_offset([0,10,0,10], "x_min") = 0
        # so boundary[0] stays at 1
        x_min_openings = [o for o in results if o.wall == "x_min"]
        assert len(x_min_openings) == 1
        assert x_min_openings[0].boundary[0] == pytest.approx(1.0)

    def test_no_coplanar_openings(self):
        """FC in the middle of the building, no walls on building boundary."""
        fc = FireCompartment(
            name="center",
            boundary=[5, 15, 3, 7],
            openings=[Opening(wall="x_min", type="door", boundary=[0, 2, 0, 3])],
        )
        story = Story(name="1F", height=3.0, fire_compartments=[fc])
        building = Building(
            name="test",
            boundary=[0, 20, 0, 10],
            stories=[story],
        )
        building.update_z_offsets()
        results = detect_coplanar_openings(building, story)
        assert results == []

    def test_no_fire_compartments(self):
        story = Story(name="1F", height=3.0, fire_compartments=[])
        building = Building(name="test", boundary=[0, 20, 0, 10], stories=[story])
        building.update_z_offsets()
        results = detect_coplanar_openings(building, story)
        assert results == []

    def test_returns_opening_instances(self):
        building, story = self._make_building_and_story()
        results = detect_coplanar_openings(building, story)
        for o in results:
            assert isinstance(o, Opening)


# ============================================================
# resolve_negative_offset
# ============================================================
class TestResolveNegativeOffset:
    """Negative -> wall_length + w_offset - width. Positive -> unchanged."""

    def test_positive_unchanged(self):
        assert resolve_negative_offset(5.0, 2.0, 20.0) == 5.0

    def test_zero_unchanged(self):
        assert resolve_negative_offset(0.0, 2.0, 20.0) == 0.0

    def test_negative_resolved(self):
        # wall_length + w_offset - width = 20 + (-3) - 2 = 15
        assert resolve_negative_offset(-3.0, 2.0, 20.0) == 15.0

    def test_negative_flush_end(self):
        # wall_length + (-width) - width = 20 + (-2) - 2 = 16
        assert resolve_negative_offset(-2.0, 2.0, 20.0) == 16.0

    def test_negative_minus_one(self):
        # Common pattern: offset=-1 means 1m from end
        # wall_length + (-1) - width = 20 - 1 - 2 = 17
        assert resolve_negative_offset(-1.0, 2.0, 20.0) == 17.0

    def test_large_negative(self):
        # wall_length + w_offset - width = 20 + (-18) - 2 = 0
        assert resolve_negative_offset(-18.0, 2.0, 20.0) == 0.0


# ============================================================
# opening_to_world_coords
# ============================================================
class TestOpeningToWorldCoords:
    """Convert opening to [x1, x2, y1, y2, z1, z2] world coords."""

    def _make_building_story_opening(
        self, wall, boundary, bld_boundary=None, story_height=4.0, z_bottom=0.0
    ):
        if bld_boundary is None:
            bld_boundary = [0, 20, 0, 10]
        opening = Opening(wall=wall, type="door", boundary=boundary)
        story = Story(name="1F", height=story_height)
        story.z_bottom = z_bottom
        building = Building(boundary=bld_boundary, stories=[story])
        return opening, building, story

    def test_y_min_wall_exterior(self):
        # Opening on y_min wall: runs along x axis
        # boundary = [w_offset=3, width=2, h_offset=0, height=3]
        # building boundary = [offset_x=0, length=20, offset_y=0, width=10]
        # x1 = offset_x + w_offset = 0 + 3 = 3
        # x2 = offset_x + w_offset + width = 0 + 3 + 2 = 5
        # y1 = y2 = offset_y = 0  (on y_min wall)
        # z1 = z_bottom + h_offset = 0 + 0 = 0
        # z2 = z_bottom + h_offset + height = 0 + 0 + 3 = 3
        opening, building, story = self._make_building_story_opening(
            "y_min", [3, 2, 0, 3]
        )
        result = opening_to_world_coords(opening, building, story, is_exterior=True)
        x1, x2, y1, y2, z1, z2 = result
        assert x1 == pytest.approx(3.0)
        assert x2 == pytest.approx(5.0)
        assert y1 == pytest.approx(0.0)
        assert y2 == pytest.approx(0.0)
        assert z1 == pytest.approx(0.0)
        assert z2 == pytest.approx(3.0)

    def test_y_max_wall_exterior(self):
        # y_max wall: y = offset_y + width = 0 + 10 = 10
        opening, building, story = self._make_building_story_opening(
            "y_max", [5, 3, 1, 2]
        )
        result = opening_to_world_coords(opening, building, story, is_exterior=True)
        x1, x2, y1, y2, z1, z2 = result
        assert x1 == pytest.approx(5.0)
        assert x2 == pytest.approx(8.0)
        assert y1 == pytest.approx(10.0)
        assert y2 == pytest.approx(10.0)
        assert z1 == pytest.approx(1.0)
        assert z2 == pytest.approx(3.0)

    def test_x_min_wall_exterior(self):
        # x_min wall: runs along y axis
        # x1 = x2 = offset_x = 0
        # y1 = offset_y + w_offset
        # y2 = offset_y + w_offset + width
        opening, building, story = self._make_building_story_opening(
            "x_min", [2, 4, 0, 3]
        )
        result = opening_to_world_coords(opening, building, story, is_exterior=True)
        x1, x2, y1, y2, z1, z2 = result
        assert x1 == pytest.approx(0.0)
        assert x2 == pytest.approx(0.0)
        assert y1 == pytest.approx(2.0)
        assert y2 == pytest.approx(6.0)
        assert z1 == pytest.approx(0.0)
        assert z2 == pytest.approx(3.0)

    def test_x_max_wall_exterior(self):
        # x_max wall: x = offset_x + length = 0 + 20 = 20
        opening, building, story = self._make_building_story_opening(
            "x_max", [1, 3, 0.5, 2.5]
        )
        result = opening_to_world_coords(opening, building, story, is_exterior=True)
        x1, x2, y1, y2, z1, z2 = result
        assert x1 == pytest.approx(20.0)
        assert x2 == pytest.approx(20.0)
        assert y1 == pytest.approx(1.0)
        assert y2 == pytest.approx(4.0)
        assert z1 == pytest.approx(0.5)
        assert z2 == pytest.approx(3.0)

    def test_with_building_offset(self):
        # building boundary = [5, 20, 3, 10], y_min wall
        # x1 = 5 + 2 = 7, x2 = 5 + 2 + 3 = 10
        # y1 = y2 = 3
        opening, building, story = self._make_building_story_opening(
            "y_min", [2, 3, 0, 3], bld_boundary=[5, 20, 3, 10]
        )
        result = opening_to_world_coords(opening, building, story, is_exterior=True)
        x1, x2, y1, y2, z1, z2 = result
        assert x1 == pytest.approx(7.0)
        assert x2 == pytest.approx(10.0)
        assert y1 == pytest.approx(3.0)
        assert y2 == pytest.approx(3.0)

    def test_second_story(self):
        # z_bottom = 4.0 for second story
        opening, building, story = self._make_building_story_opening(
            "y_min", [0, 5, 0, 2], story_height=3.0, z_bottom=4.0
        )
        result = opening_to_world_coords(opening, building, story, is_exterior=True)
        z1, z2 = result[4], result[5]
        assert z1 == pytest.approx(4.0)
        assert z2 == pytest.approx(6.0)

    def test_returns_six_element_tuple(self):
        opening, building, story = self._make_building_story_opening(
            "y_min", [0, 5, 0, 3]
        )
        result = opening_to_world_coords(opening, building, story)
        assert len(result) == 6

    def test_interior_opening_x_min(self):
        # For interior opening (is_exterior=False), the coordinate
        # along the wall axis uses the FC boundary instead of building
        # We test the basic return shape works
        fc = FireCompartment(
            name="FC",
            boundary=[5, 15, 0, 10],
            openings=[],
        )
        opening = Opening(wall="x_min", type="door", boundary=[2, 3, 0, 3])
        story = Story(name="1F", height=4.0, fire_compartments=[fc])
        story.z_bottom = 0.0
        building = Building(boundary=[0, 20, 0, 10], stories=[story])
        result = opening_to_world_coords(opening, building, story, is_exterior=False)
        assert len(result) == 6
        # For interior x_min wall with fc boundary x_min=5:
        # x1 = x2 = offset_x + fc_x_min = 0 + 5 = 5
        x1, x2 = result[0], result[1]
        assert x1 == pytest.approx(5.0)
        assert x2 == pytest.approx(5.0)


# ============================================================
# Integration tests
# ============================================================
class TestGeometryIntegration:
    def test_coplanar_then_world_coords(self):
        """Detect coplanar opening, then convert to world coords."""
        fc = FireCompartment(
            name="FC-Left",
            boundary=[0, 10, 0, 10],
            openings=[
                Opening(wall="x_min", type="door", boundary=[2, 3, 0, 3]),
            ],
        )
        story = Story(name="1F", height=4.0, fire_compartments=[fc])
        building = Building(
            name="plant",
            boundary=[0, 20, 0, 10],
            wall_thickness=0.24,
            stories=[story],
        )
        building.update_z_offsets()

        coplanars = detect_coplanar_openings(building, story)
        assert len(coplanars) == 1

        o = coplanars[0]
        coords = opening_to_world_coords(o, building, story, is_exterior=True)
        x1, x2, y1, y2, z1, z2 = coords
        # x_min wall: x=0, y runs along wall
        assert x1 == pytest.approx(0.0)
        assert x2 == pytest.approx(0.0)
        # w_offset=2, width=3 -> y1=2, y2=5
        assert y1 == pytest.approx(2.0)
        assert y2 == pytest.approx(5.0)
        assert z1 == pytest.approx(0.0)
        assert z2 == pytest.approx(3.0)

    def test_negative_offset_then_world_coords(self):
        """Resolve negative offset before converting."""
        wall_len = wall_length_for_building([0, 20, 0, 10], "y_min")
        w_offset = resolve_negative_offset(-3.0, 2.0, wall_len)
        # wall_length=20, -3 + 20 - 2 = 15
        assert w_offset == pytest.approx(15.0)

        opening = Opening(wall="y_min", type="window", boundary=[w_offset, 2, 1, 1.5])
        story = Story(name="1F", height=4.0)
        story.z_bottom = 0.0
        building = Building(boundary=[0, 20, 0, 10], stories=[story])

        coords = opening_to_world_coords(opening, building, story, is_exterior=True)
        x1, x2, y1, y2, z1, z2 = coords
        assert x1 == pytest.approx(15.0)
        assert x2 == pytest.approx(17.0)
        assert y1 == pytest.approx(0.0)
        assert y2 == pytest.approx(0.0)
        assert z1 == pytest.approx(1.0)
        assert z2 == pytest.approx(2.5)


# ============================================================
# validate_opening_bounds
# ============================================================
class TestValidateOpeningBounds:
    """Validate that an opening fits within its wall segment."""

    def test_valid_opening_no_errors(self):
        """Opening well within wall returns no errors."""
        opening = Opening(wall="y_min", type="door", boundary=[2, 3, 0, 2.5])
        errors = validate_opening_bounds(opening, wall_length=20.0, story_height=4.0)
        assert errors == []

    def test_opening_flush_with_wall_end(self):
        """Opening exactly at wall edge is valid (within tolerance)."""
        opening = Opening(wall="y_min", type="door", boundary=[17, 3, 0, 4])
        errors = validate_opening_bounds(opening, wall_length=20.0, story_height=4.0)
        assert errors == []

    def test_opening_exceeds_wall_length(self):
        """Opening that exceeds wall length returns error."""
        opening = Opening(wall="y_min", type="door", boundary=[18, 3, 0, 2])
        errors = validate_opening_bounds(opening, wall_length=20.0, story_height=4.0)
        assert len(errors) == 1
        assert "exceeds wall length" in errors[0]

    def test_opening_exceeds_story_height(self):
        """Opening that exceeds story height returns error."""
        opening = Opening(wall="y_min", type="window", boundary=[0, 2, 2, 3])
        errors = validate_opening_bounds(opening, wall_length=20.0, story_height=4.0)
        assert len(errors) == 1
        assert "exceeds story height" in errors[0]

    def test_negative_w_offset_resolves_valid(self):
        """Negative w_offset that resolves to valid position returns no errors."""
        # resolve: wall_length + w_offset - width = 20 + (-3) - 2 = 15
        # 15 + 2 = 17 <= 20, so valid
        opening = Opening(wall="y_min", type="door", boundary=[-3, 2, 0, 2])
        errors = validate_opening_bounds(opening, wall_length=20.0, story_height=4.0)
        assert errors == []

    def test_negative_w_offset_resolves_invalid(self):
        """Negative w_offset that resolves to negative returns error."""
        # resolve: wall_length + w_offset - width = 5 + (-10) - 3 = -8
        opening = Opening(wall="y_min", type="door", boundary=[-10, 3, 0, 2])
        errors = validate_opening_bounds(opening, wall_length=5.0, story_height=4.0)
        assert any("w_offset" in e and "negative" in e for e in errors)

    def test_negative_h_offset(self):
        """Negative h_offset returns error."""
        opening = Opening(wall="y_min", type="window", boundary=[0, 2, -1, 2])
        errors = validate_opening_bounds(opening, wall_length=20.0, story_height=4.0)
        assert len(errors) == 1
        assert "h_offset" in errors[0] and "negative" in errors[0]

    def test_multiple_errors(self):
        """Opening that exceeds both wall and story returns two errors."""
        opening = Opening(wall="y_min", type="door", boundary=[19, 3, 3, 3])
        errors = validate_opening_bounds(opening, wall_length=20.0, story_height=4.0)
        assert len(errors) == 2


# ============================================================
# validate_building
# ============================================================
class TestValidateBuilding:
    """Validate all openings across stories and fire compartments."""

    def test_valid_building_no_errors(self):
        """A building with all valid openings returns no errors."""
        fc = FireCompartment(
            name="FC-A",
            boundary=[0, 10, 0, 10],
            openings=[Opening(wall="x_min", type="door", boundary=[1, 2, 0, 2])],
        )
        story = Story(
            name="1F",
            height=4.0,
            openings=[Opening(wall="y_min", type="window", boundary=[2, 3, 1, 1.5])],
            fire_compartments=[fc],
        )
        building = Building(
            name="test",
            boundary=[0, 20, 0, 10],
            stories=[story],
        )
        building.update_z_offsets()
        errors = validate_building(building)
        assert errors == []

    def test_catches_exterior_opening_error(self):
        """Detects exterior opening that exceeds wall length."""
        story = Story(
            name="1F",
            height=4.0,
            openings=[Opening(wall="y_min", type="door", boundary=[18, 5, 0, 2])],
        )
        building = Building(
            name="test",
            boundary=[0, 20, 0, 10],
            stories=[story],
        )
        building.update_z_offsets()
        errors = validate_building(building)
        assert len(errors) == 1
        assert "Story 1F" in errors[0]
        assert "exterior opening 0" in errors[0]

    def test_catches_fc_opening_error(self):
        """Detects FC opening that exceeds wall length."""
        fc = FireCompartment(
            name="FC-A",
            boundary=[0, 5, 0, 5],
            openings=[Opening(wall="x_min", type="door", boundary=[3, 4, 0, 2])],
        )
        story = Story(
            name="2F",
            height=3.0,
            fire_compartments=[fc],
        )
        building = Building(
            name="test",
            boundary=[0, 20, 0, 10],
            stories=[story],
        )
        building.update_z_offsets()
        errors = validate_building(building)
        assert len(errors) == 1
        assert "FC 'FC-A'" in errors[0]

    def test_catches_errors_across_stories(self):
        """Detects errors in multiple stories."""
        story1 = Story(
            name="1F",
            height=3.0,
            openings=[Opening(wall="y_min", type="door", boundary=[19, 5, 0, 2])],
        )
        story2 = Story(
            name="2F",
            height=3.0,
            openings=[Opening(wall="x_min", type="window", boundary=[0, 2, 2, 3])],
        )
        building = Building(
            name="test",
            boundary=[0, 20, 0, 10],
            stories=[story1, story2],
        )
        building.update_z_offsets()
        errors = validate_building(building)
        assert len(errors) == 2
        assert any("Story 1F" in e for e in errors)
        assert any("Story 2F" in e for e in errors)
