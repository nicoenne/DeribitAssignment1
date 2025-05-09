import time
import json
from numpy import sqrt, exp, log, round
from datetime import datetime, timezone
import websocket
import threading
import certifi
from scipy.stats import norm
from mark_price_calc.instrument import Instrument


class MarkPriceCalculator:
    def __init__(self, expiry_code, t1, t2, strikes):
        """
        Initialize the Mark Price Generator.

        Parameters:
        - expiry_code: Deribit expiry code (e.g., "23MAY25")
        - t1: Total runtime in seconds
        - t2: Interval between computations in seconds
        - strikes: Array of strike prices to calculate mark prices for
        """
        self.expiry_code = expiry_code
        expiry_datetime = datetime.strptime(self.expiry_code, "%d%b%y")
        self.expiry_datetime = expiry_datetime.replace(hour=8, minute=0, second=0, tzinfo=timezone.utc)
        self.time_to_expiry = None
        self.t1 = t1
        self.t2 = t2
        self.strikes = strikes

        self.prices_snapshot = {}
        self.snapshot_lock = threading.Lock()

        self.ws = None
        self.curr = "BTC"  # default to BTC
        self.instruments = {name: Instrument(name) for name in self._generate_instrument_names()}
        self.index_price = None
        self.index_volatility = None

    def _generate_instrument_names(self):
        """Generate full instrument names for the given strikes."""
        # Parse the expiry code to get the date
        # Format example: BTC-23MAY25-40000-C for a 40,000 strike call option
        instrument_names = []
        for strike in self.strikes:
            call_name = f"{self.curr}-{self.expiry_code}-{strike}-C"
            put_name = f"{self.curr}-{self.expiry_code}-{strike}-P"
            instrument_names.extend([call_name, put_name])
        return instrument_names

    def _connect_to_deribit(self):
        """Establish WebSocket connection to Deribit."""
        print("Connecting to Deribit API ...")
        self.ws = websocket.WebSocketApp(
            "wss://test.deribit.com/ws/api/v2",
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )

        # Start WebSocket connection in a separate thread
        wst = threading.Thread(target=lambda: self.ws.run_forever(
            sslopt={"ca_certs": certifi.where()}
        ))
        wst.daemon = True
        wst.start()

        # Wait for connection to establish
        time.sleep(1)

    def _subscribe_to_channel(self, channel):
        """Subscribe to a specific Deribit WebSocket channel."""
        msg = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "public/subscribe",
            "params": {
                "channels": [channel]
            }
        }
        self.ws.send(json.dumps(msg))

    def on_open(self, ws):
        """Handle WebSocket open event."""
        print("Connection established")

        # Subscribe to index price
        self._subscribe_to_channel(f"deribit_price_index.{self.curr.lower()}_usd")

        # Subscribe to index volatility for the fallback case of illiquid options
        self._subscribe_to_channel(f"deribit_volatility_index.{self.curr.lower()}_usd")

        # Subscribe to order books for each instrument
        for instrument_name in self.instruments.keys():
            self._subscribe_to_channel(f"book.{instrument_name}.100ms")
            self._subscribe_to_channel(f"ticker.{instrument_name}.100ms")

    def on_message(self, ws, message):
        """Process incoming WebSocket messages."""
        message = json.loads(message)
        # Handle subscription confirmations
        if "id" in message and message.get("id") == 42:
            return

        if message.get("method") != "subscription":
            return

        params = message.get("params")
        channel = params.get("channel")
        data = params.get("data")

        # Handle index price updates
        if channel.startswith('deribit_price_index'):
            self.index_price = data['price']
            return

        # Handle index price updates
        if channel.startswith('deribit_volatility_index'):
            self.index_volatility = data['volatility']
            return

        # Handle instrument order book updates
        if channel.startswith('book'):
            try:
                self.instruments[data.get("instrument_name")].update(data)
            except KeyError:
                print('[WARNING] Received an unknown instrument name')

        # Handle ticker updates to peep at Deribit mark price
        if channel.startswith('ticker'):
            try:
                self.instruments[data.get("instrument_name")].deribit_price = data['mark_price']
            except KeyError:
                print('[WARNING] Received an unknown instrument name')

    def on_error(self, ws, error):
        """Handle WebSocket errors."""
        print(f"Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close event."""
        print("Connection closed")

    def _price_instrument_from_order_book(self, instrument):
        """
        Compute mark price = index_price + EMA[(best_bid + best_ask)/2 - index_price]
        """
        if self.index_price is None:
            print(f"[WARNING] No index price available.")
            return
        # Check for liquidity
        if instrument.best_ask is None or instrument.best_bid is None:
            print(f"[WARNING] Unable to determine best bid/ask for {instrument.name}.")
            return
        mid_price = (instrument.best_bid + instrument.best_ask) * .5
        ema_value = mid_price - (1 / self.index_price)
        # The EMA will consider up to 2.5 minutes of data,
        # so roughly N = 2.5 * 60 / t2 number of observations
        alpha = 2 / ((2.5 * 60 / self.t2) + 1)
        if instrument.ema_value is None:
            instrument.ema_value = mid_price
        else:
            instrument.ema_value = alpha * ema_value + (1 - alpha) * instrument.ema_value
        instrument.ema_price = (1 / self.index_price) + instrument.ema_value

    def _price_instrument_with_bsm(self, instrument):
        """ Compute the price in BTC with Black & Scholes model."""
        if self.index_price is None or self.index_volatility is None:
            print(f"[WARNING] Missing index price or volatility index for fallback pricing.")
            return
        k = instrument.strike
        s = self.index_price
        sigma = self.index_volatility / 100
        r = 0.0
        t = self.time_to_expiry

        d1 = (log(s / k) + 0.5 * sigma ** 2 * t) / (sigma * sqrt(t))
        d2 = d1 - sigma * sqrt(t)

        if instrument.opt_type == 'C':
            price = s * norm.cdf(d1) - k * exp(-r * t) * norm.cdf(d2)
        else:  # Put
            price = k * exp(-r * t) * norm.cdf(-d2) - s * norm.cdf(-d1)

        instrument.bsm_price = price / s

    def _price_instrument(self, instrument):
        """Compute mark price using order book if liquid, otherwise fallback to Black-Scholes."""
        # First try order book
        if instrument.best_bid and instrument.best_ask:
            self._price_instrument_from_order_book(instrument)
            instrument.price = round(instrument.ema_price, 4)
        # Fallback to BSM
        else:
            self._price_instrument_with_bsm(instrument)
            instrument.price = round(instrument.bsm_price, 4)

    def get_latest_prices(self):
        with self.snapshot_lock:
            return self.prices_snapshot

    def run(self):
        """Run the mark price generator for the specified duration and intervals."""
        print(f"Starting mark price generator for {self.expiry_code}")
        print(f"Runtime: {self.t1} seconds, Interval: {self.t2} seconds")
        print(f"Strikes: {self.strikes}")

        # Connect to Deribit
        self._connect_to_deribit()

        # Wait for initial data to load
        print("Waiting for initial market data...")
        time.sleep(5)

        start_time = time.time()
        next_time = start_time
        end_time = start_time + self.t1

        try:
            while time.time() < end_time:
                current_time = time.time()
                # Check if it's time for the next calculation
                if current_time < next_time:
                    continue
                # Updates the time to expiry (Actual/Actual convention)
                time_to_expiry = (self.expiry_datetime - datetime.now(tz=timezone.utc)).total_seconds()
                self.time_to_expiry = time_to_expiry / (365.25 * 24 * 3600)

                print(f"\nPerforming calculation at {datetime.now().strftime("%H:%M:%S")}")
                for instrument in self.instruments.values():
                    self._price_instrument(instrument)
                    with self.snapshot_lock:
                        self.prices_snapshot[instrument.name] = {
                            'strike': instrument.strike,
                            'type': instrument.opt_type,
                            'deribit_price': instrument.deribit_price,
                            'price': instrument.price
                            }

                # Schedule next calculation
                next_time = current_time + self.t2
                # Sleep to avoid excessive CPU usage
                time.sleep(0.05)

        except KeyboardInterrupt:
            print("Interrupted by user")
        finally:
            # Clean up
            if self.ws:
                self.ws.close()
