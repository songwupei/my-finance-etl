"""穿透监管 — Card links to PanReg HTML reports."""
from shiny import ui


def panreg_ui():
    return ui.TagList(
        ui.card(
            ui.card_header("穿透监管报告"),
            ui.markdown("""
            集团成员单位逃逸账户检测报告。

            [**打开完整报告（新标签页）**](http://localhost:5001/panreg-report)
            """),
        ),
        ui.card(
            ui.card_header("穿透监管报告"),
            ui.markdown("""
            集团成员单位账户数量异常检测报告。

            [**打开完整报告（新标签页）**](http://localhost:5001/panreg-report1)
            """),
        ),
    )
