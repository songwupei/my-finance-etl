from flask import Blueprint, send_file

from ..config import _proj_dir

panreg_bp = Blueprint("panreg", __name__)


@panreg_bp.route("/panreg-report")
def panreg_report():
    path = _proj_dir / "data/01_raw/account_PanReg_report.html"
    return send_file(str(path))
