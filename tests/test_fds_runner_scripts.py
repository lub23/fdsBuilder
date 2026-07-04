import os
import shutil
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_ONE = ROOT / "run_one_fds.sh"
RUN_BATCH = ROOT / "run_fds_batch.sh"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def _fake_fds_root(tmp_path: Path) -> Path:
    fds_root = tmp_path / "fake_fds"
    bin_dir = fds_root / "bin"
    bin_dir.mkdir(parents=True)

    _write_executable(
        bin_dir / "FDS6VARS.sh",
        f"""
        export PATH="{bin_dir}:$PATH"
        """,
    )
    _write_executable(
        bin_dir / "mpirun",
        """
        #!/bin/bash
        if [ "${1:-}" = "-n" ]; then
            shift 2
        fi
        exec "$@"
        """,
    )
    _write_executable(
        bin_dir / "fake_fds",
        r"""
        #!/bin/bash
        set -u
        fds_file="$1"
        chid=$(sed -n "s/.*CHID='\([^']*\)'.*/\1/p" "$fds_file" | head -n 1)
        if [ -z "$chid" ]; then
            chid=$(basename "$fds_file" .fds)
        fi

        for stop_file in ./*.stop; do
            [ -e "$stop_file" ] || continue
            echo "ERROR(109): Remove the file, $(basename "$stop_file"), from the current directory (CHID: $chid)"
            exit 109
        done

        if [ "${FAKE_FDS_MODE:-ok}" = "no_burn" ]; then
            cat > "${chid}_hrr.csv" <<EOF
Time,HRR
s,kW
0,0
1,0
EOF
            for _ in $(seq 1 80); do
                [ -f "${chid}.stop" ] && exit 0
                sleep 0.05
            done
            exit 12
        fi

        exit 0
        """,
    )
    return fds_root


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(extra or {})
    return env


def test_run_one_removes_stale_stop_files_before_launch(tmp_path: Path):
    fds_root = _fake_fds_root(tmp_path)
    fds_file = tmp_path / "case_a.fds"
    fds_file.write_text("&HEAD CHID='custom_chid', TITLE='test' /\n", encoding="utf-8")

    case_dir = tmp_path / "case_a"
    case_dir.mkdir()
    (case_dir / "custom_chid.stop").write_text("", encoding="utf-8")
    (case_dir / "old_run.stop").write_text("", encoding="utf-8")

    result = subprocess.run(
        [str(RUN_ONE), str(fds_file), "1", str(fds_root), "fake_fds"],
        cwd=tmp_path,
        env=_env({"HRR_MONITOR": "0"}),
        text=True,
        capture_output=True,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "FDS stop cleanup: removed stale .stop file(s) before launch." in output
    assert not list(case_dir.glob("*.stop"))


def test_batch_logs_no_combustion_early_stop_as_third_status(tmp_path: Path):
    fds_root = _fake_fds_root(tmp_path)
    shutil.copy2(RUN_ONE, tmp_path / "run_one_fds.sh")
    shutil.copy2(RUN_BATCH, tmp_path / "run_fds_batch.sh")
    (tmp_path / "run_one_fds.sh").chmod(0o755)
    (tmp_path / "run_fds_batch.sh").chmod(0o755)

    fds_file = tmp_path / "no_burn_case.fds"
    fds_file.write_text("&HEAD CHID='no_burn_chid', TITLE='test' /\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", "./run_fds_batch.sh", "1", "1", "fake_fds"],
        cwd=tmp_path,
        env=_env(
            {
                "FDS_ROOT": str(fds_root),
                "FAKE_FDS_MODE": "no_burn",
                "HRR_MONITOR_WINDOW": "1",
                "HRR_MONITOR_INTERVAL": "1",
                "HRR_STOP_GRACE": "3",
            }
        ),
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    summary = (tmp_path / "batch_summary.log").read_text(encoding="utf-8")
    worker_log = (tmp_path / "._fds_batch_logs" / "worker_1.log").read_text(encoding="utf-8")
    assert "<<< 未燃提前终止: ./no_burn_case.fds" in summary
    assert "成功: 0  未燃提前终止: 1  失败: 0" in summary
    assert "HRR_RESULT=NO_COMBUSTION_EARLY_STOP" in worker_log
    assert not fds_file.exists()
    assert not list((tmp_path / "no_burn_case").glob("*.stop"))
