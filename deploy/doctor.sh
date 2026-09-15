#!/bin/bash
# ============================================================
# doctor.sh — 部署体检（内外网差异的自动化检查）
# ============================================================
# 用法:
#   bash deploy/doctor.sh              只检查，不改动任何东西
#   bash deploy/doctor.sh --deep       依赖检查改为真实 import（慢，更准）
#   bash deploy/doctor.sh --fix        修复可再生项（重建共享区软链）
#
# 退出码: 0 = 无错误（可能有警告）；1 = 有错误

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

FIX=false
DEEP=false
for arg in "$@"; do
    case "$arg" in
        --fix)     FIX=true ;;
        --deep)    DEEP=true ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "未知参数: $arg" >&2; exit 2 ;;
    esac
done

ERRORS=0
WARNINGS=0

ok()   { echo "  ✅ $*"; }
bad()  { echo "  ❌ $*"; ERRORS=$((ERRORS + 1)); }
warn() { echo "  ⚠️  $*"; WARNINGS=$((WARNINGS + 1)); }
head2() { echo; echo "── $* ──"; }

# ---- 加载部署配置（PROJECTS_ROOT / 端口 / 运行时等）----
# shellcheck source=deploy/lib.sh
source "$SCRIPT_DIR/lib.sh"
deploy_load "$PROJECT_ROOT"

echo "🩺 财务数据分析平台 · 部署体检"
echo "   主题: $PROFILE_NAME（$PROFILE）  仓库: $PROJECT_ROOT"

# ═══════════════════════════════════════════════════════════
# 1. 路径
# ═══════════════════════════════════════════════════════════
head2 "路径"

path_exists() {  # path_exists <路径> <说明>
    if [ -d "$1" ]; then ok "$2: $1"; else bad "$2 不存在: $1"; fi
    return 0
}

path_exists "$PROJECTS_ROOT"                "PROJECTS_ROOT"
path_exists "$LOG_DIR"                      "日志目录"
[ "$ENABLE_SIONTILES" = "true" ] && path_exists "$SIONTILES_DIR" "SIONTILES_DIR"

# 坚果云共享区：两台机器路径一致，但内网只同步了部分子目录
NUTSTORE_ROOT="${NUTSTORE_ROOT:-/home/song/NutstoreFiles}"
for sub in "2-Code" "8-MyData"; do
    if [ -d "$NUTSTORE_ROOT/$sub" ]; then
        ok "共享区 $NUTSTORE_ROOT/$sub"
    else
        bad "共享区缺目录: $NUTSTORE_ROOT/$sub"
    fi
done

# 仓库内需要可写的目录
for d in "data/warehouse" "data/01_raw" "generated_reports"; do
    if [ ! -d "$PROJECT_ROOT/$d" ]; then
        warn "目录不存在（首次运行可能正常）: $d"
    elif [ ! -w "$PROJECT_ROOT/$d" ]; then
        bad "目录不可写: $d"
    else
        ok "可写: $d"
    fi
done

# ═══════════════════════════════════════════════════════════
# 2. 共享区软链（可再生）
# ═══════════════════════════════════════════════════════════
head2 "共享区软链"

link_state() {  # link_state <链接> <期望目标>
    local name="$1" expect="$2"
    if [ ! -e "$name" ] && [ ! -L "$name" ]; then
        warn "$name 不存在（可 bash scripts/link_shared.sh 重建）"
    elif [ ! -e "$name" ]; then
        bad "$name 断链 -> $(readlink "$name")"
    elif [ "$(readlink "$name")" != "$expect" ]; then
        warn "$name 指向 $(readlink "$name")（期望 $expect）"
    else
        ok "$name"
    fi
    return 0
}

link_state "standards"                 "$NUTSTORE_ROOT/8-MyData/Standards"
link_state "map_utils"                 "$NUTSTORE_ROOT/2-Code/1-MyPython/pybox/map_utils"
link_state "generated_reports/data"    "../data/01_raw/2026年司库账户数据"

if [ -L "Standards" ]; then
    warn "存在大写 Standards 软链，与 standards 重复（大小写在 Linux 上是两个名字）"
fi

if $FIX; then
    echo
    bash "$PROJECT_ROOT/scripts/link_shared.sh" || ERRORS=$((ERRORS + 1))
fi

# ═══════════════════════════════════════════════════════════
# 3. 运行时
# ═══════════════════════════════════════════════════════════
head2 "运行时"

if deploy_check_runtime; then
    ok "运行时: ${RUN_CMD[*]}"
else
    bad "运行时不可用: ${RUN_CMD[*]}"
fi

if [ -n "$MAMBA_ROOT_PREFIX" ] && [ -d "$MAMBA_ROOT_PREFIX/envs" ]; then
    for e in "$CONDA_ENV" quarto; do
        [ -z "$e" ] && continue
        if [ -d "$MAMBA_ROOT_PREFIX/envs/$e" ]; then
            ok "环境存在: $e"
        else
            warn "环境不存在: $e（相关功能会失败）"
        fi
    done
