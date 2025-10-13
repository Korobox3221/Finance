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

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


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
    unique_stocks = db.execute("SELECT unique_stocks from portfolio where unique_stocks is not null and stock_buyer == (?)",name)
    stocks = []
    counter = 0
    for stock in unique_stocks:
        stocks.append(stock["unique_stocks"])
    for stock in stocks:
        if db.execute("SELECT SUM(shares) from portfolio  where stock_symbol == (?) and stock_buyer == (?)", stock, name )[counter]["SUM(shares)"] == 0:
            stocks.remove(stock)
    changed = []
    for price in stocks:
        changed.append(lookup(price))
    prices = []
    for i in changed:
        prices.append(usd(i["price"]))
    shares = []
    for stock in stocks:
        shares.append(db.execute("SELECT SUM(shares) from portfolio  where stock_symbol == (?) and stock_buyer == (?)", stock, name )[counter]["SUM(shares)"])
    total = []
    for stock in stocks:
        total.append(usd(db.execute("SELECT SUM(price) from portfolio  where stock_symbol == (?) and stock_buyer == (?)", stock, name )[counter]["SUM(price)"]))
    all_total = db.execute("SELECT SUM(price) from portfolio where stock_buyer == (?)", name)[0]["SUM(price)"]
    if all_total == None:
        all_total = 0
    cash = db.execute("SELECT cash from users where username == (?)", name)[0]["cash"]
    all_total =  usd((int(all_total) + cash))
    cash = usd(cash)
    return render_template("index.html",stocks = stocks, prices = prices, shares = shares, total = total, all_total = all_total, cash = cash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide stock name", 400)
        elif not request.form.get("shares"):
            return apology("must provide number of shares", 400)
        elif  lookup(request.form.get("symbol")) == None:
            return apology("invalid stock symbol", 400)
        elif request.form.get("shares").isnumeric() == False:
            return apology("unacceptable number of shares", 400)
        stock_sym = request.form.get("symbol")
        unique_stocks = db.execute("SELECT unique_stocks FROM portfolio")
        shares = request.form.get("shares")
        price = float(lookup(stock_sym)["price"]) * float(shares)
        stock_name = lookup(stock_sym)["symbol"]
        time = (db.execute("SELECT DATETIME('now')"))[0]["DATETIME('now')"]
        for i in unique_stocks:
            if i["unique_stocks"] == stock_name:
                stock_name = None
        else:
            name = session.get("name")
            cash = (db.execute("SELECT cash from users where username == (?)", name))[0]["cash"]
            if cash < price:
                return apology("No enough money for the stock", 403)
            change = int(cash - price)
            db.execute("UPDATE users SET cash = (?)  where username == (?)",change, name)
            db.execute("INSERT INTO portfolio(stock_buyer, stock_symbol, shares, price, time, unique_stocks) VALUES(?,?,?,?,?,?)", name, stock_sym, shares, price, time, stock_name)
            return redirect("/")

    return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    name = session.get("name")
    stocks = db.execute("SELECT stock_symbol,shares,price,time from portfolio where stock_buyer == (?)",name)
    prices = db.execute("SELECT price from portfolio where stock_buyer == (?)",name)
    dollars = []
    for price in prices:
        dollars.append(usd(abs(price["price"])))


    return render_template("history.html", stocks = stocks, dollars = dollars)


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
        names = db.execute("SELECT username FROM users")
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("password and confirmation don't match", 400)
        for i in names:
            if i["username"] == request.form.get("username"):
                return apology("the username already taken", 400)


        password =  request.form.get("password")
        username = request.form.get("username")
        db.execute("INSERT INTO users(username, hash) VALUES(?,?)", username, generate_password_hash(password))

    return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    name = session.get("name")
    stocks = []
    old_unique = db.execute("SELECT unique_stocks from portfolio where unique_stocks is not null and stock_buyer == (?)",name)
    for stock in old_unique:
        stocks.append(stock["unique_stocks"])
    if request.method == "POST":
        if not request.form.get("symbol"):
                return apology("must provide stock name", 400)

        elif not request.form.get("shares"):
                return apology("must provide number of shares", 400)

        elif  lookup(request.form.get("symbol")) == None:
                return apology("invalid stock symbol", 400)
        elif int(request.form.get("shares")) <= 0:
                return apology("unacceptable number of shares", 400)
        stock_sym = request.form.get("symbol")
        shares = request.form.get("shares")
        if int(shares) > int(db.execute("SELECT SUM(shares) FROM portfolio where stock_buyer == (?) and stock_symbol == (?)", name, stock_sym )[0]["SUM(shares)"]):
            return apology("Not enough shares", 400)
        time = (db.execute("SELECT DATETIME('now')"))[0]["DATETIME('now')"]
        price = float(lookup(stock_sym)["price"]) * float(shares)
        stock_name = lookup(stock_sym)["symbol"]
        time = (db.execute("SELECT DATETIME('now')"))[0]["DATETIME('now')"]
        unique_stocks = db.execute("SELECT unique_stocks FROM portfolio")
        for i in unique_stocks:
            if i["unique_stocks"] == stock_name:
                stock_name = None
        else:
            cash = (db.execute("SELECT cash from users where username == (?)", name))[0]["cash"]
            change = int(cash + price)
            shares = -int(shares)
            price = -int(price)
            db.execute("UPDATE users SET cash = (?)  where username == (?)",change, name)
            db.execute("INSERT INTO portfolio(stock_buyer, stock_symbol, shares, price, time, unique_stocks) VALUES(?,?,?,?,?,?)", name, stock_sym, shares, price, time, stock_name)

            return redirect("/")

    return render_template("sell.html", stocks = stocks)
@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
        if request.method == "POST":
            if not request.form.get("amount"):
                return apology("must provide withdraw amount", 403)
            name = session.get("name")
            amount = int(request.form.get("amount"))
            cash = (db.execute("SELECT cash from users where username == (?)", name))[0]["cash"]
            if int(amount) > cash:
                return apology("Not enough money to withdraw",403)
            change = int(cash - amount)
            db.execute("UPDATE users SET cash = (?)  where username == (?)",change, name)
            return redirect("/success")
        return render_template("withdraw.html")

@app.route("/success")
@login_required
def success():
    return render_template("success.html")
