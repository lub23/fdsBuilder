"""Heat source parameters: 4-dim feature vector, enumerated parameter options."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Tuple


ELEVATION_OPTIONS: Tuple[int, ...] = (0, 30, 45, 60)
DURATION_OPTIONS: Tuple[float, ...] = (1.36, 2.1, 7.5)
HEAT_FLUX_OPTIONS: Tuple[float, ...] = (50, 100, 500, 1000, 2000, 3000, 5000, 7000, 10000, 12000, 15000, 20000)
AZIMUTH_OPTIONS: Tuple[int, ...] = tuple(range(0, 360, 5))


@dataclass(frozen=True)
class HeatSourceParams:
    elevation: int
    azimuth: int
    duration: float
    heat_flux: float

    def __post_init__(self) -> None:
        if self.elevation not in ELEVATION_OPTIONS:
            raise ValueError(
                f"elevation {self.elevation} not in {ELEVATION_OPTIONS}"
            )
        if self.duration <=0:
            raise ValueError(
                f"duration {self.duration} should be positive"
            )
        # if self.duration not in DURATION_OPTIONS:
        #     raise ValueError(
        #         f"duration {self.duration} not in {DURATION_OPTIONS}"
        #     )
        if self.heat_flux not in HEAT_FLUX_OPTIONS:
            raise ValueError(
                f"heat_flux {self.heat_flux} not in {HEAT_FLUX_OPTIONS}"
            )
        if self.azimuth not in AZIMUTH_OPTIONS:
            raise ValueError(
                f"azimuth {self.azimuth} must be in 0..355 step 5"
            )

    def to_feature_vector(self) -> List[float]:
        return [
            float(self.elevation),
            float(self.azimuth),
            float(self.duration),
            float(self.heat_flux),
        ]


def iter_heat_source_combinations() -> Iterator[HeatSourceParams]:
    for e in ELEVATION_OPTIONS:
        for d in DURATION_OPTIONS:
            for hf in HEAT_FLUX_OPTIONS:
                for az in AZIMUTH_OPTIONS:
                    yield HeatSourceParams(
                        elevation=e, azimuth=az, duration=d, heat_flux=hf
                    )
