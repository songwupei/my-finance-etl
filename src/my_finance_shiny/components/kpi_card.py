"""KPI card component."""
from shiny import ui


def kpi_card(title: str, metrics: dict[str, str]) -> ui.Tag:
    """Render a card with KPI metrics table.

    Args:
        title: Card title.
        metrics: Dict of label -> value strings.
    """
    rows = "".join(
        f"| {label} | **{value}** |\n"
        for label, value in metrics.items()
    )
    return ui.card(
        ui.card_header(title),
        ui.markdown(
            f"""
| 指标 | 数值 |
|------|------|
{rows}
"""
        ),
    )
