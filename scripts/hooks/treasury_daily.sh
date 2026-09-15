#!/bin/bash
# 司库日报自动化流程
# 由 archive_monitor 在解压处理完成后触发
set -euo pipefail

SEND_ONLY=false
if [[ "${1:-}" == "--send-only" ]]; then
    SEND_ONLY=true
fi

TODAY=$(date +%Y%m%d)

# 本脚本位于 <仓库>/scripts/hooks/，据此定位仓库根，避免写死机器相关路径：
#   外网 /home/song/NutstoreFiles/projects/my-finance-etl
#   内网 /home/songwp/projects/my-finance-etl
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/treasury_daily_${TODAY}.log"
START_TS=$(date +%s)

# ── 步骤状态 — 避免 run_hook 重试时重复执行已完成步骤 ──────
STATE_DIR="/tmp/treasury_daily_state"
mkdir -p "$STATE_DIR"
STATE_FILE="$STATE_DIR/state_${TODAY}"

mark_done() { echo "$1" >> "$STATE_FILE"; }
is_done()  { grep -qxF "$1" "$STATE_FILE" 2>/dev/null; }
clear_state() { rm -f "$STATE_FILE"; }

# ── 工具函数 ─────────────────────────────────────────────────
TOTAL_STEPS=3
bar_width=30
step_names=("Kedro ETL" "Quarto 渲染" "发送邮件")
safe_pipe() { set +e; "$@" 2>&1 | tee -a "$LOG_FILE"; local _r=${PIPESTATUS[0]}; set -e; return $_r; }

bar() {
    local cur=$1
    local pct=$(( cur * 100 / TOTAL_STEPS ))
    local filled=$(( cur * bar_width / TOTAL_STEPS ))
    local empty=$(( bar_width - filled ))
    printf -v bar_filled '%*s' "$filled" ''
    printf -v bar_empty   '%*s' "$empty"   ''
    bar_filled=${bar_filled// /█}
    bar_empty=${bar_empty// /░}
    printf '[%s%s] %d/%d (%d%%)\n' "$bar_filled" "$bar_empty" "$cur" "$TOTAL_STEPS" "$pct"
}

step_header() {
    local step=$1 name=$2
    local elapsed=$(($(date +%s) - START_TS))
    echo ""
    echo "╔══════════════════════════════════════════════════╗"
    printf "║  Step %d/%d: %-28s ║\n" "$step" "$TOTAL_STEPS" "$name"
    printf "║  %-44s ║\n" "$(bar $((step - 1)))"
    printf "║  已耗时: %-36s ║\n" "${elapsed}s"
    echo "╚══════════════════════════════════════════════════╝"
    echo ""
}

step_done() {
    local step=$1 elapsed=$(($(date +%s) - START_TS))
    echo ""
    printf '✓ Step %d/%d 完成  (%ss elapsed)\n' "$step" "$TOTAL_STEPS" "$elapsed"
    echo ""
}

step_skip() {
    local step=$1 name=$2 elapsed=$(($(date +%s) - START_TS))
    echo ""
    printf '⤳ Step %d/%d: %s — 已完成，跳过 (%ss elapsed)\n' "$step" "$TOTAL_STEPS" "$name" "$elapsed"
    echo ""
}

banner() {
    echo ""
    echo "  ╔══════════════════════════════════════╗"
    printf "  ║  司库日报自动化 — %s  ║\n" "$TODAY"
    echo "  ╚══════════════════════════════════════╝"
    echo ""
}

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# ── 开始 ───────────────────────────────────────────────────
banner

# ═══════════════════════════════════════════════════════════
# Step 1/3: Kedro ETL
# ═══════════════════════════════════════════════════════════
if $SEND_ONLY; then
    log "--send-only: 跳过 Kedro ETL"
else
    if is_done "step1"; then
        step_skip 1 "${step_names[0]}"
    else
        step_header 1 "${step_names[0]}"
        log "启动 Kedro pipeline: treasury_data ..."
        if safe_pipe micromamba run -n myetl bash -c "
          cd $PROJECT_ROOT &&
          kedro run --pipeline=treasury_data
        "; then
            mark_done "step1"
            step_done 1
        else
            log "✗ Kedro 失败，终止流程"
            exit 1
        fi
    fi
fi

# ═══════════════════════════════════════════════════════════
# Step 2/3: Quarto 渲染
# ═══════════════════════════════════════════════════════════
if $SEND_ONLY; then
    log "--send-only: 跳过 Quarto 渲染"
else
    if is_done "step2"; then
        step_skip 2 "${step_names[1]}"
    else
        step_header 2 "${step_names[1]}"
        log "渲染 daily_report_account-gb.qmd → PDF ..."
        if safe_pipe micromamba run -n quarto bash -c "
          cd $PROJECT_ROOT/generated_reports &&
          quarto render daily_report_account-gb.qmd
        "; then
            mark_done "step2"
            step_done 2
        else
            log "✗ Quarto 渲染失败，终止流程"
            exit 1
        fi
    fi
fi

# ═══════════════════════════════════════════════════════════
# Step 3/3: 发送邮件
# ═══════════════════════════════════════════════════════════
if is_done "step3"; then
    step_skip 3 "${step_names[2]}"
else
    step_header 3 "${step_names[2]}"
    PDF_PATH="$PROJECT_ROOT/generated_reports/daily_report_account-gb.pdf"
    EMAIL_FROM="${EMAIL_FROM:-songwupei@qq.com}"
    EMAIL_TO="${EMAIL_TO:-songwupei@163.com}"
    EMAIL_SUBJECT="${EMAIL_SUBJECT_PREFIX:-司库日报}${TODAY}"
    BODY="${EMAIL_SUBJECT_PREFIX:-司库日报} — 自动生成于 $(date '+%Y-%m-%d %H:%M')"
    if [ -f "$PDF_PATH" ]; then
        log "发送邮件: ${EMAIL_SUBJECT} → ${EMAIL_TO}"
        micromamba run -n quarto mailops send \
            -t "$EMAIL_TO" \
            -s "$EMAIL_SUBJECT" \
            -b "$BODY" \
            -a "$PDF_PATH" \
            -f "$EMAIL_FROM"
        mark_done "step3"
        step_done 3
    else
        log "✗ PDF 不存在: $PDF_PATH"
        exit 1
    fi
fi

# ── 收尾 ───────────────────────────────────────────────────
clear_state
TOTAL_ELAPSED=$(($(date +%s) - START_TS))
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║          全部完成 ✓                  ║"
printf "  ║  总耗时: %-28s ║\n" "${TOTAL_ELAPSED}s"
echo "  ╚══════════════════════════════════════╝"
echo ""
