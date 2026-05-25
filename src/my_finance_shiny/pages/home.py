"""首页 — markdown welcome card."""
from shiny import ui


def home_ui():
    return ui.card(
        ui.card_header("HOME"),
        ui.markdown("""
        # 财务数据 ETL 仪表板

        欢迎使用财务数据分析平台。

        - **穿透监控**：资产负债结构气泡图、杠杆率 vs 账户规模
        - **地理分布**：成员单位全国地图分布
        - **关系分析**：关联关系分析
        - **概览**：数据概览
        """),
    )
