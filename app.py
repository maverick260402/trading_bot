from flask import Flask, request, jsonify, session,render_template
import threading
from Live_trading_with_Supertrend_ultra_final_lite import topgun
from flask_cors import CORS
import os
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for cross-origin requests
global stop_flag
# stop_flag = False 

# Function to start trading in a separate thread
def start_trading(trading_symbol, symbol_token, exchange, quantity,):
    global stop_flag
 # Reset stop flag when starting
    stop_flag = False
    trade_thread = threading.Thread(target=topgun, args=(trading_symbol, symbol_token, exchange, quantity))
    trade_thread.start()
    return trade_thread

app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")  # Replace with a secure key

# Dummy credentials (replace with a database in production)
USERNAME = os.getenv("USERNAMEE", "topgun")
PASSWORD = os.getenv("PASSWORD", "maverick")
@app.route('/')
def index():
    return render_template('index.html')
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    print(username)
    print(USERNAME)
    print(password)
    print(PASSWORD)

    if username == USERNAME and password == PASSWORD:
        session['user'] = username  # Store user in session
        return jsonify({"message": "Login successful", "token": "dummy_token"}), 200
    else:
        return jsonify({"message": "Invalid credentials"}), 401

@app.route('/dashboard', methods=['GET'])
def dashboard():
    if 'user' in session:
        return jsonify({"message": f"Welcome {session['user']} to the dashboard!"}), 200
    else:
        return jsonify({"message": "Unauthorized"}), 401

@app.route("/apply_supertrend", methods=["POST"])
def apply_supertrend():
    """API endpoint to trigger the Supertrend calculation."""
    global stop_flag
    
    try:
        # Ensure the request contains JSON
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400

        # Get JSON data
        data = request.get_json()

        # Extract data from the frontend payload
        trading_symbol = data.get("tradingsymbol")
        symbol_token = data.get("symboltoken")
        exchange = data.get("exchange", "NSE")
        quantity = data.get("quantity")

        # Validate required fields
        if not all([trading_symbol, symbol_token, quantity]):
            return jsonify({"error": "Missing required parameters"}), 400

        # Run the trading function in a separate thread
        # thread = threading.Thread(target=topgun, args=(trading_symbol, symbol_token, exchange, quantity))
        # thread.start()
        start_trading(trading_symbol, symbol_token, exchange, quantity)

        return jsonify({
            "message": "Supertrend strategy applied successfully",
            "trading_symbol": trading_symbol,
            "symbol_token": symbol_token
        }), 200

    except Exception as e:
        print(f"Error in apply_supertrend: {str(e)}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route("/stop_supertrend", methods=["POST"])
def stop_supertrend():

    #Still pending to put logic inside this api, which can break the running topgun() function.??
    """Stop the currently running trade."""
    global stop_flag
    stop_flag = True  # Set flag to stop the running trade
    return jsonify({"message": "Supertrend trading stopped"}), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)  # Changed port to avoid conflict
