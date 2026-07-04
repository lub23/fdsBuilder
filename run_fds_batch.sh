#!/bin/bash
set -u

MAX_JOBS="${1:-1}"
NP_PER_TASK="${2:-4}"
FDS_BIN="${3:-fds}"
HRR_MONITOR="${HRR_MONITOR:-1}"
HRR_MONITOR_WINDOW="${HRR_MONITOR_WINDOW:-120}"
HRR_MONITOR_INTERVAL="${HRR_MONITOR_INTERVAL:-5}"
HRR_MONITOR_THRESHOLD="${HRR_MONITOR_THRESHOLD:-1e-6}"
HRR_STOP_GRACE="${HRR_STOP_GRACE:-60}"
NO_COMBUSTION_RC="${NO_COMBUSTION_RC:-10}"

FDS_ROOT="${FDS_ROOT:-/home/blue/FDS/FDS6}"
FDS_BINDIR="$FDS_ROOT/bin"
FDS_VARS="$FDS_BINDIR/FDS6VARS.sh"
FDS_PATTERN="*.fds"
LOG_DIR="._fds_batch_logs"
SUMMARY_LOG="batch_summary.log"

mkdir -p "$LOG_DIR"
> "$SUMMARY_LOG"
TIMESTAMP() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(TIMESTAMP)] ===== FDS Batch Runner =====" | tee -a "$SUMMARY_LOG"
echo "[$(TIMESTAMP)] MAX_JOBS=$MAX_JOBS  NP_PER_TASK=$NP_PER_TASK  FDS_BIN=$FDS_BIN" | tee -a "$SUMMARY_LOG"
echo "[$(TIMESTAMP)] HRR_MONITOR=$HRR_MONITOR  WINDOW=${HRR_MONITOR_WINDOW}s  INTERVAL=${HRR_MONITOR_INTERVAL}s  THRESHOLD=$HRR_MONITOR_THRESHOLD" | tee -a "$SUMMARY_LOG"

if [ ! -d "$FDS_BINDIR" ]; then
    echo "[ERROR] FDS 安装目录不存在: $FDS_BINDIR" >&2
    exit 1
fi
if [ ! -x "$FDS_BINDIR/$FDS_BIN" ]; then
    echo "[ERROR] 没有可执行文件: $FDS_BINDIR/$FDS_BIN" >&2
    echo "[ERROR] 可选项: fds / fds_openmp / fds_impi_intel_linux" >&2
    exit 1
fi

NCPU=$(nproc)
TOTAL_NEED=$((MAX_JOBS * NP_PER_TASK))
if [ "$TOTAL_NEED" -gt "$NCPU" ]; then
    echo "[WARN] 需要 ${TOTAL_NEED} 核,本机只有 ${NCPU} 核,会超载降低速度" | tee -a "$SUMMARY_LOG"
fi

TASK_QUEUE="$LOG_DIR/.task_queue"
TMP_LIST="$LOG_DIR/.fds_list.$$"

# 只取顶层目录的 .fds,排除子目录
find . -maxdepth 1 -type f -name "$FDS_PATTERN" 2>/dev/null | sort > "$TMP_LIST"

TOTAL=$(wc -l < "$TMP_LIST")
if [ "$TOTAL" -eq 0 ]; then
    echo "[ERROR] 当前目录没有 .fds 文件" >&2
    exit 1
fi

echo "[$(TIMESTAMP)] Found $TOTAL fds file(s)" | tee -a "$SUMMARY_LOG"
cat "$TMP_LIST" | tee -a "$SUMMARY_LOG"
mv "$TMP_LIST" "$TASK_QUEUE"

RUNNING_DIR="$LOG_DIR/.running"
mkdir -p "$RUNNING_DIR"

cleanup() {
    echo ""
    echo "[$(TIMESTAMP)] !!! 收到中断信号,清理中... !!!"
    pkill -P $$ 2>/dev/null
    pkill -f "run_one_fds.sh" 2>/dev/null
    pkill -f "$FDS_BIN" 2>/dev/null
    exit 130
}
trap cleanup INT TERM

