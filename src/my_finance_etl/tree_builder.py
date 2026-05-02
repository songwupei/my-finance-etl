import pandas as pd
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
    parsed_base_info: pd.DataFrame,
    dim_unit_report: pd.DataFrame,
    parameters: Dict,
) -> pd.DataFrame:
    """
    从封面代码和报送实例维度表构建组织树
    """
    root_code = parameters["organization"]["root_code"]
    logger = logging.getLogger(__name__)

    # 构建所有node_id集合
    all_node_ids = set()
    for _, row in dim_unit_report.iterrows():
        node_id = f"{row['code']}_{row['suffix']}"
        all_node_ids.add(node_id)

    records = []
    for _, row in parsed_base_info.iterrows():
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

        # 在 dim_unit_report 中查找 entity_report_id
        entity_match = dim_unit_report[
            (dim_unit_report["code"] == unit_code) &
            (dim_unit_report["suffix"] == suffix)
        ]
        if entity_match.empty:
            logger.warning(f"节点 {node_id} 未在 dim_unit_report 中找到，跳过")
            logger.debug(f"查询条件: code={unit_code}, suffix={suffix}")
            logger.debug(f"dim_unit_report中唯一code值: {dim_unit_report['code'].unique()}")
            logger.debug(f"dim_unit_report中唯一suffix值: {dim_unit_report['suffix'].unique()}")
            continue

        entity_id = entity_match.iloc[0]["entity_report_id"]
        unit_name = entity_match.iloc[0]["unit_name"]  # 原始值，含口径括号

        # 跳过unit_name为空的记录
        if pd.isna(unit_name) or not unit_name:
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

    tree_df = pd.DataFrame(records)
    return tree_df