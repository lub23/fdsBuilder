"""8-category combustible classification.

Maps `COMBUSTIBLE_LIBRARY` keys in `models/materials.py` to a fixed taxonomy
and computes per-building normalized vectors.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Tuple


COMBUSTIBLE_CATEGORIES: Tuple[str, ...] = (
    "wood_paper",
    "textile",
    "plastic",
    "fuel_oil",
    "electronics",
    "chemical",
    "metal",
    "composite",
)


# Order matters: first-match wins. More specific keywords are placed before
# more general ones (e.g. AEROSPACE_COMPOSITE before COMPOSITE-like keys).
_RULES: List[Tuple[str, Tuple[str, ...]]] = [
    (
        "composite",
        (
            "AEROSPACE_COMPOSITE",
            "PREPREG",
            "FIBER_INSULATION",
            "SURFACE_COATING_LAYER",
            "POWDER_COATING",
            "DISPLAY_PROP_MODEL",
            "DIESEL_GENERATOR",
            "PLASTIC_EQUIPMENT",
            "EMERGENCY_SUPPLIES",
            "ACCESSORIES",
        ),
    ),
    (
        "electronics",
        (
            "OIL_CIRCUIT_BREAKER",
            "OIL_TRANSFORMER",
            "FIRE_CONTROL_HOST",
            "FIRE_PUMP_CABLE",
            "CABLE",
            "CONTROL_CABINET",
            "SWITCH_CABINET",
            "SERVER_CABINET",
            "ELECTRICAL_CABINET",
            "ELECTRICAL_EQUIPMENT",
            "ELECTRICAL_PANEL",
            "ELECTRONICS_CONSOLE",
            "CONTROL_ROOM",
            "TEST_EQUIPMENT",
            "LAB_EQUIPMENT",
            "OFFICE_EQUIPMENT",
            "MONITOR_CABLE",
            "NETWORK_CABLE",
        ),
    ),
    (
        "chemical",
        (
            "OILY_RAGS",
            "OILY_WASTE",
            "OILY_SLUDGE",
            "CHEMICAL",
            "SOLVENT",
            "PAINT",
            "COATING_AGENT",
            "COATING_SOLVENT",
            "ADHESIVE",
            "SEALANT",
            "BITUMEN",
            "POLISHING_PASTE",
            "GRINDING_SLUDGE",
            "HAZARDOUS",
            "REAGENT",
            "ELECTROLYTE",
            "WELDING_GAS",
            "RUST_PREVENTION",
            "CUTTING_FLUID",
        ),
    ),
    (
        "wood_paper",
        (
            "WOODEN_PALLET",
            "WOOD_PALLET",
            "WOODEN_FURNITURE",
            "WOOD_FURNITURE",
            "WOOD_TABLE",
            "WOOD_CHAIR",
            "WOODEN_BOX",
            "PAPER_STACK",
            "PAPER_ARCHIVE",
            "PAPER_BOX",
            "DENSE_ARCHIVE",
            "CARDBOARD_BOX",
            "PACKING_BOX",
            "PACKING_MATERIAL",
            "BOOKSHELF",
            "MEETING_TABLE",
            "OFFICE_CHAIR",
            "OFFICE_FURNITURE",
            "OFFICE_COMPOSITE_FURNITURE",
            "OFFICE_SUPPLIES",
            "TEMP_TIMBER",
        ),
    ),
    (
        "textile",
        (
            "FABRIC",
            "MATTRESS",
            "CURTAIN",
            "CARPET",
            "TEXTILE",
            "UPHOLSTERED",
            "ACOUSTIC_PANEL",
            "AIRCRAFT_INTERIOR_TRIM",
            "DECORATION_MATERIAL",
        ),
    ),
    (
        "plastic",
        (
            "PLASTIC",
            "RUBBER",
            "POLYMER",
            "FOAM_PACKAGING",
            "ELECTRICAL_PLASTIC",
            "ESD_PACKAGING",
            "FRP_",
            "LIGHTWEIGHT_PARTITION",
        ),
    ),
    (
        "fuel_oil",
        (
            "JET_FUEL",
            "JET_FUEL_RESIDUE",
            "GLYCOL_DEICING",
            "LUBE_",
            "LUBRICATION",
            "HYDRAULIC",
            "PROPELLANT",
            "COMBUSTIBLE_GAS_CYLINDER",
            "GAS_CYLINDER",
            "IGNITION_OIL",
            "DIESEL",
            "GASOLINE",
            "FUEL",
            "OIL",
        ),
    ),
    (
        "metal",
        (
            "METAL",
            "STEEL_PLATE",
            "ALUMINUM_POWDER",
            "SPARE_PARTS_METAL",
            "ASSEMBLY_PARTS",
            "FINISHED_PRODUCT",
            "TOOL_BOX",
            "CRANE_SYSTEM",
            "CRANE_HYDRAULIC_TANK",
            "PREBAKED_ANODE",
            "CATHODE_CARBON",
            "CARBON_MATERIAL",
            "COAL_",
            "POT_TENDING",
            "ANODE_STAGING",
        ),
    ),
]


def classify_combustible_key(key: str) -> Optional[str]:
    """Return the taxonomy category for a COMBUSTIBLE_LIBRARY key, or None."""
    if not key:
        return None
    upper = key.upper()
    for category, keywords in _RULES:
        for kw in keywords:
            if kw in upper:
                return category
    return None


def combustible_vector(counts: Mapping[str, float]) -> List[float]:
    """Aggregate raw combustible counts into a normalized 8-dim vector.

    - If `counts` is empty or every key is unknown, returns a uniform 1/8
      vector so downstream models never see all-zero features.
    - Known+unknown mix: unknown counts are ignored (not added to any bucket),
      and the remaining known counts are normalized.
    """
    buckets: Dict[str, float] = {cat: 0.0 for cat in COMBUSTIBLE_CATEGORIES}
    total_known = 0.0
    for key, count in counts.items():
        if count <= 0:
            continue
        category = classify_combustible_key(key)
        if category is None:
            continue
        buckets[category] += float(count)
        total_known += float(count)

    if total_known <= 0:
        return [1.0 / 8.0] * 8

    return [buckets[cat] / total_known for cat in COMBUSTIBLE_CATEGORIES]
