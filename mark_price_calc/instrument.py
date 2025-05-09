class Instrument:
    def __init__(self, name):
        self.name = name
        self.strike = float(name.split('-')[2])
        self.opt_type = name[-1]
        self.bids = {}
        self.asks = {}
        self.best_bid = None
        self.best_ask = None
        self.last_change_id = None
        self.ema_value = None
        self.ema_price = None
        self.bsm_price = None
        self.price = None
        self.deribit_price = None

    def update(self, data):
        change_id = data.get("change_id")
        prev_change_id = data.get("prev_change_id", None)
        update_type = data.get("type")

        # Verify continuity
        if self.last_change_id is not None and prev_change_id is not None:
            if prev_change_id != self.last_change_id:
                print(f"[WARNING] Missed updates for {self.name}")
                return

        # Handle first notification
        if update_type == "snapshot":
            self.bids = {price: amount for _, price, amount in data.get("bids", [])}
            self.asks = {price: amount for _, price, amount in data.get("asks", [])}

        elif update_type == "change":
            for action, price, amount in data.get("bids", []):
                self._update_side(self.bids, action, price, amount)
            for action, price, amount in data.get("asks", []):
                self._update_side(self.asks, action, price, amount)

        if self.bids:
            self.best_bid = max(self.bids.copy())
        if self.asks:
            self.best_ask = min(self.asks.copy())

        # Update change ID tracker
        self.last_change_id = change_id

    def _update_side(self, book, action, price, amount):
        if action == "new" or action == "change":
            book[price] = amount
        elif action == "delete":
            book.pop(price, None)

    def __repr__(self):
        """Used for debugging."""
        return f"Instrument({self.name}) — {len(self.bids)} bids / {len(self.asks)} asks"
