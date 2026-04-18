import math

import pytest

from agent_damage.src.processing.combustible_stats import (
    COMBUSTIBLE_CATEGORIES,
    classify_combustible_key,
    combustible_vector,
)


def test_categories_are_fixed_order_of_8():
    assert COMBUSTIBLE_CATEGORIES == (
        "wood_paper",
        "textile",
        "plastic",
        "fuel_oil",
        "electronics",
        "chemical",
        "metal",
        "composite",
    )


@pytest.mark.parametrize(
    "key,expected",
    [
        ("WOOD_TABLE", "wood_paper"),
        ("WOODEN_PALLET", "wood_paper"),
        ("PAPER_STACK", "wood_paper"),
        ("CARDBOARD_BOX", "wood_paper"),
        ("BOOKSHELF", "wood_paper"),
        ("FABRIC_SOFA", "textile"),
        ("CURTAIN", "textile"),
        ("CARPET_FINISH", "textile"),
        ("ACOUSTIC_PANEL", "textile"),
        ("PLASTIC_BIN", "plastic"),
        ("RUBBER_HOSE", "plastic"),
        ("POLYMER_MATERIAL", "plastic"),
        ("FOAM_PACKAGING", "plastic"),
        ("JET_FUEL", "fuel_oil"),
        ("DIESEL_TANK", "fuel_oil"),
        ("LUBE_OIL_TANK", "fuel_oil"),
        ("SOLID_PROPELLANT", "fuel_oil"),
        ("CABLE_BUNDLE", "electronics"),
        ("SWITCH_CABINET", "electronics"),
        ("SERVER_CABINET", "electronics"),
        ("OIL_TRANSFORMER", "electronics"),
        ("CHEMICAL_DRUM", "chemical"),
        ("PAINT_SOLVENT", "chemical"),
        ("ELECTROLYTE", "chemical"),
        ("OILY_SLUDGE_CONTAINER", "chemical"),
        ("METAL_PARTS", "metal"),
        ("STEEL_PLATE", "metal"),
        ("COAL_STACK", "metal"),
        ("PREBAKED_ANODE_BLOCK", "metal"),
        ("AEROSPACE_COMPOSITE_PART", "composite"),
        ("PREPREG_MATERIAL", "composite"),
        ("SURFACE_COATING_LAYER", "composite"),
        ("DIESEL_GENERATOR", "composite"),
    ],
)
def test_classify_combustible_key_known(key: str, expected: str):
    assert classify_combustible_key(key) == expected


def test_classify_unknown_key_returns_none():
    assert classify_combustible_key("ZZZ_TOTALLY_UNKNOWN") is None


def test_combustible_vector_normalized():
    counts = {"WOOD_TABLE": 2, "FABRIC_SOFA": 2, "JET_FUEL": 4}
    vec = combustible_vector(counts)
    assert len(vec) == 8
    assert math.isclose(sum(vec), 1.0, abs_tol=1e-9)
    assert math.isclose(vec[0], 0.25)  # wood_paper
    assert math.isclose(vec[1], 0.25)  # textile
    assert math.isclose(vec[3], 0.5)   # fuel_oil


def test_combustible_vector_empty_is_uniform():
    vec = combustible_vector({})
    assert len(vec) == 8
    for v in vec:
        assert math.isclose(v, 1 / 8)


def test_combustible_vector_unknown_keys_fallback_uniform():
    vec = combustible_vector({"ZZZ_UNKNOWN": 10})
    assert math.isclose(sum(vec), 1.0, abs_tol=1e-9)
    for v in vec:
        assert math.isclose(v, 1 / 8)
