"""穿透监管页面 — Card 链接到 account_PanReg_report.html."""
import vizro.models as vm

_vizro_page_panreg = vm.Page(
    id="panreg",
    title="穿透监管",
    components=[
        vm.Card(text="""
## 穿透监管报告

集团成员单位逃逸账户检测报告。

[**打开完整报告（新标签页）**](/panreg-report)
        """),
        vm.Card(text="""
## 穿透监管报告

集团成员单位账户数量异常检测报告。

[**打开完整报告（新标签页）**](/panreg-report1)
        """),
    ],
)
