"""Dashboard assembly: imports trigger module-level Vizro page + data loading."""


def build_dashboard(app):
    """Build Vizro dashboard and register Dash callbacks on the Flask app."""
    from .navigation import build_vizro
    build_vizro(app)

    # Register Dash cascade filter callbacks (must be imported after Vizro/Dash init)
    from .. import callbacks  # noqa: F401 - side-effect import registers @callback
