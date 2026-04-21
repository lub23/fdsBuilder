#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File  : facility.py
@Author: Lubber
@Date  : 2026-03-09
@Version : 2.0
@Desc  : Simplified facility data management for the new JSON schema.
         Specialized buildings load directly via Building.from_dict().
         Equivalent buildings are generated via ParameterEngine.
"""

import json
import os
from typing import Dict

from models.building import Building
from models.parameter_engine import ParameterEngine


class FacilityManager:
    def __init__(self):
        self.facilities: Dict[str, dict] = {}
        facilities_dir = os.path.join(os.path.dirname(__file__), "..", "facilities")
        self._load_all(facilities_dir)

    def _load_all(self, data_dir: str):
        """Load all JSON files from ./facilities/"""
        filenames = sorted(f for f in os.listdir(data_dir) if f.endswith(".json"))
        for filename in filenames:
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            stem = filename[:-5]  # remove .json
            self.facilities[stem] = data

    def get_type(self, facility_name: str) -> str:
        """Return 'specialized' or 'equivalent'"""
        return self.facilities[facility_name]["type"]

    def list_buildings(self, facility_name: str) -> list:
        """List building names in a facility"""
        return [b["name"] for b in self.facilities[facility_name]["buildings"]]

    def get_building_data(self, facility_name: str, building_name: str) -> dict:
        """Get raw building dict from facility"""
        return self._find_building(facility_name, building_name)

    def load_specialized(self, facility_name: str, building_name: str) -> Building:
        """Load a specialized building directly (no conversion)"""
        bdata = self._find_building(facility_name, building_name)
        building = Building.from_dict(bdata)
        building.update_z_offsets()
        return building

    def load_equivalent(self, facility_name: str, building_name: str, params: dict) -> Building:
        """Generate a building from equivalent model template + user params"""
        bdata = self._find_building(facility_name, building_name)
        return ParameterEngine.generate(bdata, params)

    def default_params(self, facility_name: str, building_name: str) -> dict:
        """Get default parameter values for an equivalent model building.
        Returns dict with length, width, height, stories (default values from ranges)
        and their ranges for UI display."""
        bdata = self._find_building(facility_name, building_name)
        resolve = ParameterEngine.resolve_range
        return {
            "length": resolve(bdata["length_range"]),
            "width": resolve(bdata["width_range"]),
            "height": resolve(bdata["height_range"]),
            "stories": int(resolve(bdata["stories_range"])),
            "ranges": {
                "length": bdata["length_range"],
                "width": bdata["width_range"],
                "height": bdata["height_range"],
                "stories": bdata["stories_range"],
            },
        }

    def _find_building(self, facility_name: str, building_name: str) -> dict:
        """Find a building by name within a facility"""
        for b in self.facilities[facility_name]["buildings"]:
            if b["name"] == building_name:
                return b
        raise ValueError(f"Building '{building_name}' not found in facility '{facility_name}'")
