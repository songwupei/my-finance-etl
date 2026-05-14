"""Dash cascade filter callbacks for the account map page."""
from dash import Input, Output, callback, no_update

from .dashboard.data import _bank_map_account_data


def _get_filter_options(df, column):
    vals = sorted(df[column].dropna().unique().tolist())
    return [{"label": v, "value": v} for v in vals]


def _apply_all_filters(df, provinces, cities, banks, subgroups, branches=None):
    for col, vals in [("province", provinces), ("bank_city", cities),
                       ("financial_institution", banks), ("sub_group_name", subgroups),
                       ("branch_name", branches)]:
        if vals:
            df = df[df[col].isin(vals)]
    return df


def _bank_data():
    return _bank_map_account_data if _bank_map_account_data.shape[0] > 0 else None


@callback(Output("city-filter", "options"),
          Input("prov-filter", "value"), Input("bank-filter", "value"),
          Input("sg-filter", "value"))
def update_city_options(prov, bank, sg):
    df = _bank_data()
    if df is None:
        return no_update
    df = _apply_all_filters(df, prov, None, bank, sg)
    return _get_filter_options(df, "bank_city")


@callback(Output("bank-filter", "options"),
          Input("prov-filter", "value"), Input("city-filter", "value"),
          Input("sg-filter", "value"))
def update_bank_options(prov, city, sg):
    df = _bank_data()
    if df is None:
        return no_update
    df = _apply_all_filters(df, prov, city, None, sg)
    return _get_filter_options(df, "financial_institution")


@callback(Output("sg-filter", "options"),
          Input("prov-filter", "value"), Input("city-filter", "value"),
          Input("bank-filter", "value"))
def update_subgroup_options(prov, city, bank):
    df = _bank_data()
    if df is None:
        return no_update
    df = _apply_all_filters(df, prov, city, bank, None)
    return _get_filter_options(df, "sub_group_name")


@callback(Output("branch-filter", "options"),
          Input("prov-filter", "value"), Input("city-filter", "value"),
          Input("bank-filter", "value"), Input("sg-filter", "value"))
def update_branch_options(prov, city, bank, sg):
    df = _bank_data()
    if df is None:
        return no_update
    df = _apply_all_filters(df, prov, city, bank, sg)
    return _get_filter_options(df, "branch_name")
