#!/usr/bin/env python3
"""Parameter sweep: export FDS for each facility × every parameter combination.

Each facility gets its own directory under case/.
  - net_heat_flux (temperature): 1500, 2000, 2500 K
  - duration:                    1.36, 2.1, 7.5 s
  - azimuth:                     0, 90, 180, 270 °
  - elevation:                   0, 30, 45, 60 °

Naming: {facility}_q{temp}_a{az}_e{el}_d{dur_ms}_t{sim_time}.fds
Total per facility: 3 × 3 × 4 × 4 = 144 cases
"""

import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

from models.building import Building, BuildingGroup
from generators.fds_generator import FDSGenerator

FACILITIES = [
    "materion_buffalo",
    "materion_newton",
    "warrick_power_plant",
]

HEAT_FLUXES = [1500, 2000, 2500]
DURATIONS = [1.36, 2.1, 7.5]
AZIMUTHS = [0, 90, 180, 270]
ELEVATIONS = [0, 30, 45, 60]

TOTAL = len(HEAT_FLUXES) * len(DURATIONS) * len(AZIMUTHS) * len(ELEVATIONS)


def build_bg_once(data: dict, facility: str) -> BuildingGroup:
    """Build BG once — FC placements, _click herd, etc. depend only on buildings."""
    buildings = [Building.from_dict(b) for b in data["buildings"]]
    for b in buildings:
        b.update_z_offsets()

    bg = BuildingGroup(name=facility, buildings=buildings)
    if "domain" in data:
        bg.domain = data["domain"]
    if "heat_source" in data:
        bg.heat_source = dict(data["heat_source"])

    bg.simulation_time = data.get("simulation_time", bg.simulation_time)
    return bg


def sweep(facility: str):
    t_fac_start = time.time()

    path = PROJECT_DIR / "facilities" / f"{facility}.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    out_dir = PROJECT_DIR / "case" / facility
    out_dir.mkdir(parents=True, exist_ok=True)
    # Clear out old fds files so we don't leave dead variants on disk.
    for fds in out_dir.glob("*.fds"):
        fds.unlink()

    bg = build_bg_once(data, facility)
    sim_time = int(bg.simulation_time)

    # Persistent mutable holders reused across cases.
    hs = bg.heat_source

    count = 0
    for flux in HEAT_FLUXES:
        for dur in DURATIONS:
            for az in AZIMUTHS:
                for el in ELEVATIONS:
                    dur_ms = int(dur * 1000)
                    fname = f"{facility}_q{flux}_a{az}_e{el}_d{dur_ms}_t{sim_time}.fds"
                    fpath = out_dir / fname

                    hs["net_heat_flux"] = flux
                    hs["duration"] = dur
                    hs["azimuth"] = az
                    hs["elevation"] = el

                    gen = FDSGenerator(bg)
                    fds_code = gen.generate()

                    fpath.write_text(fds_code, encoding="utf-8")

                    count += 1
                    print(f"  [{count:3d}/{TOTAL}] {fname}")

    print(f"  Done: {count} FDS in {time.time() - t_fac_start:.1f}s → {out_dir}")


def main():
    for fac in FACILITIES:
        print(f"\n{'='*60}")
        print(f"Facility: {fac}")
        print("=" * 60)
        sweep(fac)

    print(f"\nAll done.")


if __name__ == "__main__":
    main()
