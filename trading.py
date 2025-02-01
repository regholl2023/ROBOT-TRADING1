import time
import os
from alpaca.trading.client import TradingClient
from paging import send_notification
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

from gmail_reader import process_messages

# Constants
INVEST_PERCENTAGE = 0.9  # 90% of available balance
API_KEY = os.getenv('ALPACA_API_KEY')
API_SECRET = os.getenv('ALPACA_API_SECRET')
ROBOT_NAME = os.getenv("ROBOT_NAME", "Day Trader: Price Action Bot for High Volatility and High Liquidity Stocks (TA)")

POLLING_FREQUENCY = 1  # sec

processed_gmail_message = set()

# Initialize Alpaca clients
trading_client = TradingClient(API_KEY, API_SECRET, paper=True)
data_client = StockHistoricalDataClient(API_KEY, API_SECRET)

def get_us_balance():
    """Fetch paper account balance"""
    account = trading_client.get_account()
    return float(account.cash)

def get_current_price(symbol):
    """Get real-time price using latest quote"""
    request = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
    quotes = data_client.get_stock_latest_quote(request)
    return float(quotes[symbol].ask_price)

def place_us_order(symbol, qty, side):
    """Place a market order"""
    if qty < 0.01:  # Minimum quantity of 0.01 shares
        return False

    # Create market order
    order_details = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == 'BUY' else OrderSide.SELL,
        time_in_force=TimeInForce.DAY
    )

    try:
        order = trading_client.submit_order(order_details)
        print(f"Order placed: {order}")
        return True
    except Exception as e:
        print(f"Error placing order: {e}")
        return False

def get_position_quantity(symbol):
    """Get quantity of shares held for a symbol"""
    try:
        position = trading_client.get_open_position(symbol)
        return float(position.qty)
    except:
        return 0
    
def check_signal():
    messages = process_messages()[::-1]  # Get all messages within 2 minutes
    global processed_gmail_message
    for msg in messages:
        if msg['id'] in processed_gmail_message:
            continue
            
        if ROBOT_NAME in msg["body"]:
            message = msg["body"].lower()
            
            # Check for buy signal
            if "bought" in message and "shares at" in message:
                # Extract symbol - assuming format "bought X SYMBOL shares at"
                words = message.split()
                for i, word in enumerate(words):
                    if word == "bought":
                        symbol = words[i + 2].upper()  # Get the word after the quantity
                        processed_gmail_message.add(msg['id'])
                        return "BUY", symbol
            
            # Check for sell signal
            elif "sold" in message and "shares at" in message:
                # Extract symbol - assuming format "sold X SYMBOL shares at"
                words = message.split()
                for i, word in enumerate(words):
                    if word == "sold":
                        symbol = words[i + 2].upper()  # Get the word after the quantity
                        processed_gmail_message.add(msg['id'])
                        return "SELL", symbol
            
            # Mark message as processed even if it doesn't contain a valid signal
            processed_gmail_message.add(msg['id'])
    
    return None, None




def main():
    try:
        while True:
            signal_type, symbol = check_signal()  # Implement your signal logic
            if signal_type is None:
                time.sleep(POLLING_FREQUENCY)
            
            current_balance = get_us_balance()
            current_price = get_current_price(symbol)
            
            if signal_type == 'BUY' and current_balance > 0:
                invest_amt = current_balance * INVEST_PERCENTAGE
                qty = round(invest_amt / current_price, 2)  # Allow fractional shares with 2 decimal points
                if qty > 0:
                    print(f"Buying {qty} shares of {symbol} at ${current_price:.2f}")
                    if place_us_order(symbol, qty, 'BUY'):
                        send_notification("BUY Signal", f"Bought {qty} shares of {symbol} at ${current_price:.2f}", priority=-1)
                
            elif signal_type == 'SELL':
                qty = get_position_quantity(symbol)
                if qty > 0:
                    print(f"Selling {qty} shares of {symbol}")
                    if place_us_order(symbol, qty, 'SELL'):
                        send_notification("SELL Signal", f"Sold {qty} shares of {symbol} at ${current_price:.2f}", priority=-1)
            
            time.sleep(POLLING_FREQUENCY)  # Reduce polling frequency

    except KeyboardInterrupt:
        print("\nStopping trading bot...")


if __name__ == "__main__":
    print(get_us_balance())
