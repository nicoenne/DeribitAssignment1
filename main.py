from mark_price_calc.mark_price_calculator import MarkPriceCalculator
from mark_price_calc.dashboard import run_app
import threading

if __name__ == "__main__":
    # Inputs example:
    expiry_code = "23MAY25"
    t1 = 3600                          # Run the app for 3600 seconds
    t2 = 2                             # Update prices each 2 seconds
    strikes = [95000, 100000, 105000]  # Strikes to keep track

    # Start the app
    calculator = MarkPriceCalculator(expiry_code, t1, t2, strikes)
    threading.Thread(target=calculator.run, daemon=True).start()
    run_app(calculator)
