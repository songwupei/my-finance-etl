"""Fallback card shown when data is empty."""
from shiny import ui


def fallback_card(text: str = "等待数据加载...") -> ui.Tag:
    return ui.card(
        ui.card_header("提示"),
        ui.markdown(f"### {text}"),
    )
