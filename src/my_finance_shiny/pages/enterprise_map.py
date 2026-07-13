"""企业地图分析 — SionTiles 嵌入式矢量瓦片地图."""
from shiny import reactive, ui


_SIONTILES_PORT = 8765


def enterprise_map_ui():
    return ui.card(
        ui.card_header("企业地图分析"),
        ui.tags.iframe(
            src=f"http://localhost:{_SIONTILES_PORT}",
            style="width: 100%; height: calc(100vh - 120px); border: none; border-radius: 0 0 8px 8px;",
        ),
        ui.tags.div(
            ui.tags.small(
                "地图服务由 SionTiles 提供 (PMTiles + MapLibre GL JS)。"
                "如地图未加载，请确认 SionTiles 服务已启动。",
                style="color: #888;",
            ),
            style="padding: 8px 16px;",
        ),
    )


def enterprise_map_server(input, output, session):
    pass
