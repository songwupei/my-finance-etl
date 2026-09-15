#!/usr/bin/env bash
# ============================================================
# lib.sh — 部署配置加载器与共用函数
# ============================================================
# 由 start.sh / stop.sh / kill.sh / kill_shiny.sh 共同 source。
#
# 加载顺序（同名键后者覆盖前者）：
#   deploy/defaults.env → deploy/profiles/<PROFILE>.env → deploy/local.env
#
# PROFILE 默认按 /etc/os-release 的 ID 自动推导，
# 可用 `--profile <名>` 或环境变量 PROFILE= 覆盖。

# ---- 探测当前系统主题 ----
deploy_detect_profile() {
    local os_id=""
    if [ -r /etc/os-release ]; then
        os_id="$(set +e; . /etc/os-release 2>/dev/null; printf '%s' "${ID:-}")"
    fi
    os_id="$(printf '%s' "$os_id" | tr '[:upper:]' '[:lower:]')"
    case "$os_id" in
        arch*)      printf 'arch' ;;
        openeuler*) printf 'openeuler' ;;
        *)          printf 'default' ;;
    esac
}

# ---- 从 pyproject.toml 读版本，避免标题里的版本号与包版本漂移 ----
deploy_read_version() {
    local pyproject="$1/pyproject.toml"
    [ -r "$pyproject" ] || return 0
    sed -n 's/^version[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "$pyproject" | head -1
}

# ---- 加载配置：脚本里在定义 SCRIPT_DIR 之后立即调用 ----
deploy_load() {
    local root="$1"
    local deploy_dir="$root/deploy"
    local profile_file

    if [ ! -r "$deploy_dir/defaults.env" ]; then
        echo "❌ 缺少配置文件: $deploy_dir/defaults.env" >&2
        exit 1
    fi
    # shellcheck source=/dev/null
    source "$deploy_dir/defaults.env"

    PROFILE="${PROFILE:-$(deploy_detect_profile)}"
    profile_file="$deploy_dir/profiles/${PROFILE}.env"
    if [ -r "$profile_file" ]; then
        # shellcheck source=/dev/null
        source "$profile_file"
    else
        echo "⚠️  未找到系统主题配置 $profile_file，回退到 defaults.env" >&2
    fi

    if [ -r "$deploy_dir/local.env" ]; then
        # shellcheck source=/dev/null
        source "$deploy_dir/local.env"
    fi

    deploy_finalize "$root"
}

# ---- 派生路径、组装运行时命令 ----
deploy_finalize() {
    local root="$1"

    if [ -z "$PROJECTS_ROOT" ]; then
        echo "❌ PROJECTS_ROOT 未配置。" >&2
        echo "   请在 deploy/profiles/${PROFILE}.env 或 deploy/local.env 中设置。" >&2
        exit 1
    fi
    [ -d "$PROJECTS_ROOT" ] || echo "⚠️  PROJECTS_ROOT 不存在: $PROJECTS_ROOT" >&2

    SIONTILES_DIR="${SIONTILES_DIR:-$PROJECTS_ROOT/SionTiles/web}"
    LOG_DIR="${LOG_DIR:-$root/logs}"
    APP_VERSION="$(deploy_read_version "$root")"

    # 运行时前缀：默认 micromamba run -n <环境名>；
    # RUNTIME_CMD 非空则完全接管（venv / conda 等场景）。
    if [ -n "$RUNTIME_CMD" ]; then
        read -r -a RUN_CMD <<< "$RUNTIME_CMD"
    else
        if [ -z "$MICROMAMBA_BIN" ]; then
            MICROMAMBA_BIN="$(command -v micromamba 2>/dev/null || true)"
        fi
        if [ -n "$CONDA_ENV" ]; then
            RUN_CMD=("$MICROMAMBA_BIN" run -n "$CONDA_ENV")
        else
            # CONDA_ENV 留空：沿用调用者当前激活的环境
            RUN_CMD=("$MICROMAMBA_BIN" run)
        fi
    fi

    # 端口清理工具：本机装了什么用什么
    if [ "$KILL_TOOL" = "auto" ]; then
        if command -v lsof >/dev/null 2>&1; then
            KILL_TOOL="lsof"
        elif command -v fuser >/dev/null 2>&1; then
            KILL_TOOL="fuser"
        else
            KILL_TOOL=""
        fi
    fi

    # 一并传给子进程，Python 侧后续可复用同一份路径定义
    export PROJECTS_ROOT BIND_HOST
    export SIONTILES_PORT SHINY_PORT VIZRO_PORT
}

# ---- 校验运行时可用 ----
deploy_check_runtime() {
    local bin="${RUN_CMD[0]}"
    if [ -z "$bin" ] || { [ ! -x "$bin" ] && ! command -v "$bin" >/dev/null 2>&1; }; then
        echo "❌ 找不到运行时: ${RUN_CMD[*]}" >&2
        echo "   当前主题: $PROFILE_NAME（$PROFILE）" >&2
        echo "   请检查 deploy/profiles/${PROFILE}.env 的" >&2
        echo "   MICROMAMBA_BIN / CONDA_ENV / RUNTIME_CMD。" >&2
        return 1
    fi
    if [ -n "$MAMBA_ROOT_PREFIX" ]; then
        export MAMBA_ROOT_PREFIX
    fi
    return 0
}

# ---- 查监听某端口的进程号 ----
deploy_port_pids() {
    local port="$1"
    case "$KILL_TOOL" in
        lsof)  lsof -i :"$port" -t 2>/dev/null ;;
        fuser) fuser -n tcp "$port" 2>/dev/null ;;
    esac
    return 0
}

# ---- 按端口清理进程；没有进程时返回 1 ----
deploy_kill_port() {
    local port="$1" name="$2" pids
    pids="$(deploy_port_pids "$port" | tr '\n' ' ' | sed 's/ *$//')"
    if [ -z "$pids" ]; then
        return 1
    fi
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    echo "   ✅ $name (port $port) 已清理 (PID: $pids)"
    return 0
}

# ---- 供 stop.sh 遍历的服务清单 ----
deploy_services() {
    printf 'SionTiles:%s\n' "$SIONTILES_PORT"
    printf 'Vizro:%s\n' "$VIZRO_PORT"
    printf 'Shiny:%s\n' "$SHINY_PORT"
}
