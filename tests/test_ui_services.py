import json

from models.building import BuildingGroup
from services.fds_naming import (
    default_fds_filename,
    default_smv_filename,
    results_dir_for,
    results_smv_path,
    sanitize_chid,
    video_path_for,
)
from services.program_paths import load_program_path, save_program_path


def test_sanitize_chid_keeps_existing_ascii_behavior():
    assert sanitize_chid("foo bar.baz-qux") == "foo_bar_baz_qux"
    assert sanitize_chid("中文") == "building"


def test_default_fds_filename_uses_heat_source_suffix():
    model = BuildingGroup(name="test case")
    model.heat_source.update({"net_heat_flux": 1234, "azimuth": 45, "elevation": 30, "duration": 2.1})
    model.simulation_time = 600

    assert default_fds_filename(model) == "test_case_q1234_a45_e30_d2100_t600.fds"
    assert default_smv_filename(model) == "test_case_q1234_a45_e30_d2100_t600.smv"


def test_results_paths_match_precomputed_layout():
    model = BuildingGroup(name="frymaster_corporation")
    model.heat_source.update({"net_heat_flux": 500, "azimuth": 0, "elevation": 0, "duration": 1.36})
    model.simulation_time = 1800

    assert results_dir_for(model) == (
        "results/frymaster_corporation/frymaster_corporation_q500_a0_e0_d1360_t1800"
    )
    assert results_smv_path(model) == (
        "results/frymaster_corporation/frymaster_corporation_q500_a0_e0_d1360_t1800/"
        "frymaster_corporation_q500_a0_e0_d1360_t1800.smv"
    )


def test_video_path_matches_demo_clip_naming():
    model = BuildingGroup(name="hangar lingen")
    model.heat_source.update({"net_heat_flux": 30000, "azimuth": 270, "elevation": 60, "duration": 7.5})
    model.simulation_time = 1800

    assert video_path_for(model) == "video/hangar_lingen_q30000_a270_e60_d7500_t1800.mp4"


def test_reference_case_base_name_strips_condition_suffix():
    from services.damage_prediction import reference_case_base_name

    assert reference_case_base_name("ligen") == "hangar_ligen"
    assert reference_case_base_name("hanger") == "hanger"
    assert reference_case_base_name("unknown_facility_code") == "unknown_facility_code"


def test_program_path_round_trip(tmp_path):
    config_file = tmp_path / "program_paths.json"
    save_program_path("test_tool", "/opt/fds/bin/test_tool", config_file=config_file)

    assert load_program_path("test_tool", config_file=config_file) == "/opt/fds/bin/test_tool"
    assert json.loads(config_file.read_text())["test_tool"] == "/opt/fds/bin/test_tool"


def test_damage_facility_resolves_specialized_identity():
    from services.damage_prediction import resolve_damage_facility

    model = BuildingGroup(name="Frymaster Corporation")
    assert resolve_damage_facility(model, {"frymaster_corporation"}) == (
        "frymaster_corporation",
        None,
    )


def test_damage_facility_resolves_equivalent_scale_from_dimensions():
    from models.facility import FacilityManager
    from services.damage_prediction import resolve_damage_facility

    manager = FacilityManager()
    buildings = []
    for name in manager.list_buildings("aerospace"):
        params = manager.params_for_scale("aerospace", name, scale_idx=2)
        buildings.append(manager.load_equivalent("aerospace", name, params))
    model = BuildingGroup(name="aerospace", buildings=buildings)

    assert resolve_damage_facility(
        model,
        {"aerospace_small", "aerospace_medium", "aerospace_large"},
    ) == ("aerospace_large", "large")


def test_damage_facility_rejects_unknown_custom_model():
    import pytest

    from services.damage_prediction import (
        UnsupportedDamageFacility,
        resolve_damage_facility,
    )

    with pytest.raises(UnsupportedDamageFacility, match="不在当前代理模型"):
        resolve_damage_facility(BuildingGroup(name="custom"), {"aerospace_small"})
