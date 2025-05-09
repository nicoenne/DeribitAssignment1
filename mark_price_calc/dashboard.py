import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc
import pandas as pd


def run_app(calculator):
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.title = "Deribit Mark Price Monitor"

    app.layout = dbc.Container([
        html.H2("Mark Price Monitor"),
        dcc.Interval(id="interval", interval=calculator.t2 * 1000, n_intervals=0),
        dash_table.DataTable(
            id="price-table",
            columns=[
                {"name": "Deribit Call", "id": "deribit_call"},
                {"name": "Price Call", "id": "price_call"},
                {"name": "Strike", "id": "strike"},
                {"name": "Deribit Put", "id": "deribit_put"},
                {"name": "Price Put", "id": "price_put"},
            ],
            style_cell={"padding": "6px", "fontFamily": "Arial", "fontSize": 14},
            style_header={"backgroundColor": "#f8f9fa", "fontWeight": "bold"},
            style_table={"overflowX": "auto"},
            style_cell_conditional=[
                {"if": {"column_id": "strike"}, "textAlign": "center", "fontWeight": "bold"},
                {"if": {"column_id": "deribit_call"}, "textAlign": "right"},
                {"if": {"column_id": "price_call"}, "textAlign": "right"},
                {"if": {"column_id": "deribit_put"}, "textAlign": "left"},
                {"if": {"column_id": "price_put"}, "textAlign": "left"},
            ],
        ),
    ])

    @app.callback(
        Output("price-table", "data"),
        [Input("interval", "n_intervals")]
    )
    def update_table(n):
        prices = calculator.get_latest_prices()
        if not prices:
            return html.Div("Waiting for data...")
        prices = pd.DataFrame(prices).T
        prices.sort_values(by=["strike", "type"], inplace=True)
        prices = prices.pivot(index="strike", columns="type", values=["deribit_price", "price"])
        prices.columns = ["deribit_call", "deribit_put", "price_call", "price_put"]
        prices = prices.reset_index()
        prices = prices[["deribit_call", "price_call", "strike", "deribit_put", "price_put"]]
        return prices.to_dict("records")

    app.run(debug=False, use_reloader=False)
