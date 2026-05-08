import polars as pl
import logging
from typing import Dict, Set


def find_parent_node_id(parent_code: str, all_node_ids: Set[str]) -> str:
    """根据parent_code查找合适的父节点ID"""
    if not parent_code:
        return "#"

    # 优先尝试suffix=9
    candidate_9 = f"{parent_code}_9"
    if candidate_9 in all_node_ids:
        return candidate_9

    # 查找该parent_code存在的其他suffix
    for node_id in all_node_ids:
        if node_id.startswith(f"{parent_code}_"):
            return node_id

    return "#"


def build_organization_tree(
    parsed_base_info: pl.DataFrame,
    dim_unit_report: pl.DataFrame,
    parameters: Dict,
) -> pl.DataFrame:
    """
    从封面代码和报送实例维度表构建组织树
    """
    root_code = parameters["organization"]["root_code"]
    logger = logging.getLogger(__name__)

    # 预收集所有有效 node_id（仅包含 parsed_base_info 中实际存在的节点）
    all_node_ids = set()
    for row in parsed_base_info.iter_rows(named=True):
        uc = row.get("code")
        sf = row.get("suffix")
        if uc and sf:
            all_node_ids.add(f"{uc}_{sf}")

    records = []
    for row in parsed_base_info.iter_rows(named=True):
        unit_code = row.get("code")  # parsed_base_info中实际列名是"code"不是"unit_code"
        parent_code = row.get("parent_code")
        suffix = row.get("suffix")  # 实际列名是"suffix"不是"reported_caliber_code"
        period = row.get("period")

        if not unit_code or not suffix:
            logger.debug(f"跳过空unit_code或suffix的行: unit_code={unit_code}, suffix={suffix}")
            continue

        # 生成本节点ID和父节点ID
        node_id = f"{unit_code}_{suffix}"
        parent_id = find_parent_node_id(parent_code, all_node_ids)
        # 自引用检测：父节点即自己 → 挂 root
        if parent_id == node_id:
            parent_id = "#"

        # 在 dim_unit_report 中查找 entity_report_id
        entity_match = dim_unit_report.filter(
            (pl.col("code") == unit_code) & (pl.col("suffix") == suffix)
        )
        if entity_match.is_empty():
            logger.warning(f"节点 {node_id} 未在 dim_unit_report 中找到，跳过")
            logger.debug(f"查询条件: code={unit_code}, suffix={suffix}")
            logger.debug(f"dim_unit_report中唯一code值: {dim_unit_report['code'].unique().to_list()}")
            logger.debug(f"dim_unit_report中唯一suffix值: {dim_unit_report['suffix'].unique().to_list()}")
            continue

        entity_id = entity_match.row(0, named=True)["entity_report_id"]
        unit_name = entity_match.row(0, named=True)["unit_name"]  # 原始值，含口径括号

        # 跳过unit_name为空的记录
        if unit_name is None or not unit_name:
            logger.warning(f"节点 {node_id} 的 unit_name 为空，跳过")
            continue

        # 根节点处理：如果parent_code是None或者找不到合适的父节点，设置为#
        if unit_code == root_code and suffix == "9":
            parent_id = "#"

        records.append({
            "node_id": node_id,
            "parent_id": parent_id,
            "node_name": f"{unit_name}_{suffix} ({unit_code})",
            "unit_code": unit_code,
            "suffix": suffix,
            "period": period,
            "entity_report_id": entity_id,
        })

    tree_df = pl.DataFrame(records)

    # 后处理：修正树根 — 自引用/失踪父节点挂 #，根节点后缀统一为 _9
    node_ids_set = set(tree_df["node_id"].to_list())
    rename_map = {}  # old_node_id → new_node_id
    fixed_parents = []
    fixed_node_ids = []
    fixed_node_names = []
    for row in tree_df.iter_rows(named=True):
        pid = row["parent_id"]
        nid = row["node_id"]
        if pid == nid or pid not in node_ids_set:
            pid = "#"
        # 根节点如果是 _1 且无对应 _9 → 改名 _9 (合并口径)
        if pid == "#" and nid.endswith("_1"):
            code = row["unit_code"]
            nid_9 = f"{code}_9"
            if nid_9 not in node_ids_set:
                rename_map[nid] = nid_9
                row["node_name"] = row["node_name"].replace("_1 (", "_9 (")
                nid = nid_9
        fixed_parents.append(pid)
        fixed_node_ids.append(nid)
        fixed_node_names.append(row["node_name"])
    # 同步更新子节点的 parent_id 引用
    if rename_map:
        fixed_parents = [rename_map.get(p, p) for p in fixed_parents]
    tree_df = tree_df.with_columns([
        pl.Series("parent_id", fixed_parents),
        pl.Series("node_id", fixed_node_ids),
        pl.Series("node_name", fixed_node_names),
    ])

    return tree_df