import json

from models.building import BuildingGroup
from services.fds_naming import (
    default_fds_filename,
    default_smv_filename,
    results_dir_for,
    results_smv_path,
    sanitize_chid,
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


def test_program_path_round_trip(tmp_path):
    config_file = tmp_path / "program_paths.json"
    save_program_path("fds", "/opt/fds/bin/fds", config_file=config_file)

    assert load_program_path("fds", config_file=config_file) == "/opt/fds/bin/fds"
    assert json.loads(config_file.read_text())["fds"] == "/opt/fds/bin/fds"
