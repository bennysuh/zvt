# -*- coding: utf-8 -*-
from typing import List

import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output

from zvt.api.business import get_trader
from zvt.app import app
from zvt.charts.dcc_components import get_trader_detail_figures
from zvt.domain import business
from zvt.reader.business_reader import AccountReader, OrderReader

account_readers = []
order_readers = []

# init the data
trader_domains: List[business.Trader] = get_trader(return_type='domain')

trader_names: List[str] = [item.trader_name for item in trader_domains]


def load_traders():
    global trader_domains
    global trader_names

    trader_domains = get_trader(return_type='domain')
    for trader in trader_domains:
        account_readers.append(AccountReader(trader_names=[trader.trader_name], level=trader.level))
        order_readers.append(OrderReader(trader_names=[trader.trader_name]))

    trader_names = [item.trader_name for item in trader_domains]


load_traders()


def serve_layout():
    layout = html.Div(
        [
            html.Div(
                [
                    dcc.Dropdown(
                        id='trader-selector',
                        placeholder='select the trader',
                        options=[{'label': item, 'value': i} for i, item in enumerate(trader_names)])
                ]),

            html.Div(id='trader-details', style={'width': '80%', 'margin': 'auto'}),

            dcc.Interval(
                id='interval-component',
                interval=5 * 1000,  # in milliseconds
                n_intervals=0
            )

        ])

    load_traders()

    return layout


@app.callback(
    Output('trader-details', 'children'),
    [Input('interval-component', 'n_intervals'),
     Input('trader-selector', 'value')])
def update_trader_details(n, i):
    if i is None or n < 1:
        return ''

    return get_trader_detail_figures(trader_domain=trader_domains[i], account_reader=account_readers[i],
                                     order_reader=order_readers[i])
