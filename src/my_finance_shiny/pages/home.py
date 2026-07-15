"""首页 — KPI 欢迎卡。"""

from shiny import ui


def page():
    """首页 UI。"""
    return ui.card(
        ui.card_header("FinForge"),
        ui.markdown("""
        # FinForge — AI 驱动的财务数据监管平台

        集成大模型智能查询与穿透式监管规则引擎。

        - **🤖 智能查询**：自然语言 → SQL，零代码探索数据
        - **🔍 穿透监控**：资产负债气泡图、杠杆率分析、账户地图
        - **📊 余额统计**：子集团/银行/地理/交叉四维分析
        - **📍 地图可视化**：全国企业分布、银行账户地理分布
        """),
    )
