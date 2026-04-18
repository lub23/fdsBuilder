"""核心枚举：毁伤等级、设施类型。"""

from __future__ import annotations

from enum import Enum


class DamageLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def numeric(self) -> int:
        return {"low": 0, "medium": 1, "high": 2}[self.value]

    @classmethod
    def from_numeric(cls, value: int) -> "DamageLevel":
        return cls({0: "low", 1: "medium", 2: "high"}[int(value)])


class FacilityType(Enum):
    AEROSPACE = "aerospace"
    AIRPORT_HANGAR = "airport_hangar"
    MACHINERY_MANUFACTURING = "machinery_manufacturing"
    METALLURGICAL = "metallurgical"

    @property
    def index(self) -> int:
        return {
            "aerospace": 0,
            "airport_hangar": 1,
            "machinery_manufacturing": 2,
            "metallurgical": 3,
        }[self.value]

    @classmethod
    def from_filename(cls, filename: str) -> "FacilityType":
        stem = filename.lower().rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if "aerospace" in stem:
            return cls.AEROSPACE
        if "airport" in stem or "hangar" in stem:
            return cls.AIRPORT_HANGAR
        if "machinery" in stem or "manufacturing" in stem:
            return cls.MACHINERY_MANUFACTURING
        if "metallurg" in stem:
            return cls.METALLURGICAL
        raise ValueError(f"Cannot infer FacilityType from filename: {filename}")
