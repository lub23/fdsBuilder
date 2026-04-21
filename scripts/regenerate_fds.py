#!/usr/bin/env python3
"""Regenerate FDS files from facility JSON files with fixes applied."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models.building import BuildingGroup, Building
from generators.fds_generator import FDSGenerator


def load_facility_json(json_path: Path) -> dict:
    """Load facility JSON file."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def facility_json_to_building_group(data: dict) -> BuildingGroup:
    """Convert facility JSON to BuildingGroup."""
    if "buildings" not in data:
        raise ValueError("JSON must contain 'buildings' key")

    buildings_data = data["buildings"]
    buildings = [Building.from_dict(b) for b in buildings_data]

    bg = BuildingGroup(name=data.get("name", ""), buildings=buildings)

    if "heat_source" in data:
        bg.heat_source = data["heat_source"]
    if "simulation_time" in data:
        bg.simulation_time = data["simulation_time"]
    if "domain" in data:
        bg.domain = data["domain"]

    return bg


def regenerate_fds(facility_name: str):
    """Regenerate FDS file for a facility."""
    json_path = Path(f"facilities/{facility_name}.json")
    fds_path = Path(f"case/{facility_name}.fds")

    if not json_path.exists():
        print(f"ERROR: {json_path} not found")
        return False

    data = load_facility_json(json_path)
    bg = facility_json_to_building_group(data)

    generator = FDSGenerator(bg)
    fds_code = generator.generate()

    with open(fds_path, "w", encoding="utf-8") as f:
        f.write(fds_code)

    domain, grid_size = generator._compute_mesh()
    nx = max(10, int((domain[1] - domain[0]) / grid_size))
    ny = max(10, int((domain[3] - domain[2]) / grid_size))
    nz = max(10, int((domain[5] - domain[4]) / grid_size))
    total_cells = nx * ny * nz

    print(f"Regenerated {fds_path}")
    print(f"  Domain: {domain}")
    print(f"  Grid size: {grid_size:.2f}m")
    print(f"  Mesh: {nx} x {ny} x {nz} = {total_cells:,} cells")

    return True


def main():
    facilities = ["airport_hangar", "warrick_power_plant"]

    for facility in facilities:
        print(f"\n{'=' * 60}")
        print(f"Regenerating {facility}")
        print("=" * 60)
        regenerate_fds(facility)


if __name__ == "__main__":
    main()
