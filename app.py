import os, sqlite3, io, csv
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-development-secret")
DB = os.path.join(os.path.dirname(__file__), "tradenexa.db")

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, company TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, description TEXT, suggested_hs TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY, user_id INTEGER, trade_type TEXT, product TEXT, quantity REAL, unit_price REAL, origin TEXT, destination TEXT, total REAL, created_at TEXT);
        CREATE TABLE IF NOT EXISTS shipments(id INTEGER PRIMARY KEY, user_id INTEGER, tracking TEXT, origin TEXT, destination TEXT, status TEXT, eta TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, user_id INTEGER, doc_type TEXT, reference TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS markets(id INTEGER PRIMARY KEY, user_id INTEGER, product TEXT, country TEXT, rationale TEXT, created_at TEXT);
        """)
init_db()

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name, email, password, company = (request.form.get(k,"").strip() for k in ("name","email","password","company"))
        if not name or not email or len(password) < 8:
            flash("Enter your name, email and a password of at least 8 characters.", "danger")
        else:
            try:
                with db() as con:
                    con.execute("INSERT INTO users(name,email,password,company) VALUES(?,?,?,?)",
                                (name,email,generate_password_hash(password),company))
                flash("Account created. Please sign in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "danger")
    return render_template("auth.html", mode="Register")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE email=?", (request.form.get("email","").strip(),)).fetchone()
        if user and check_password_hash(user["password"], request.form.get("password","")):
            session["user_id"], session["user_name"] = user["id"], user["name"]
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("auth.html", mode="Login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    with db() as con:
        trades = con.execute("SELECT * FROM trades WHERE user_id=? ORDER BY id DESC LIMIT 6",(uid,)).fetchall()
        shipments = con.execute("SELECT * FROM shipments WHERE user_id=? ORDER BY id DESC LIMIT 5",(uid,)).fetchall()
        stats = con.execute("""SELECT
            COALESCE(SUM(CASE WHEN trade_type='Import' THEN total END),0) imports,
            COALESCE(SUM(CASE WHEN trade_type='Export' THEN total END),0) exports,
            COUNT(*) trade_count FROM trades WHERE user_id=?""",(uid,)).fetchone()
    return render_template("dashboard.html", trades=trades, shipments=shipments, stats=stats)

@app.route("/classification", methods=["GET","POST"])
@login_required
def classification():
    result = None
    if request.method == "POST":
        name = request.form.get("name","").strip()
        desc = request.form.get("description","").strip()
        if name:
            result = classify_product(name, desc)
            with db() as con:
                con.execute("INSERT INTO products(user_id,name,description,suggested_hs,created_at) VALUES(?,?,?,?,?)",
                            (session["user_id"],name,desc,result["hs"],datetime.now().isoformat(timespec="seconds")))
    return render_template("classification.html", result=result)

def classify_product(name, desc):
    # Transparent keyword-based demo fallback; not an official HS classification.
    text = (name + " " + desc).lower()
    rules = [
        (["t-shirt","shirt","cotton garment","clothing"],"6109 (indicative)","Knitted or crocheted apparel; exact code depends on material and construction."),
        (["rice"],"1006 (indicative)","Rice; exact subheading depends on processing and variety."),
        (["coffee"],"0901 (indicative)","Coffee; exact subheading depends on roasted/unroasted and decaffeination."),
        (["phone","mobile","smartphone"],"8517 (indicative)","Telephone apparatus; exact subheading depends on device specifications."),
        (["tea"],"0902 (indicative)","Tea; exact subheading depends on packaging and processing."),
    ]
    for words, hs, reason in rules:
        if any(w in text for w in words):
            return {"hs":hs,"reason":reason}
    return {"hs":"Not determined – research required","reason":"No confident demo keyword match. Review the product composition, function and official tariff schedule."}

@app.route("/calculator", methods=["GET","POST"])
@login_required
def calculator():
    result = None
    if request.method == "POST":
        try:
            product=request.form["product"].strip()
            qty=float(request.form["quantity"]); price=float(request.form["unit_price"])
            shipping=float(request.form.get("shipping",0)); insurance=float(request.form.get("insurance",0))
            duty_rate=float(request.form.get("duty_rate",0))
            if not product or min(qty,price,shipping,insurance,duty_rate)<0 or qty<=0:
                raise ValueError()
            goods=qty*price
            assessable=goods+shipping+insurance
            duty=assessable*duty_rate/100
            total=assessable+duty
            result={"goods":goods,"shipping":shipping,"insurance":insurance,"duty":duty,"total":total,"unit":total/qty}
            with db() as con:
                con.execute("INSERT INTO trades(user_id,trade_type,product,quantity,unit_price,origin,destination,total,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (session["user_id"],request.form["trade_type"],product,qty,price,request.form.get("origin",""),request.form.get("destination",""),total,datetime.now().isoformat(timespec="seconds")))
        except (ValueError, KeyError):
            flash("Please enter valid non-negative numbers and a quantity greater than zero.", "danger")
    return render_template("calculator.html", result=result)

@app.route("/markets", methods=["GET","POST"])
@login_required
def markets():
    suggestions = []
    if request.method == "POST":
        product=request.form.get("product","").strip()
        if product:
            # Demo suggestions only. No live trade data is queried.
            suggestions = [
                ("United States","Large, diverse consumer and business market; validate demand and product-specific requirements."),
                ("United Arab Emirates","Regional trading and re-export hub; check local standards and buyer demand."),
                ("Germany","Potential European market; assess applicable EU product, labeling and sustainability rules."),
            ]
            with db() as con:
                for country, rationale in suggestions:
                    con.execute("INSERT INTO markets(user_id,product,country,rationale,created_at) VALUES(?,?,?,?,?)",
                        (session["user_id"],product,country,rationale,datetime.now().isoformat(timespec="seconds")))
    return render_template("markets.html", suggestions=suggestions)

@app.route("/shipments", methods=["GET","POST"])
@login_required
def shipments():
    if request.method == "POST":
        vals=[request.form.get(k,"").strip() for k in ("tracking","origin","destination","status","eta")]
        if all(vals):
            with db() as con:
                con.execute("INSERT INTO shipments(user_id,tracking,origin,destination,status,eta,created_at) VALUES(?,?,?,?,?,?,?)",
                    (session["user_id"],*vals,datetime.now().isoformat(timespec="seconds")))
            flash("Shipment record saved. Status is user-entered demo data, not live carrier tracking.", "success")
        else: flash("Complete all shipment fields.", "danger")
    with db() as con:
        rows=con.execute("SELECT * FROM shipments WHERE user_id=? ORDER BY id DESC",(session["user_id"],)).fetchall()
    return render_template("shipments.html", shipments=rows)

@app.route("/documents", methods=["GET","POST"])
@login_required
def documents():
    if request.method == "POST":
        data={k:request.form.get(k,"").strip() for k in ("doc_type","reference","seller","buyer","product","quantity","unit_price","currency")}
        if not data["reference"] or not data["product"]:
            flash("Reference and product are required.", "danger")
            return render_template("documents.html")
        buffer=io.BytesIO()
        pdf=canvas.Canvas(buffer,pagesize=A4)
        pdf.setTitle(data["doc_type"])
        pdf.setFont("Helvetica-Bold",18); pdf.drawString(50,790,"TradeNexa AI")
        pdf.setFont("Helvetica-Bold",14); pdf.drawString(50,755,data["doc_type"]+" – DRAFT")
        pdf.setFont("Helvetica",10)
        y=720
        for label,key in [("Reference","reference"),("Seller","seller"),("Buyer","buyer"),("Product","product"),("Quantity","quantity"),("Unit price","unit_price"),("Currency","currency")]:
            pdf.drawString(50,y,f"{label}: {data[key]}"); y-=25
        pdf.setFont("Helvetica-Oblique",9)
        pdf.drawString(50,80,"Draft for review only. Verify all legal, customs and commercial details before use.")
        pdf.save(); buffer.seek(0)
        with db() as con:
            con.execute("INSERT INTO documents(user_id,doc_type,reference,created_at) VALUES(?,?,?,?)",
                (session["user_id"],data["doc_type"],data["reference"],datetime.now().isoformat(timespec="seconds")))
        return send_file(buffer,as_attachment=True,download_name="tradenexa_"+data["doc_type"].lower().replace(" ","_")+".pdf",mimetype="application/pdf")
    return render_template("documents.html")

@app.route("/assistant", methods=["GET","POST"])
@login_required
def assistant():
    answer=None
    if request.method=="POST":
        q=request.form.get("question","").strip().lower()
        if any(w in q for w in ["hs code","classification"]):
            answer="HS classification depends on product material, function, composition and tariff rules. Use the classification tool for an indicative suggestion, then verify with the importing country's official tariff schedule or a customs broker."
        elif any(w in q for w in ["duty","customs","tax"]):
            answer="Customs duty varies by importing country, HS code, origin, trade agreements and current rules. Enter a verified duty rate in the calculator; this demo does not fetch official rates."
        elif any(w in q for w in ["invoice","document","packing list"]):
            answer="A commercial invoice describes the seller, buyer, goods, quantity, value, currency and delivery terms. A packing list describes package contents, weights and dimensions. Requirements vary by shipment."
        elif any(w in q for w in ["shipping","freight","shipment"]):
            answer="Compare air, sea and land freight based on cost, transit time, cargo type and route. This demo stores manual shipment updates and does not connect to carrier tracking."
        else:
            answer="I can explain HS classification, customs duty concepts, invoices, packing lists, shipping options and import/export workflows. For country-specific decisions, verify current official rules."
    return render_template("assistant.html", answer=answer)

@app.route("/analytics")
@login_required
def analytics():
    with db() as con:
        rows=con.execute("SELECT trade_type, SUM(total) total FROM trades WHERE user_id=? GROUP BY trade_type",(session["user_id"],)).fetchall()
        recent=con.execute("SELECT trade_type,product,total,created_at FROM trades WHERE user_id=? ORDER BY id DESC LIMIT 12",(session["user_id"],)).fetchall()
    data={r["trade_type"]:r["total"] for r in rows}
    return render_template("analytics.html", imports=data.get("Import",0), exports=data.get("Export",0), recent=recent)

@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    with db() as con:
        if request.method=="POST":
            con.execute("UPDATE users SET name=?,company=? WHERE id=?",(request.form.get("name",""),request.form.get("company",""),session["user_id"]))
            session["user_name"]=request.form.get("name","")
            flash("Profile updated.","success")
        user=con.execute("SELECT name,email,company FROM users WHERE id=?",(session["user_id"],)).fetchone()
    return render_template("profile.html", user=user)

if __name__ == "__main__":
    app.run(debug=True)
