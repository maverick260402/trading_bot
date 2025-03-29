import requests
import os
import pyotp
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sys
import datetime
import time
from dotenv import load_dotenv
import pandas_ta as ta

sys.stdout.reconfigure(encoding='utf-8')

# Load environment variables from .env file
load_dotenv()

# Angel One API credentials
API_KEY = os.getenv("ANGELONE_API_KEY")
CLIENT_ID = os.getenv("ANGELONE_CLIENT_ID")
PASSWORD = os.getenv("ANGELONE_MPIN")
TOTP_SECRET = os.getenv("ANGELONE_TOTP_SECRET")

# Global variables
auth_token = None
headers = None
duration = "DAY"
# quantity = 1
active_position = None
entry_price = None
stop_loss = None
take_profit = None

stop_flag = False
# Candle size configuration
CANDLE_SIZE = "ONE_MINUTE"  # Options: "ONE_MINUTE", "FIVE_MINUTE", "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR", "ONE_DAY"

# Map candle size to minutes for calculations
CANDLE_SIZE_MINUTES = {
"ONE_MINUTE": 1,
"FIVE_MINUTE": 5,
"FIFTEEN_MINUTE": 15,
"THIRTY_MINUTE": 30,
"ONE_HOUR": 60,
"ONE_DAY": 1440  # Not really used for intraday rounding, but included for completeness
}