fi

# ═══════════════════════════════════════════════════════════
# 4. 依赖完整性（按服务声明，见 deploy/requirements/）
# ═══════════════════════════════════════════════════════════
head2 "依赖完整性$( $DEEP && echo '（deep）')"

declare -A ENV_MODS=() ENV_BINS=()
declare -a SEEN_ENVS=()
for f in "$SCRIPT_DIR"/requirements/*.txt; do
    [ -r "$f" ] || continue
    e="$(sed -n 's/^# *env: *//p' "$f" | head -1)"
    e="${e:-${CONDA_ENV:-myetl}}"
    case " ${SEEN_ENVS[*]:-} " in *" $e "*) ;; *) SEEN_ENVS+=("$e") ;; esac
    while IFS= read -r line; do
        case "$line" in ''|'#'*) continue ;; esac
        case "$line" in
            bin:*) ENV_BINS[$e]="${ENV_BINS[$e]:-} ${line#bin:}" ;;
            *)     ENV_MODS[$e]="${ENV_MODS[$e]:-} $line" ;;
        esac
    done < "$f"
done

CHECKER='
import importlib, importlib.util, shutil, sys
args = sys.argv[1:]
if "--" in args:
    i = args.index("--"); mods, bins = args[:i], args[i+1:]
else:
    mods, bins = args, []
deep = "--deep" in mods
mods = [m for m in mods if m != "--deep"]
for m in mods:
    try:
        if deep:
            importlib.import_module(m)
        else:
            if importlib.util.find_spec(m) is None:
                raise ImportError("not found")
    except Exception as ex:
        print("MISSING_MOD|%s|%s" % (m, type(ex).__name__))
for b in bins:
    if shutil.which(b) is None:
        print("MISSING_BIN|%s|" % b)
'

for e in "${SEEN_ENVS[@]}"; do
    mods="${ENV_MODS[$e]:-}"
    bins="${ENV_BINS[$e]:-}"
    if [ -z "${mods// /}" ] && [ -z "${bins// /}" ]; then continue; fi

    # 每个环境只起一个 python 子进程（一次 micromamba run 约 0.3~1 秒，
    # 逐个模块起进程会慢到不可用）
    if [ "$e" = "${CONDA_ENV:-}" ]; then
        run_cmd=("${RUN_CMD[@]}")
    else
        run_cmd=("$MICROMAMBA_BIN" run -n "$e")
    fi

    extra=""
    $DEEP && extra="--deep"
    # shellcheck disable=SC2086
    out="$("${run_cmd[@]}" python -c "$CHECKER" $extra $mods -- $bins 2>/dev/null)"
    if [ -z "$out" ]; then
        ok "环境 $e：依赖齐全（$(echo $mods | wc -w) 个模块 / $(echo $bins | wc -w) 个命令）"
    else
        while IFS='|' read -r kind name detail; do
            case "$kind" in
                MISSING_MOD) bad "环境 $e 缺模块: $name" ;;
                MISSING_BIN) bad "环境 $e 缺命令: $name" ;;
            esac
        done <<< "$out"
    fi
done

# ═══════════════════════════════════════════════════════════
# 5. 端口
# ═══════════════════════════════════════════════════════════
head2 "端口（占用不算错误，仅提示）"

while IFS=: read -r name port; do
    pids="$(deploy_port_pids "$port" | tr '\n' ' ' | sed 's/ *$//')"
    if [ -z "$pids" ]; then
        ok "$name $port 空闲"
    else
        cmd="$(ps -o comm= -p "${pids%% *}" 2>/dev/null || echo '?')"
        warn "$name $port 已被占用（PID $pids, $cmd）"
    fi
done < <(deploy_services)

# ═══════════════════════════════════════════════════════════
# 6. 凭据与敏感值
# ═══════════════════════════════════════════════════════════
head2 "本机凭据"

LOCAL_ENV="$SCRIPT_DIR/local.env"
if [ ! -f "$LOCAL_ENV" ]; then
    bad "缺少 $LOCAL_ENV（从 deploy/local.env.example 复制）"
else
    perm="$(stat -c '%a' "$LOCAL_ENV")"
    if [ "$perm" = "600" ]; then ok "deploy/local.env 权限 600"; else
        bad "deploy/local.env 权限是 $perm，应为 600"
        $FIX && chmod 600 "$LOCAL_ENV" && ok "已修正为 600"
    fi
    for key in AMAP_API_KEY_S; do
        if grep -q "^${key}=" "$LOCAL_ENV" 2>/dev/null; then ok "键存在: $key"; else
            bad "缺少键: $key"
        fi
    done
fi

if git -C "$PROJECT_ROOT" ls-files --error-unmatch deploy/local.env >/dev/null 2>&1; then
    bad "deploy/local.env 被版本控制跟踪了，应立即 git rm --cached"
