"""企业地图 — SionTiles/MapLibre iframe 嵌入（全屏）。"""

from shiny import ui


def page():
    return ui.tags.iframe(
        src="http://localhost:8765",
        style="width: 100%; height: calc(100vh - 58px); border: none;",
    )
