"""Navigation, Dashboard assembly, and Vizro build."""
import vizro.models as vm
from vizro import Vizro

from .home import (
    _vizro_page_home,
    _vizro_page_monitor,
    _vizro_page_overview,
    _vizro_page_relationship,
)
from .map import _vizro_page_map
from .account_map import _vizro_page_bank_map
from .account_detail import _vizro_page_account_detail
from .balance import (
    _vizro_page_balance_overview,
    _vizro_page_balance_subgroup,
    _vizro_page_balance_bank,
    _vizro_page_balance_geo,
    _vizro_page_balance_cross,
)
from .panreg import _vizro_page_panreg

_vizro_navigation = vm.Navigation(
    pages={
        "首页": ["home"],
        "地理": ["china-map"],
        "监控": ["penetration-monitor", "bank-account-map"],
        "分析": ["relationship-analysis", "account-detail", "overview", "panreg"],
        "账户余额统计分析": ["balance-overview", "balance-subgroup", "balance-bank", "balance-geo", "balance-cross"],
    },
    nav_selector=vm.NavBar(
        items=[
            vm.NavLink(
                icon="home",
                label="HOME",
                pages={
                    "首页": ["home"],
                    "地理": ["china-map"],
                },
            ),
            vm.NavLink(
                icon="account_balance",
                label="账户",
                pages={
                    "监控": ["penetration-monitor", "bank-account-map"],
                    "分析": ["relationship-analysis", "account-detail", "overview", "panreg"],
                    "账户余额统计分析": ["balance-overview", "balance-subgroup", "balance-bank", "balance-geo", "balance-cross"],
                },
            ),
        ]
    ),
)

_vizro_dashboard = vm.Dashboard(
    pages=[_vizro_page_home, _vizro_page_monitor, _vizro_page_relationship,
           _vizro_page_account_detail, _vizro_page_panreg,
           _vizro_page_overview, _vizro_page_map, _vizro_page_bank_map,
           _vizro_page_balance_overview, _vizro_page_balance_subgroup,
           _vizro_page_balance_bank, _vizro_page_balance_geo, _vizro_page_balance_cross],
    navigation=_vizro_navigation,
)


def build_vizro(app):
    """Attach Vizro dashboard to the given Flask app."""
    _vizro = Vizro(server=app, url_base_pathname='/vizro/')
    _vizro.build(_vizro_dashboard)
    return _vizro
