#!/bin/bash
# run_one_fds.sh - 跑单个 fds 案例
# 用法: ./run_one_fds.sh <fds文件路径> <NP> <FDS_ROOT> <FDS_BIN>
# 不应直接调用,统一由 run_fds_batch.sh 调度

set -u

FDS_FILE="$1"
NP="$2"
FDS_ROOT="$3"
FDS_BIN="$4"

if [ -z "$FDS_FILE" ] || [ ! -f "$FDS_FILE" ]; then
    echo "[ERROR] FDS file not found: $FDS_FILE" >&2
    exit 2
fi

# source FDS6VARS.sh 官方 env:设 PATH / LD_LIBRARY_PATH / INTEL MPI
FDS_VARS="$FDS_ROOT/bin/FDS6VARS.sh"
if [ -f "$FDS_VARS" ]; then
    source "$FDS_VARS"
else
    echo "[WARN] $FDS_VARS 不存在,手动设置 PATH" >&2
    export PATH="$FDS_ROOT/bin:$FDS_ROOT/bin/INTEL/bin:$PATH"
    export LD_LIBRARY_PATH="$FDS_ROOT/bin/INTEL/lib:${LD_LIBRARY_PATH:-}"
fi

# 关掉 OpenMP 默认线程数,避免和 MPI 进程抢 CPU
export OMP_NUM_THREADS=1

HRR_MONITOR="${HRR_MONITOR:-1}"
HRR_MONITOR_WINDOW="${HRR_MONITOR_WINDOW:-120}"
HRR_MONITOR_INTERVAL="${HRR_MONITOR_INTERVAL:-5}"
HRR_MONITOR_THRESHOLD="${HRR_MONITOR_THRESHOLD:-1e-6}"
HRR_STOP_GRACE="${HRR_STOP_GRACE:-60}"
NO_COMBUSTION_RC="${NO_COMBUSTION_RC:-10}"

hrr_status() {
    local csv_file="$1"
    awk -F, -v window="$HRR_MONITOR_WINDOW" -v eps="$HRR_MONITOR_THRESHOLD" '
        NR <= 2 { next }
        {
            gsub(/^[ \t]+|[ \t]+$/, "", $1)
            gsub(/^[ \t]+|[ \t]+$/, "", $2)
            if ($1 == "" || $2 == "") next
            t = $1 + 0
            h = $2 + 0
            rows += 1
            if (t > last_time) last_time = t
            if (t <= window && (h > eps || h < -eps)) changed = 1
        }
        END {
            if (rows == 0) exit 2
            printf "%.6f %d\n", last_time, changed ? 1 : 0
        }
    ' "$csv_file"
}

time_reached_window() {
    local last_time="$1"
    awk -v t="$last_time" -v w="$HRR_MONITOR_WINDOW" 'BEGIN { exit !((t + 0) >= (w + 0)) }'
}

cleanup_stop_files() {
    local phase="$1"
    local removed=0
    local f
    for f in ./*.stop; do
        [ -e "$f" ] || continue
        rm -f -- "$f"
        removed=1
    done
    if [ "$removed" -eq 1 ]; then
        echo "FDS stop cleanup: removed stale .stop file(s) ${phase}."
    fi
}

# CHID = 原 .fds 文件名(去扩展名),与原 work.slurm 同约定
CASE_NAME=$(basename "$FDS_FILE" .fds)
echo "Running case: $CASE_NAME  (MPI np=$NP, bin=$FDS_BIN)"

mkdir -p "$CASE_NAME"
cp "$FDS_FILE" "$CASE_NAME/"
cd "$CASE_NAME" || exit 3

OUTPUT_CHID=$(sed -n "s/.*CHID[[:space:]]*=[[:space:]]*'\([^']*\)'.*/\1/p" "$CASE_NAME.fds" | head -n 1)
if [ -z "$OUTPUT_CHID" ]; then
    OUTPUT_CHID=$(sed -n 's/.*CHID[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$CASE_NAME.fds" | head -n 1)
fi
if [ -z "$OUTPUT_CHID" ]; then
    OUTPUT_CHID="$CASE_NAME"
fi
if [ "$OUTPUT_CHID" != "$CASE_NAME" ]; then
    echo "FDS output CHID: $OUTPUT_CHID"
fi

HRR_CSV="${OUTPUT_CHID}_hrr.csv"
STOP_FILE="${OUTPUT_CHID}.stop"
cleanup_stop_files "before launch"

mpirun -n "$NP" "$FDS_BIN" "$CASE_NAME.fds" &
FDS_PID=$!
EARLY_STOP=0
COMBUSTION_SEEN=0

cleanup_case() {
    if kill -0 "$FDS_PID" 2>/dev/null; then
        touch "$STOP_FILE" 2>/dev/null || true
        kill -TERM "$FDS_PID" 2>/dev/null || true
    fi
}
trap cleanup_case INT TERM

if [ "$HRR_MONITOR" != "0" ]; then
    echo "HRR monitor: ${HRR_CSV}, window=${HRR_MONITOR_WINDOW}s, threshold=${HRR_MONITOR_THRESHOLD}"
    while kill -0 "$FDS_PID" 2>/dev/null; do
        if [ -f "$HRR_CSV" ]; then
            status=$(hrr_status "$HRR_CSV" 2>/dev/null || true)
            if [ -n "$status" ]; then
                last_time=${status% *}
                changed=${status#* }
                if [ "$changed" = "1" ]; then
                    COMBUSTION_SEEN=1
                    echo "HRR monitor: HRR changed within ${HRR_MONITOR_WINDOW}s; continue full run."
                    break
                fi
                if time_reached_window "$last_time"; then
                    EARLY_STOP=1
                    echo "HRR monitor: HRR stayed zero through ${last_time}s; requesting graceful FDS stop."
                    touch "$STOP_FILE"
                    break
                fi
            fi
        fi
        sleep "$HRR_MONITOR_INTERVAL"
    done
fi

if [ "$EARLY_STOP" -eq 1 ]; then
    waited=0
    while kill -0 "$FDS_PID" 2>/dev/null && [ "$waited" -lt "$HRR_STOP_GRACE" ]; do
        sleep "$HRR_MONITOR_INTERVAL"
        waited=$((waited + HRR_MONITOR_INTERVAL))
    done
    if kill -0 "$FDS_PID" 2>/dev/null; then
        echo "HRR monitor: FDS did not stop after ${HRR_STOP_GRACE}s; terminating mpirun."
        kill -TERM "$FDS_PID" 2>/dev/null || true
        sleep 10
        kill -KILL "$FDS_PID" 2>/dev/null || true
    fi
fi

wait "$FDS_PID"
rc=$?
trap - INT TERM
cleanup_stop_files "after FDS exit"

if [ "$EARLY_STOP" -eq 1 ]; then
    echo "HRR monitor: no combustion detected in the first ${HRR_MONITOR_WINDOW}s; classified as no-combustion early stop."
    echo "HRR_RESULT=NO_COMBUSTION_EARLY_STOP"
    exit "$NO_COMBUSTION_RC"
fi

exit $rc