worker() {
    local worker_id=$1
    local log_file="$LOG_DIR/worker_${worker_id}.log"
    echo "[$(TIMESTAMP)] [worker-$worker_id] 启动" >> "$SUMMARY_LOG"

    while true; do
        local fds_file
        fds_file=$(flock "$TASK_QUEUE.lock" -c "head -n 1 '$TASK_QUEUE' 2>/dev/null && sed -i '1d' '$TASK_QUEUE'" 2>/dev/null | head -n 1)

        if [ -z "$fds_file" ] || [ ! -f "$fds_file" ]; then
            echo "[$(TIMESTAMP)] [worker-$worker_id] 队列空,退出" >> "$SUMMARY_LOG"
            break
        fi

        echo "$fds_file" > "$RUNNING_DIR/worker_${worker_id}"
        echo "[$(TIMESTAMP)] [worker-$worker_id] >>> 启动: $fds_file" | tee -a "$SUMMARY_LOG" "$log_file"
        local start_ts=$(date +%s)

        bash ./run_one_fds.sh "$fds_file" "$NP_PER_TASK" "$FDS_ROOT" "$FDS_BIN" \
            >> "$log_file" 2>&1
        local rc=$?

        local end_ts=$(date +%s)
        local cost=$((end_ts - start_ts))
        local cost_min=$((cost / 60))
        local cost_sec=$((cost % 60))

        local case_dir=$(basename "$fds_file" .fds)
        if [ $rc -eq 0 ]; then
            echo "[$(TIMESTAMP)] [worker-$worker_id] <<< 完成: $fds_file (用时 ${cost_min}m${cost_sec}s)" \
                | tee -a "$SUMMARY_LOG" "$log_file"
            rm -f "$fds_file"
        elif [ "$rc" -eq "$NO_COMBUSTION_RC" ]; then
            echo "[$(TIMESTAMP)] [worker-$worker_id] <<< 未燃提前终止: $fds_file (用时 ${cost_min}m${cost_sec}s)" \
                | tee -a "$SUMMARY_LOG" "$log_file"
            rm -f "$fds_file"
        else
            echo "[$(TIMESTAMP)] [worker-$worker_id] <<< 失败: $fds_file rc=$rc (用时 ${cost_min}m${cost_sec}s)" \
                | tee -a "$SUMMARY_LOG" "$log_file"
        fi

        rm -f "$RUNNING_DIR/worker_${worker_id}"
    done
}

export -f worker
export -f TIMESTAMP
export LOG_DIR SUMMARY_LOG TASK_QUEUE RUNNING_DIR NP_PER_TASK FDS_ROOT FDS_BIN
export HRR_MONITOR HRR_MONITOR_WINDOW HRR_MONITOR_INTERVAL HRR_MONITOR_THRESHOLD HRR_STOP_GRACE NO_COMBUSTION_RC

echo "[$(TIMESTAMP)] 启动 $MAX_JOBS 个并发 worker..." | tee -a "$SUMMARY_LOG"

WORKER_PIDS=()
for i in $(seq 1 "$MAX_JOBS"); do
    worker "$i" &
    WORKER_PIDS+=($!)
done

for pid in "${WORKER_PIDS[@]}"; do
    wait "$pid" 2>/dev/null
done

SUCCESS=$(grep -h "<<< 完成" "$LOG_DIR"/worker_*.log 2>/dev/null | wc -l)
NO_COMBUSTION=$(grep -h "<<< 未燃提前终止" "$LOG_DIR"/worker_*.log 2>/dev/null | wc -l)
FAILED=$(grep -h "<<< 失败" "$LOG_DIR"/worker_*.log 2>/dev/null | wc -l)

echo "[$(TIMESTAMP)] ===== 全部跑完 =====" | tee -a "$SUMMARY_LOG"
echo "[$(TIMESTAMP)] 总计: $TOTAL  成功: $SUCCESS  未燃提前终止: $NO_COMBUSTION  失败: $FAILED" | tee -a "$SUMMARY_LOG"
echo "[$(TIMESTAMP)] 详细日志: $LOG_DIR/" | tee -a "$SUMMARY_LOG"
echo ""
echo "查看汇总: cat $SUMMARY_LOG"
echo "查看失败案例: grep '失败' $LOG_DIR/worker_*.log"
echo "查看未燃提前终止案例: grep '未燃提前终止' $LOG_DIR/worker_*.log"
echo "完成。"