def topgun(trading_symbol,symbol_token,exchange, quantity):
    # Fix UnicodeEncodeError for Windows
    sys.stdout.reconfigure(encoding='utf-8')

    # Load environment variables from .env file
    # load_dotenv()

    # # Angel One API credentials
    # API_KEY = os.getenv("ANGELONE_API_KEY")
    # CLIENT_ID = os.getenv("ANGELONE_CLIENT_ID")
    # PASSWORD = os.getenv("ANGELONE_MPIN")
    # TOTP_SECRET = os.getenv("ANGELONE_TOTP_SECRET")

    # # Global variables
    # auth_token = None
    # headers = None
    # duration = "DAY"
    # # quantity = 1
    # active_position = None
    # entry_price = None
    # stop_loss = None
    # take_profit = None

    # # Candle size configuration
    # CANDLE_SIZE = "ONE_MINUTE"  # Options: "ONE_MINUTE", "FIVE_MINUTE", "FIFTEEN_MINUTE", "THIRTY_MINUTE", "ONE_HOUR", "ONE_DAY"

    # # Map candle size to minutes for calculations
    # CANDLE_SIZE_MINUTES = {
    #     "ONE_MINUTE": 1,
    #     "FIVE_MINUTE": 5,
    #     "FIFTEEN_MINUTE": 15,
    #     "THIRTY_MINUTE": 30,
    #     "ONE_HOUR": 60,
    #     "ONE_DAY": 1440  # Not really used for intraday rounding, but included for completeness
    # }

    def debug_dataframe(df, label="Dataframe"):
        """Helper function to debug dataframe issues"""
        print(f"\n===== {label} Debug Info =====")
        print(f"Shape: {df.shape}")
        print(f"Columns: {df.columns.tolist()}")
        print(f"Index type: {type(df.index)}")
        if isinstance(df.index, pd.DatetimeIndex):
            print(f"Timezone info: {df.index.tz}")
        print(f"First few rows:")
        print(df.head(2))
        print(f"Last few rows:")
        print(df.tail(2))
        print("=" * 40)

    def login_to_angel_one():
        global auth_token, headers
        
        # API endpoint for login
        url = "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"
        
        # Headers
        headers = {
            "Content-type": "application/json",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "Accept": "application/json",
            "X-PrivateKey": API_KEY,
            "X-UserType": "USER",
            "X-SourceID": "WEB"
        }
        
        # Request body for login
        payload = {
            "clientcode": CLIENT_ID,
            "password": PASSWORD,
            "totp": pyotp.TOTP(TOTP_SECRET).now()
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response_data = response.json()
            
            if response_data.get("status"):
                print("✅ Login successful!")
                auth_token = response_data["data"]["jwtToken"]
                headers["Authorization"] = f"Bearer {auth_token}"  # Add auth token to headers
                return True
            else:
                print("❌ Login failed. Error:", response_data.get("message"))
                return False
        except Exception as e:
            print("⚠ An error occurred during login:", str(e))
            return False

    def logout_from_angel_one():
        global headers

        # API endpoint for logout
        url = "https://apiconnect.angelone.in/rest/secure/angelbroking/user/v1/logout"

        # Request payload
        payload = {
            "clientcode": CLIENT_ID  # Ensure CLIENT_ID is defined
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            response_data = response.json()

            if response_data.get("status"):
                print("✅ Logout successful!")
                return True
            else:
                print("❌ Logout failed. Error:", response_data.get("message"))
                return False
        except Exception as e:
            print("⚠ An error occurred during logout:", str(e))
            return False

    def fetch_historical_stock_data(symbol_token, exchange):
        global CANDLE_SIZE
        
        now = datetime.datetime.now()
        today = now.date()
        current_time = now.time()
        
        # Define market hours
        market_open = datetime.time(9, 15)
        market_close = datetime.time(15, 30)
        
        # Determine if market is currently open
        market_is_open = (now.weekday() < 5) and (market_open <= current_time <= market_close)
        
        # Get the most recent or current trading day
        if market_is_open:
            # Market is currently open, use today's data from open until now
            trading_date = today
            from_date = today.strftime("%Y-%m-%d") + " 09:15"
            to_date = now.strftime("%Y-%m-%d %H:%M")
        else:
            # Market is closed, find the most recent trading day
            days_to_subtract = 1
            if now.weekday() == 5:  # Saturday
                days_to_subtract = 1  # Get Friday's data
            elif now.weekday() == 6:  # Sunday
                days_to_subtract = 2  # Get Friday's data
            elif current_time < market_open and now.weekday() != 0:
                # Before market open on weekday, get yesterday's data
                days_to_subtract = 1
            elif current_time > market_close:
                # After market close, get today's data
                days_to_subtract = 0
            elif now.weekday() == 0 and current_time < market_open:
                # Monday before market open, get Friday's data
                days_to_subtract = 3
            
            trading_date = today - datetime.timedelta(days=days_to_subtract)
            from_date = trading_date.strftime("%Y-%m-%d") + " 09:15"
            to_date = trading_date.strftime("%Y-%m-%d") + " 15:30"
        
        print(f"📅 Fetching historical data ({CANDLE_SIZE}) from {from_date} to {to_date}")
        
        payload = {
            "exchange": exchange,
            "symboltoken": symbol_token,
            "interval": CANDLE_SIZE,  # Use global candle size
            "fromdate": from_date,
            "todate": to_date
        }
        
        url = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
        response = requests.post(url, json=payload, headers=headers)
        
        try:
            response_data = response.json()
        except Exception as e:
            print("❌ Failed to parse API response:", str(e))
            return None
        
        if "data" in response_data and response_data["data"]:
            df = pd.DataFrame(response_data["data"], columns=["date", "open", "high", "low", "close", "volume"])
            df["date"] = pd.to_datetime(df["date"])
            
            # Filter data to include only market working hours (09:15 to 15:30)
            df["time"] = df["date"].dt.time
            df = df[(df["time"] >= datetime.time(9, 15)) & (df["time"] <= datetime.time(15, 30))]
            df = df.drop(columns=["time"])
            
            df.set_index("date", inplace=True)
            print(f"✅ Historical Data Fetched Successfully! ({len(df)} candles)")
            return df
        else:
            print("❌ API returned no historical data!")
            return None

    def fetch_live_stock_data(symbol_token, exchange):
        url = "https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/"
        payload = {"mode": "FULL", "exchangeTokens": {exchange: [symbol_token]}}
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response_data = response.json()
            
            if "data" in response_data:
                market_data = response_data["data"].get("fetched", [])
                if market_data:
                    # Convert the data to a dataframe
                    current_time = pd.Timestamp.now(tz='Asia/Kolkata')
                    live_data = {
                        "date": current_time,
                        "open": float(market_data[0].get("open", 0)),
                        "high": float(market_data[0].get("high", 0)),
                        "low": float(market_data[0].get("low", 0)),
                        "close": float(market_data[0].get("ltp", 0)),  # Using LTP as close
                        "volume": int(market_data[0].get("totalTradedVolume", 0))
                    }
                    
                    # Create a dataframe with a single row
                    df = pd.DataFrame([live_data])
                    df.set_index("date", inplace=True)
                    
                    print("✅ Live data fetched successfully:")
                    print(df)
                    return df
        except Exception as e:
            print("❌ Failed to fetch live data:", str(e))
        
        return None

    def update_live_data(live_df, new_data):
        global CANDLE_SIZE, CANDLE_SIZE_MINUTES
        
        if new_data is not None and not new_data.empty:
            if live_df is None or live_df.empty:
                combined = new_data
            else:
                # Get minutes for current candle size
                minutes_to_round = CANDLE_SIZE_MINUTES.get(CANDLE_SIZE, 15)
                
                # Round timestamps to the interval specified by CANDLE_SIZE
                new_time = new_data.index[0]
                rounded_time = pd.Timestamp(
                    year=new_time.year, 
                    month=new_time.month,
                    day=new_time.day,
                    hour=new_time.hour,
                    minute=(new_time.minute // minutes_to_round) * minutes_to_round,
                    tz=new_time.tz
                )
                
                # Check if we need to update the last candle or create a new one
                if not live_df.empty:
                    # Ensure the index is datetime type with consistent timezone handling
                    if not isinstance(live_df.index, pd.DatetimeIndex):
                        # Convert to timezone-aware datetime preserving any timezone information
                        live_df.index = pd.to_datetime(live_df.index, utc=True).tz_convert(rounded_time.tz)
                    elif live_df.index.tz != rounded_time.tz:
                        # Ensure timezone consistency
                        if live_df.index.tz is None:
                            live_df.index = pd.to_datetime(live_df.index).tz_localize(rounded_time.tz)
                        else:
                            live_df.index = live_df.index.tz_convert(rounded_time.tz)
                    
                    # Use floor with the correct candle interval
                    floor_str = f"{minutes_to_round}min"
                    
                    # Now check if we update the last candle or create a new one
                    last_candle_time = live_df.index[-1]
                    last_candle_floor = last_candle_time.floor(floor_str)
                    rounded_time_floor = rounded_time.floor(floor_str)
                    
                    if last_candle_floor == rounded_time_floor:
                        # Update the last candle
                        last_idx = live_df.index[-1]
                        live_df.at[last_idx, 'high'] = max(live_df.at[last_idx, 'high'], new_data['high'].values[0])
                        live_df.at[last_idx, 'low'] = min(live_df.at[last_idx, 'low'], new_data['low'].values[0])
                        live_df.at[last_idx, 'close'] = new_data['close'].values[0]
                        live_df.at[last_idx, 'volume'] += new_data['volume'].values[0]
                        
                        # Only keep the OHLCV columns when updating
                        columns_to_keep = ['open', 'high', 'low', 'close', 'volume']
                        for col in live_df.columns:
                            if col not in columns_to_keep:
                                live_df = live_df.drop(columns=[col])
                                
                        combined = live_df
                    else:
                        # Add a new candle
                        new_data.index = [rounded_time]
                        
                        # Only keep the OHLCV columns when adding new data
                        new_data = new_data[['open', 'high', 'low', 'close', 'volume']]
                        
                        # Ensure we have the same columns in both dataframes before concatenation
                        if set(live_df.columns) != set(new_data.columns):
                            live_df = live_df[['open', 'high', 'low', 'close', 'volume']]
                        
                        combined = pd.concat([live_df, new_data])
                else:
                    # Add a new candle
                    new_data.index = [rounded_time]
                    combined = new_data
            
            # Sort index to avoid misalignment issues
            combined = combined.sort_index()
            
            # Keep only the latest 100 records
            return combined.tail(100)
        
        return live_df if live_df is not None else pd.DataFrame()

    def calculate_supertrend(df):
        if df is None or df.empty:
            print("❌ No data available for Supertrend calculation")
            return None
        
        # Make a copy to avoid modifying the original
        df_copy = df.copy()
        
        # Ensure all required columns exist and are numeric
        required_cols = ["open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in df_copy.columns:
                print(f"❌ Missing column: {col} for Supertrend calculation")
                return None
            df_copy[col] = pd.to_numeric(df_copy[col], errors='coerce')
        
        # Drop rows with NaN values
        df_copy = df_copy.dropna(subset=required_cols)
        
        # Print dataframe info for debugging
        print(f"🔍 Dataframe shape before Supertrend: {df_copy.shape}")
        
        if len(df_copy) < 10:  # Minimum length for Supertrend calculation
            print("❌ Not enough data points for Supertrend calculation")
            return df_copy
        
        try:
            # Calculate Supertrend using pandas_ta
            supertrend = ta.supertrend(df_copy['high'], df_copy['low'], df_copy['close'], length=10, multiplier=2.0)
            if supertrend is not None:
                # Make sure we don't have duplicate columns by dropping any existing supertrend columns
                for col in df_copy.columns:
                    if col.startswith('SUPERT_'):
                        df_copy = df_copy.drop(columns=[col])
                
                # Join the supertrend dataframe with our price dataframe
                df_copy = pd.concat([df_copy, supertrend], axis=1)
                
                # Explicitly align the series before comparison to avoid alignment errors
                close_series = df_copy['close']
                supertrend_series = df_copy["SUPERT_10_2.0"]
                
                # Make sure both series have the same index
                close_series, supertrend_series = close_series.align(supertrend_series, join='inner')
                
                # Create the signal column
                df_copy['signal'] = np.where(close_series > supertrend_series, 'buy', 'sell')
                
                # Detect signal changes (from buy to sell or sell to buy)
                df_copy['signal_change'] = (df_copy['signal'] != df_copy['signal'].shift(1)) & (df_copy['signal'].shift(1).notna())
                
            else:
                print("❌ Supertrend calculation returned None")
        except Exception as e:
            print(f"❌ Error calculating Supertrend: {e}")
            import traceback
            traceback.print_exc()
        
        return df_copy

    def plot_data_with_supertrend(df):
        global CANDLE_SIZE
        
        if df is None or df.empty or 'SUPERT_10_2.0' not in df.columns:
            print("❌ No data available for plotting")
            return
        
        fig = go.Figure()
        
        # Add candlestick trace
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price"
        ))
        
        # Add Supertrend line trace
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df["SUPERT_10_2.0"],
            mode="lines",
            name="Supertrend",
            line=dict(dash="dash", color="purple")
        ))
        
        # Add buy signals
        buy_signals = df[df['signal'] == 'buy']
        if not buy_signals.empty:
            fig.add_trace(go.Scatter(
                x=buy_signals.index,
                y=buy_signals["low"] * 0.998,  # Place slightly below the candle
                mode='markers',
                marker=dict(
                    color='green',
                    size=10,
                    symbol='triangle-up'
                ),
                name='Buy Signal'
            ))
        
        # Add sell signals
        sell_signals = df[df['signal'] == 'sell']
        if not sell_signals.empty:
            fig.add_trace(go.Scatter(
                x=sell_signals.index,
                y=sell_signals["high"] * 1.002,  # Place slightly above the candle
                mode='markers',
                marker=dict(
                    color='red',
                    size=10,
                    symbol='triangle-down'
                ),
                name='Sell Signal'
            ))
        
        # Calculate y-axis range with some padding
        y_min = df["low"].min() * 0.99
        y_max = df["high"].max() * 1.01
        
        fig.update_layout(
            title=f"Stock Data with Supertrend Indicator ({CANDLE_SIZE})",
            xaxis_title="Date/Time",
            yaxis_title="Price",
            yaxis=dict(range=[y_min, y_max])
        )
        
        # Use rangebreaks to remove non-trading hours and weekends
        fig.update_xaxes(
            rangebreaks=[
                dict(bounds=["sat", "mon"]),
                dict(bounds=[15.5, 9.25], pattern="hour")
            ]
        )
        
        fig.show()

    def execute_buy_order(trading_symbol, quantity, stop_loss_price=None):
        url = "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder"
        
        # Setting up order parameters
        payload = {
            "exchange": exchange,
            "tradingsymbol": trading_symbol,
            "symboltoken" : symbol_token,
            "quantity": quantity,
            "disclosedquantity": 0,
            "transactiontype": "BUY",
            "duration" : duration,
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "variety": "NORMAL"
        }

        headers = {
            'X-PrivateKey': '7Ee2qnqp',
            'Accept': 'application/json',
            'X-SourceID': 'WEB',
            'X-ClientLocalIP': 'CLIENT_LOCAL_IP',
            'X-ClientPublicIP': 'CLIENT_PUBLIC_IP',
            'X-MACAddress': 'MAC_ADDRESS',
            'X-UserType': 'USER',
            'Authorization': 'Bearer eyJhbGciOiJIUzUxMiJ9.eyJ1c2VybmFtZSI6Ikg3NjQ5MyIsInJvbGVzIjowLCJ1c2VydHlwZSI6IlVTRVIiLCJ0b2tlbiI6ImV5SmhiR2NpT2lKU1V6STFOaUlzSW5SNWNDSTZJa3BYVkNKOS5leUoxYzJWeVgzUjVjR1VpT2lKamJHbGxiblFpTENKMGIydGxibDkwZVhCbElqb2lkSEpoWkdWZllXTmpaWE56WDNSdmEyVnVJaXdpWjIxZmFXUWlPallzSW5OdmRYSmpaU0k2SWpNaUxDSmtaWFpwWTJWZmFXUWlPaUpsWVdZMVpqZGpZUzB4T0daa0xUTTJORGt0WVRkbE15MDRPRFpoWVRoa1pUTXpOVGtpTENKcmFXUWlPaUowY21Ga1pWOXJaWGxmZGpJaUxDSnZiVzVsYldGdVlXZGxjbWxrSWpvMkxDSndjbTlrZFdOMGN5STZleUprWlcxaGRDSTZleUp6ZEdGMGRYTWlPaUpoWTNScGRtVWlmU3dpYldZaU9uc2ljM1JoZEhWeklqb2lZV04wYVhabEluMTlMQ0pwYzNNaU9pSjBjbUZrWlY5c2IyZHBibDl6WlhKMmFXTmxJaXdpYzNWaUlqb2lTRGMyTkRreklpd2laWGh3SWpveE56UXlPVEl3TlRZeUxDSnVZbVlpT2pFM05ESTRNek01T0RJc0ltbGhkQ0k2TVRjME1qZ3pNems0TWl3aWFuUnBJam9pTWpNM05UY3pNbUV0TnpKaVpTMDBNalF3TFdFM09XSXRaakpoT0dOak5qSmlOelkzSWl3aVZHOXJaVzRpT2lJaWZRLmNZVWxjbFRrTm9NRm43UGFnTlNMckpadTN0SDN4cHBRSjBCcjh3c0JZNjRGUFBIVmNHdUVyRGhoSGxGN3lPYWkwdGhKRVpiMXptWnp1c1F6OXp3ZkoyRVRCRTR6M3ZoX24tV2lsdFN1MGxoYmRlME9kNzBjWk95YkJsYk9pMVFjNjh3aVM4Sl85YUZTOWZsRVJpNmhvSjAzT21WMktCNllPRGhiZzJGQl9hdyIsIkFQSS1LRVkiOiI3RWUycW5xcCIsImlhdCI6MTc0MjgzNDE2MiwiZXhwIjoxNzQyOTIwNTYyfQ.SVKypuoizgHRlVRkU2HlaiN8pzXWRybuB3bEDFc-hnJ8o36QZt5A16o63HPymYN3Y4FoyNbsDuoffkkr9Z62pg',
            'Accept': 'application/json',
            'X-SourceID': 'WEB',
            'Content-Type': 'application/json'
        }
        
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response_data = response.json()
            
            if response_data.get("status"):
                print(f"✅ Buy order placed successfully! Order ID: {response_data.get('data', {}).get('orderid')}")
                return True
            else:
                print(f"❌ Failed to place buy order: {response_data.get('message')}")
                return False
        except Exception as e:
            print(f"⚠ Error placing buy order: {str(e)}")
            return False

    def execute_sell_order(trading_symbol, quantity, stop_loss_price=None):
        url = "https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/placeOrder"
        
        # Setting up order parameters
        payload = {
            "exchange": exchange,
            "tradingsymbol": trading_symbol,
            "symboltoken" : symbol_token,
            "quantity": quantity,
            "disclosedquantity": 0,
            "transactiontype": "SELL",
            "duration" : duration,
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "variety": "NORMAL"
        }

        headers = {
            'X-PrivateKey': '7Ee2qnqp',
            'Accept': 'application/json',
            'X-SourceID': 'WEB',
            'X-ClientLocalIP': 'CLIENT_LOCAL_IP',
            'X-ClientPublicIP': 'CLIENT_PUBLIC_IP',
            'X-MACAddress': 'MAC_ADDRESS',
            'X-UserType': 'USER',
            'Authorization': 'Bearer eyJhbGciOiJIUzUxMiJ9.eyJ1c2VybmFtZSI6Ikg3NjQ5MyIsInJvbGVzIjowLCJ1c2VydHlwZSI6IlVTRVIiLCJ0b2tlbiI6ImV5SmhiR2NpT2lKU1V6STFOaUlzSW5SNWNDSTZJa3BYVkNKOS5leUoxYzJWeVgzUjVjR1VpT2lKamJHbGxiblFpTENKMGIydGxibDkwZVhCbElqb2lkSEpoWkdWZllXTmpaWE56WDNSdmEyVnVJaXdpWjIxZmFXUWlPallzSW5OdmRYSmpaU0k2SWpNaUxDSmtaWFpwWTJWZmFXUWlPaUpsWVdZMVpqZGpZUzB4T0daa0xUTTJORGt0WVRkbE15MDRPRFpoWVRoa1pUTXpOVGtpTENKcmFXUWlPaUowY21Ga1pWOXJaWGxmZGpJaUxDSnZiVzVsYldGdVlXZGxjbWxrSWpvMkxDSndjbTlrZFdOMGN5STZleUprWlcxaGRDSTZleUp6ZEdGMGRYTWlPaUpoWTNScGRtVWlmU3dpYldZaU9uc2ljM1JoZEhWeklqb2lZV04wYVhabEluMTlMQ0pwYzNNaU9pSjBjbUZrWlY5c2IyZHBibDl6WlhKMmFXTmxJaXdpYzNWaUlqb2lTRGMyTkRreklpd2laWGh3SWpveE56UXlPVEl3TlRZeUxDSnVZbVlpT2pFM05ESTRNek01T0RJc0ltbGhkQ0k2TVRjME1qZ3pNems0TWl3aWFuUnBJam9pTWpNM05UY3pNbUV0TnpKaVpTMDBNalF3TFdFM09XSXRaakpoT0dOak5qSmlOelkzSWl3aVZHOXJaVzRpT2lJaWZRLmNZVWxjbFRrTm9NRm43UGFnTlNMckpadTN0SDN4cHBRSjBCcjh3c0JZNjRGUFBIVmNHdUVyRGhoSGxGN3lPYWkwdGhKRVpiMXptWnp1c1F6OXp3ZkoyRVRCRTR6M3ZoX24tV2lsdFN1MGxoYmRlME9kNzBjWk95YkJsYk9pMVFjNjh3aVM4Sl85YUZTOWZsRVJpNmhvSjAzT21WMktCNllPRGhiZzJGQl9hdyIsIkFQSS1LRVkiOiI3RWUycW5xcCIsImlhdCI6MTc0MjgzNDE2MiwiZXhwIjoxNzQyOTIwNTYyfQ.SVKypuoizgHRlVRkU2HlaiN8pzXWRybuB3bEDFc-hnJ8o36QZt5A16o63HPymYN3Y4FoyNbsDuoffkkr9Z62pg',
            'Accept': 'application/json',
            'X-SourceID': 'WEB',
            'Content-Type': 'application/json'
        }
        
        # If stop loss is provided, use STOPLOSS variety
        #if stop_loss_price:
            #payload["variety"] = "STOPLOSS"
            #payload["triggerprice"] = stop_loss_price
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response_data = response.json()
            
            if response_data.get("status"):
                print(f"✅ Sell order placed successfully! Order ID: {response_data.get('data', {}).get('orderid')}")
                return True
            else:
                print(f"❌ Failed to place sell order: {response_data.get('message')}")
                return False
        except Exception as e:
            print(f"⚠ Error placing sell order: {str(e)}")
            return False

    def apply_trading_strategy(df, trading_symbol, quantity=1):
        global active_position, entry_price, stop_loss, take_profit
        
        if df is None or df.empty or 'signal' not in df.columns:
            print("❌ No data available for strategy application")
            return
        
        # Get the latest candle
        latest_candle = df.iloc[-1]
        current_signal = latest_candle['signal']
        signal_changed = latest_candle.get('signal_change', False)
        
        # Print current timestamp and candle info for debugging
        print(f"📊 Current candle time: {latest_candle.name}, Signal: {current_signal}, Changed: {signal_changed}")
        
        # If signal changed in the latest candle, take action
        if signal_changed:
            # Close any existing position first
            if active_position == "long":
                print(f"🔄 Closing long position at {latest_candle['close']} at {latest_candle.name}")
                execute_sell_order(trading_symbol, quantity)
                active_position = None
            elif active_position == "short":
                print(f"🔄 Closing short position at {latest_candle['close']} at {latest_candle.name}")
                execute_buy_order(trading_symbol, quantity)
                active_position = None
            
            # Open new position based on signal
            if current_signal == 'buy' and active_position is None:
                entry_price = latest_candle['close']
                # Calculate stop loss (lowest low of last 3 candles or 2% below entry)
                if len(df) >= 3:
                    stop_loss = df['low'].iloc[-3:].min()
                else:
                    stop_loss = entry_price * 0.98
                
                # Calculate take profit (1:2 risk-reward)
                risk = entry_price - stop_loss
                take_profit = entry_price + (2 * risk)
                
                print(f"📈 Opening buy position at {entry_price}, SL: {stop_loss}, TP: {take_profit} at {latest_candle.name}")
                execute_buy_order(trading_symbol, quantity)
                active_position = "long"
            
            elif current_signal == 'sell' and active_position is None:
                entry_price = latest_candle['close']
                # Calculate stop loss (highest high of last 3 candles or 2% above entry)
                if len(df) >= 3:
                    stop_loss = df['high'].iloc[-3:].max()
                else:
                    stop_loss = entry_price * 1.02
                
                # Calculate take profit (1:2 risk-reward)
                risk = stop_loss - entry_price
                take_profit = entry_price - (2 * risk)
                
                print(f"📉 Opening sell position at {entry_price}, SL: {stop_loss}, TP: {take_profit} at {latest_candle.name}")
                execute_sell_order(trading_symbol, quantity)
                active_position = "short"
        
        # Check for stop loss or take profit hits on existing positions
        elif active_position is not None:
            if active_position == "long":
                # Check for stop loss
                if latest_candle['low'] <= stop_loss:
                    print(f"❌ Stop loss hit on long position at {stop_loss} at {latest_candle.name}")
                    execute_sell_order(trading_symbol, quantity)
                    active_position = None
                # Check for take profit
                elif latest_candle['high'] >= take_profit:
                    print(f"💰 Take profit hit on long position at {take_profit} at {latest_candle.name}")
                    execute_sell_order(trading_symbol, quantity)
                    active_position = None
            
            elif active_position == "short":
                # Check for stop loss
                if latest_candle['high'] >= stop_loss:
                    print(f"❌ Stop loss hit on short position at {stop_loss} at {latest_candle.name}")
                    execute_buy_order(trading_symbol, quantity)
                    active_position = None
                # Check for take profit
                elif latest_candle['low'] <= take_profit:
                    print(f"💰 Take profit hit on short position at {take_profit} at {latest_candle.name}")
                    execute_buy_order(trading_symbol, quantity)
                    active_position = None

    def is_market_open():
        now = datetime.datetime.now()
        current_time = now.time()
        
        # Check if it's a weekday (0-4 are Monday to Friday)
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check if current time is between 9:15 AM and 3:30 PM
        market_start = datetime.time(9, 15)
        market_end = datetime.time(15, 30)
        
        return market_start <= current_time <= market_end
    
    def main():
        
        global CANDLE_SIZE, stop_flag
       
        # Login to Angel One
        if not login_to_angel_one():
            print("Exiting due to login failure")
            return
       
        # Set trading parameters
        # symbol_token = "3045"  # Reliance
        # exchange = "NSE"
        # quantity = 1
       
        # You can change candle size here
        # CANDLE_SIZE = "FIVE_MINUTE"  # Uncomment to change from default
       
       
        # Fetch historical data for initial Supertrend calculation
        historical_df = fetch_historical_stock_data(symbol_token, exchange)
       
        # Initialize live data with historical data
        live_df = historical_df.copy() if historical_df is not None else pd.DataFrame()
       
        # Calculate initial Supertrend
        if not live_df.empty:
            live_df = calculate_supertrend(live_df)
            print("Initial Supertrend calculated")
           
            # Plot initial chart
            plot_data_with_supertrend(live_df)
       
        # Trading loop
        print("Starting live trading session...")
        try:
            while not stop_flag: #Exit when stop_flag is set to True
                # Check if market is open - Uncomment for production use
                #if not is_market_open():
                    #print(f"Market is closed at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. Waiting...")
                    #time.sleep(300)  # Wait 5 minutes before checking again
                    #continue
               
                # Fetch latest live data
                new_data = fetch_live_stock_data(symbol_token, exchange)
               
                if new_data is not None and not new_data.empty:
                    # Debug information before update
                    debug_dataframe(live_df, "Before Update")
                    debug_dataframe(new_data, "New Data")
                   
                    # Update our dataset - only keep OHLCV data
                    live_df = update_live_data(live_df, new_data)
                   
                    # Debug information after update
                    debug_dataframe(live_df, "After Update")
                   
                    # Recalculate Supertrend with updated data
                    if not live_df.empty:
                        live_df = calculate_supertrend(live_df)
                       
                        if 'SUPERT_10_2.0' in live_df.columns:
                            # Apply trading strategy based on Supertrend signals
                            print(f'The Symbol Token:{trading_symbol}')
                            apply_trading_strategy(live_df, trading_symbol, quantity)
                           
                            # Plot updated chart every 5 minutes
                            if datetime.datetime.now().minute % 5 == 0:
                                plot_data_with_supertrend(live_df)
                        else:
                            print("⚠ Supertrend indicator not available in dataframe")
               
                # Wait for 1 minute before next update
                print(f"Waiting for next update... (Current time: {datetime.datetime.now().strftime('%H:%M:%S')})")
                time.sleep(60)
 
                #Check stop flag before looping
                print(stop_flag)
                if stop_flag:
                    print("Gracefully stopping trading...")
                    break
               
        except KeyboardInterrupt:
            print("\nTrading session ended by user.")
        except Exception as e:
            print(f"⚠ Error in trading loop: {str(e)}")
            import traceback
            traceback.print_exc()  # Print the full traceback for debugging
        finally:
            # Plot final chart
            if 'live_df' in locals() and not live_df.empty:
                try:
                    live_df = calculate_supertrend(live_df)
                    if 'SUPERT_10_2.0' in live_df.columns:
                        plot_data_with_supertrend(live_df)
                except Exception as e:
                    print(f"⚠ Error plotting final chart: {str(e)}")
            logout_from_angel_one()  # Ensure safe logout before stopping
            print("Trading session ended.")
                
    main()