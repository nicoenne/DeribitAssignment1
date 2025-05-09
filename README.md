# Mark price calculator

This application monitors real-time mark prices for Bitcoin options on Deribit, showing both calculated and Deribit-provided prices for calls and puts across different strikes. It is built with Python and Dash and designed for modularity and ease of extension.

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install the required packages:

```bash
pip install numpy pandas threading websocket certifi scipy datetime dash dash_bootstrap_components
```

## Usage

From the root directory, run main.py:

```python
# Inputs example:
expiry_code = "23MAY25"
t1 = 3600                          # Run the app for 3600 seconds
t2 = 2                             # Update prices each 2 seconds
strikes = [95000, 100000, 105000]  # Strikes to keep track

# Start the app
calculator = MarkPriceCalculator(expiry_code, t1, t2, strikes)
threading.Thread(target=calculator.run, daemon=True).start()
run_app(calculator)
```

The app is hosted on local host and it is accessible through a browser (tested on Chrome).
At the start, the console will output the following:

```console
Starting mark price generator for 23MAY25
Runtime: 3600 seconds, Interval: 2 seconds
Strikes: [95000, 100000, 105000]
Connecting to Deribit API ...
Dash is running on http://127.0.0.1:8050/

 * Serving Flask app 'mark_price_calc.dashboard'
 * Debug mode: off
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:8050
Press CTRL+C to quit
Waiting for initial market data...
Connection established
```
On the browser, the app will show the requested information as in the following image:

![screenshot](app_example.png)

## Key Assumptions

In order to get a realistic mark price for an arbitrary choice of strikes, I implemented two solutions, depending on the option liquidity.
For each contract, I subscribed to the corresponding order book updates, in order to keep track of the best bid and best asks. The mark price is computed as mark_price = index_price + EMA( ( best_bid + best_ask ) / 2 - index_price), where EMA is the Exponential Moving Average over the past 2.5 minutes.
Such choice is based on the available literature, given the necessity of keeping the price stable in case of market manipulation attempts.
Whenever an order book is not available through Deribit subscription, a fallback solution based on Black & Scholes formula is used. Here, the underlying price (BTC) and the historical volaility is taken through Deribit API.
