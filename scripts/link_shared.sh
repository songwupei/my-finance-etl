#!/bin/bash
# ============================================================
# link_shared.sh — 重建指向坚果云共享区的软链
# ============================================================
# 这些软链指向仓库之外，属于「可再生资产」：入库会把某一台机器的
# 路径固化成事实，另一台必断（历史上 Standards / map_utils /
# generated_reports/data 都踩过这个坑）。因此改为按需重建。
#
# 用法: bash scripts/link_shared.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 共享区根目录：两台机器都是这个挂载点，允许用环境变量覆盖
NUTSTORE_ROOT="${NUTSTORE_ROOT:-/home/song/NutstoreFiles}"

failed=0

# link <链接位置> <目标> [目标描述]
link() {
    local name="$1" target="$2" what="${3:-}"
    # 相对目标（如 generated_reports/data -> ../data/...）要按链接所在目录
    # 解析，而不是按当前工作目录
    local base; base="$(dirname "$name")"
    local resolved
    case "$target" in
        /*) resolved="$target" ;;
        *)  resolved="$base/$target" ;;
    esac

    if [ ! -L "$name" ] && [ -e "$name" ]; then
        echo "  ⚠️  $name 已存在且不是软链，跳过（请自行处理）"
        return 0
    fi
    if [ ! -e "$resolved" ]; then
        echo "  ❌ $name 的目标不存在: $target ${what:+(共享区是否已同步？)}"
        failed=1
        return 1
    fi
    if [ -L "$name" ] && [ "$(readlink "$name")" = "$target" ] && [ -e "$name" ]; then
        echo "  ✅ $name 已正确指向 $target"
        return 0
    fi
    ln -sfn "$target" "$name"
    echo "  🔗 $name -> $target"
}

echo "🔧 重建共享区软链（NUTSTORE_ROOT=$NUTSTORE_ROOT）"

# 标准库目录。小写 standards 是仓库自己的引用名
# （conf/base/parameters.yml 的 data_standard.schema_registry_path）
link "standards"        "$NUTSTORE_ROOT/8-MyData/Standards"      "标准库"
# 地图工具库
link "map_utils"        "$NUTSTORE_ROOT/2-Code/1-MyPython/pybox/map_utils" "地图工具"
# 日报渲染用的数据目录：目标在仓库内，用相对链接即与机器无关
if [ ! -d "$PROJECT_ROOT/data/01_raw/2026年司库账户数据" ]; then
    echo "  ⚠️  data/01_raw/2026年司库账户数据 不存在，跳过 generated_reports/data"
else
    link "generated_reports/data" "../data/01_raw/2026年司库账户数据" "日报数据"
fi

# 历史遗留：大写 Standards 与标准库目标重复
if [ -L "Standards" ]; then
    echo "  ℹ️  检测到大写的 Standards 软链，与 standards 重复，可执行 rm Standards 移除"
fi

echo
if [ "$failed" -eq 0 ]; then
    echo "完成。"
else
    echo "部分软链未能建立，请检查坚果云共享区是否已同步。"
    exit 1
fi
