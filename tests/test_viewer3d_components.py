import pytest

from models.building import Building, FireCompartment, Story
from models.combustibles import SPECIALIZED_COMPONENTS
from ui.viewer_3d import Viewer3D, _signature


class TestViewer3DComponentOrientation:
    def test_orientation_y_component_preview_item_swaps_footprint(self):
        viewer = Viewer3D.__new__(Viewer3D)
        comp = SPECIALIZED_COMPONENTS["POT_TENDING_MACHINE"]

        item = viewer._component_preview_item(
            comp,
            {"key": "POT_TENDING_MACHINE", "count": 1, "orientation": "y"},
            0,
        )

        assert item["length"] == comp.total_width
        assert item["width"] == comp.total_length
        assert item["_rotate_xy"] is True

    def test_orientation_y_component_part_bounds_runs_long_along_y(self):
        viewer = Viewer3D.__new__(Viewer3D)
        comp = SPECIALIZED_COMPONENTS["POT_TENDING_MACHINE"]
        item = viewer._component_preview_item(
            comp,
            {"key": "POT_TENDING_MACHINE", "count": 1, "orientation": "y"},
            0,
        )
        item["x"] = 1.0
        item["y"] = 2.0
        part = comp.parts[0]

        x1, x2, y1, y2, _z1, _z2 = viewer._component_part_bounds(
            item, part, 0.0, 0.0, 0.0
        )

        assert x2 - x1 == pytest.approx(part.width)
        assert y2 - y1 == pytest.approx(part.length)

    def test_building_signature_includes_component_orientation(self):
        def make_building(orientation):
            return Building(
                name="B",
                boundary=[0, 20, 0, 80],
                stories=[
                    Story(
                        name="1F",
                        height=12.0,
                        fire_compartments=[
                            FireCompartment(
                                name="FC",
                                boundary=[0, 20, 0, 80],
                                specialized_components=[
                                    {
                                        "key": "POT_TENDING_MACHINE",
                                        "count": 1,
                                        "orientation": orientation,
                                    }
                                ],
                            )
                        ],
                    )
                ],
            )

        assert _signature(make_building("x")) != _signature(make_building("y"))