else
    ok "deploy/local.env 未入库"
fi

# ═══════════════════════════════════════════════════════════
# 7. 外部配置里的路径（跨机器最容易漏的地方）
# ═══════════════════════════════════════════════════════════
head2 "外部配置路径"

for cfg in "$PROJECTS_ROOT/filepulse/config_treasury.toml" \
           "$PROJECTS_ROOT/filepulse/config_modelmanual_workbook.toml"; do
    [ -f "$cfg" ] || continue
    echo "  检查 $cfg"
    while IFS= read -r p; do
        [ -z "$p" ] && continue
        # 运行时临时目录（如 filepulse 的解压目录）不要求预先存在
        case "$p" in /tmp/*|/var/tmp/*) echo "  ℹ️     运行时临时路径，跳过: $p"; continue ;; esac
        if [ -e "$p" ]; then
            ok "    $p"
        else
            bad "    路径不存在: $p"
        fi
    done < <(grep -oE '"/[^"]+"' "$cfg" 2>/dev/null | tr -d '"' | sort -u)
done

[ -f "$PROJECTS_ROOT/filepulse/config_treasury.toml" ] || \
    warn "未找到 filepulse 配置（该机可能不跑 filepulse）"

# ═══════════════════════════════════════════════════════════
# 7b. 应存在的目录（缺失可由 --fix 自动创建）
# ═══════════════════════════════════════════════════════════
head2 "应存在的目录"

AUTOCREATE="$SCRIPT_DIR/autocreate-dirs.txt"
if [ -r "$AUTOCREATE" ]; then
    while IFS= read -r d; do
        case "$d" in ''|'#'*) continue ;; esac
        if [ -d "$d" ]; then
            ok "$d"
        elif $FIX; then
            if mkdir -p "$d" 2>/dev/null; then
                ok "已创建 $d"
            else
                bad "创建失败: $d"
            fi
        else
            warn "缺失（--fix 可自动创建）: $d"
        fi
    done < "$AUTOCREATE"
fi

# ═══════════════════════════════════════════════════════════
# 8. LaTeX（日报 PDF）
# ═══════════════════════════════════════════════════════════
head2 "LaTeX（日报 PDF 渲染）"

# 注意：不自动安装。内网直连 github.com/.../tinytex-releases 会被拦截
# （脚本硬编码该地址且不支持镜像），所以 TinyTeX 由人工安装，
# 这里只负责检测并给出提示词。
find_xelatex() {
    local c
    for c in \
        "$(command -v xelatex 2>/dev/null)" \
        "$(ls -d "$TINYTEX_DIR"/bin/*/xelatex 2>/dev/null | head -1)" \
        "$(ls -d "$HOME"/.TinyTeX/bin/*/xelatex 2>/dev/null | head -1)" \
        "$(ls -d /usr/local/texlive/*/bin/*/xelatex 2>/dev/null | head -1)"; do
        if [ -n "$c" ] && [ -x "$c" ]; then printf '%s' "$c"; return 0; fi
    done
    c="$("$MICROMAMBA_BIN" run -n quarto bash -c 'command -v xelatex' 2>/dev/null)"
    if [ -n "$c" ] && [ -x "$c" ]; then printf '%s' "$c"; return 0; fi
    return 1
}

tinytex_hint() {
    cat <<'EOF'
      ⚠️  未检测到 TinyTeX / xelatex → 日报可以出 docx，但无法渲染 PDF

          请通过安装 R 语言然后
              install.packages('tinytex')
              tinytex::install_tinytex()

          说明：内网直连 github.com/rstudio/tinytex-releases 会被拦截，
          且官方安装脚本将下载地址硬编码、不支持配置镜像，
          因此这一步由人工在有网环境（或代理下）完成。
          装好后若不在默认位置，请在 deploy/local.env 指定实际目录：
              TINYTEX_DIR=/实际/路径/.TinyTeX
          装完若缺中文公文类宏包，可按 deploy/texlive-packages.txt 补：
              tlmgr install $(grep -v '^#' deploy/texlive-packages.txt | grep -v '^$' | tr '\n' ' ')
EOF
}

if xl="$(find_xelatex)"; then
    ok "xelatex 可用: $xl"
    ok "TINYTEX_DIR = $TINYTEX_DIR"
else
    tinytex_hint
    warn "TinyTeX 未安装或当前用户不可见（TINYTEX_DIR=$TINYTEX_DIR；只影响日报 PDF）"
fi

# ═══════════════════════════════════════════════════════════
echo
echo "════════════════════════════════════════"
if [ "$ERRORS" -eq 0 ]; then
    echo "  体检通过（警告 $WARNINGS 项）"
else
    echo "  发现 $ERRORS 个错误、$WARNINGS 个警告"
fi
echo "════════════════════════════════════════"
[ "$ERRORS" -eq 0 ] || exit 1
