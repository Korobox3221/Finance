import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use PostgreSQL database
# The DATABASE_URL environment variable is correctly used here.
db = SQL(os.environ.get('DATABASE_URL'))

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    name = session.get("name")
    
    # ⚠️ FIX: Removed SQLite's "==" in SQL query.
    # The cs50 library handles '?' placeholders correctly for Postgres.
    unique_stocks = db.execute("SELECT DISTINCT stock_symbol FROM portfolio WHERE stock_buyer = ? AND shares > 0", name)
    
    stocks_summary = []
    grand_total = 0

    for item in unique_stocks:
        symbol = item["stock_symbol"]
        
        # Get current shares
        shares_rows = db.execute("SELECT SUM(shares) FROM portfolio WHERE stock_symbol = ? AND stock_buyer = ?", symbol, name)
        shares = shares_rows[0]["SUM(shares)"]
        
        # If shares are zero (or less), skip this stock
        if shares is None or shares <= 0:
            continue
            
        # Lookup current price
        quote = lookup(symbol)
        if quote is None:
            continue # Skip if lookup fails
        
        current_price = quote["price"]
        total_value = current_price * shares
        grand_total += total_value

        stocks_summary.append({
            "symbol": symbol,
            "name": quote["name"],
            "shares": shares,
            "price": usd(current_price),
            "total": usd(total_value)
        })
    
    # Get cash from user's table. Ensure cash is treated as a float/numeric.
    cash_rows = db.execute("SELECT cash FROM users WHERE username = ?", name)
    if not cash_rows:
        return apology("User not found", 400)
        
    cash = float(cash_rows[0]["cash"])
    
    all_total_portfolio = grand_total + cash
    
    return render_template("index.html",
                           stocks_summary=stocks_summary,
                           all_total=usd(all_total_portfolio),
                           cash=usd(cash))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock name", 400)
        
        shares_input = request.form.get("shares")
        if not shares_input or not shares_input.isdigit() or int(shares_input) <= 0:
            return apology("must provide positive whole number of shares", 400)
        
        stock_sym = request.form.get("symbol").upper()
        shares = int(shares_input)
        
        quote = lookup(stock_sym)
        if quote is None:
            return apology("invalid stock symbol", 400)

        price_per_share = quote["price"]
        transaction_cost = price_per_share * shares
        stock_name = quote["symbol"]

        # ⚠️ FIX: Used PostgreSQL's NOW() for timestamp
        time = db.execute("SELECT NOW()")[0]["now"] 
        
        name = session.get("name")
        cash_rows = db.execute("SELECT cash from users where username = ?", name)
        cash = float(cash_rows[0]["cash"])
        
        if cash < transaction_cost:
            return apology("No enough money for the stock", 403)
        
        change = cash - transaction_cost
        
        # Determine unique_stocks value
        # This logic is a bit unusual for a standard portfolio, but preserving its intent.
        # It seems to only set unique_stocks on the *first* buy of a symbol.
        unique_stocks_val = stock_name
        
        # Check if the stock symbol already exists in portfolio for this buyer
        existing_stock = db.execute("SELECT stock_symbol FROM portfolio WHERE stock_symbol = ? AND stock_buyer = ?", stock_name, name)
        if existing_stock:
             unique_stocks_val = None

        db.execute("UPDATE users SET cash = ? where username = ?", change, name)
        db.execute("INSERT INTO portfolio(stock_buyer, stock_symbol, shares, price, time, unique_stocks) VALUES(?,?,?,?,?,?)", name, stock_sym, shares, transaction_cost, time, unique_stocks_val)
        
        flash(f"Successfully bought {shares} shares of {stock_sym}!")
        return redirect("/")

    return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    name = session.get("name")
    
    # ⚠️ FIX: Removed SQLite's "==" in SQL query.
    stocks = db.execute("SELECT stock_symbol, shares, price, time FROM portfolio WHERE stock_buyer = ? ORDER BY time DESC", name)
    
    history_data = []
    for stock in stocks:
        # Note: cash and price are often returned as Decimal/Numeric types by psycopg2
        # Use abs() on the price to correctly show transaction amount
        price_usd = usd(abs(stock["price"]))
        
        # Determine transaction type
        if stock["shares"] > 0:
            stock_type = "BUY"
        else:
            stock_type = "SELL"
            
        history_data.append({
            "symbol": stock["stock_symbol"],
            "shares": abs(stock["shares"]),
            "price_usd": price_usd,
            "time": stock["time"],
            "type": stock_type
        })
        

    return render_template("history.html", stocks=history_data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        session["name"] = rows[0]["username"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    stock = []
    if request.method == "POST":
        search = request.form.get("symbol")
        if  lookup(search) != None:
            stock.append(lookup(search))
            stock[0]["price"] = usd(stock[0]["price"])
            return render_template("stock.html", stock = stock )
        else:
            return apology("no such stock :(",400)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        
        # Query database for all usernames to check for duplicates
        names = db.execute("SELECT username FROM users")
        
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password and confirmation don't match", 400)
            
        # Check if username is already taken
        for i in names:
            if i["username"] == request.form.get("username"):
                return apology("the username already taken", 400)

        password =  request.form.get("password")
        username = request.form.get("username")
        
        # Insert new user
        # Note: The database schema must use SERIAL for the ID column.
        db.execute("INSERT INTO users(username, hash) VALUES(?,?)", username, generate_password_hash(password))

        # Automatically log in the user (optional but good practice)
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        session["user_id"] = rows[0]["id"]
        session["name"] = rows[0]["username"]

        return redirect("/")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    name = session.get("name")
    
    # Select distinct stocks the user currently holds (shares > 0)
    stocks_held = db.execute("SELECT stock_symbol FROM portfolio WHERE stock_buyer = ? GROUP BY stock_symbol HAVING SUM(shares) > 0", name)
    stocks = [row["stock_symbol"] for row in stocks_held]

    if request.method == "POST":
        stock_sym = request.form.get("symbol").upper()
        shares_input = request.form.get("shares")

        if not stock_sym:
            return apology("must provide stock name", 400)
        elif stock_sym not in stocks:
            return apology("you do not hold this stock", 400)
        elif not shares_input or not shares_input.isdigit() or int(shares_input) <= 0:
            return apology("must provide positive whole number of shares", 400)
            
        shares_to_sell = int(shares_input)
        
        # Check current holdings
        shares_held_rows = db.execute("SELECT SUM(shares) FROM portfolio WHERE stock_buyer = ? AND stock_symbol = ?", name, stock_sym)
        shares_held = shares_held_rows[0]["SUM(shares)"]
        
        if shares_held is None or shares_to_sell > shares_held:
            return apology("Not enough shares", 400)
            
        quote = lookup(stock_sym)
        if quote is None:
            return apology("lookup failed for stock", 400)
            
        price_per_share = quote["price"]
        transaction_gain = price_per_share * shares_to_sell
        
        # ⚠️ FIX: Used PostgreSQL's NOW() for timestamp
        time = db.execute("SELECT NOW()")[0]["now"]
        
        # Negate shares and price for the transaction log
        shares_log = -shares_to_sell
        price_log = -transaction_gain
        
        # Update cash
        cash_rows = db.execute("SELECT cash from users where username = ?", name)
        cash = float(cash_rows[0]["cash"])
        change = cash + transaction_gain
        
        db.execute("UPDATE users SET cash = ? where username = ?", change, name)
        
        # Insert transaction log (unique_stocks is set to NULL on SELL transactions)
        db.execute("INSERT INTO portfolio(stock_buyer, stock_symbol, shares, price, time, unique_stocks) VALUES(?,?,?,?,?,NULL)", name, stock_sym, shares_log, price_log, time)

        flash(f"Successfully sold {shares_to_sell} shares of {stock_sym} for {usd(transaction_gain)}!")
        return redirect("/")

    return render_template("sell.html", stocks = stocks)
    
@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
        if request.method == "POST":
            amount_input = request.form.get("amount")
            if not amount_input or not amount_input.isdigit() or int(amount_input) <= 0:
                return apology("must provide a positive whole number amount", 403)
            
            name = session.get("name")
            amount = int(amount_input)
            
            cash_rows = db.execute("SELECT cash from users where username = ?", name)
            cash = float(cash_rows[0]["cash"])
            
            if amount > cash:
                return apology("Not enough money to withdraw",403)
            
            change = cash - amount
            db.execute("UPDATE users SET cash = ? where username = ?",change, name)
            
            flash(f"Successfully withdrew {usd(amount)}!")
            return redirect("/")
            
        return render_template("withdraw.html")