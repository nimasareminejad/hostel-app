# ================= IMPORTS =================
from flask import Flask, request, redirect, session, render_template_string, jsonify
import sqlite3
from datetime import datetime, date, timedelta

app = Flask(__name__)
app.secret_key = "fin-tech-pro"
DB = "hostel_pro.db"

# ================= DATABASE =================

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    db = get_db()
    c = db.cursor()

    # Rooms
    c.execute("""
    CREATE TABLE IF NOT EXISTS rooms(
        id INTEGER PRIMARY KEY,
        name TEXT,
        capacity INTEGER,
        base_price INTEGER,
        room_type TEXT
    )
    """)

    # Bookings
    c.execute("""
    CREATE TABLE IF NOT EXISTS bookings(
        id INTEGER PRIMARY KEY,
        room_id INTEGER,
        bed_number INTEGER,
        customer_name TEXT,
        phone TEXT,
        checkin_date TEXT,
        checkout_date TEXT,
        pricing_type TEXT,
        daily_rate INTEGER,
        is_active INTEGER DEFAULT 1,
        last_charge_date TEXT
    )
    """)

    # Transactions (Ledger)
    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY,
        booking_id INTEGER,
        type TEXT,
        amount INTEGER,
        date TEXT,
        description TEXT
    )
    """)

    # Expenses
    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY,
        title TEXT,
        amount INTEGER,
        category TEXT,
        date TEXT
    )
    """)

    # Default rooms
    if c.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0:
        rooms = [
            ("VIP", 1, 180000, "خصوصی"),
            ("عمومی", 4, 35000, "عمومی"),
            ("اقتصادی", 8, 25000, "اقتصادی"),
            ("اتاق دختران", 4, 40000, "دختران"),
            ("اتاق پسران", 4, 40000, "پسران"),
        ]
        c.executemany("INSERT INTO rooms(name,capacity,base_price,room_type) VALUES (?,?,?,?)", rooms)

    db.commit()
    db.close()

init_db()

# ================= ACCOUNTING ENGINE =================

def calculate_daily_charge(booking):
    if booking["pricing_type"] == "monthly":
        return int(booking["daily_rate"] / 30)
    return booking["daily_rate"]


def sync_daily_charges():
    db = get_db()
    today = date.today()

    bookings = db.execute("SELECT * FROM bookings WHERE is_active=1").fetchall()

    for b in bookings:
        last = datetime.strptime(b["last_charge_date"], "%Y-%m-%d").date()

        days = (today - last).days

        for i in range(1, days + 1):
            charge_day = last + timedelta(days=i)

            # جلوگیری از شارژ بعد از خروج
            if b["checkout_date"]:
                checkout = datetime.strptime(b["checkout_date"], "%Y-%m-%d").date()
                if charge_day > checkout:
                    continue

            amount = calculate_daily_charge(b)

            db.execute("""
            INSERT INTO transactions(booking_id,type,amount,date,description)
            VALUES (?,?,?,?,?)
            """, (
                b["id"],
                "charge",
                amount,
                str(charge_day),
                f"شارژ روز {charge_day}"
            ))

        db.execute("UPDATE bookings SET last_charge_date=? WHERE id=?",
                   (str(today), b["id"]))

    db.commit()
    db.close()


def get_balance(bid):
    db = get_db()

    charge = db.execute(
        "SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'",
        (bid,)
    ).fetchone()[0] or 0

    pay = db.execute(
        "SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'",
        (bid,)
    ).fetchone()[0] or 0

    db.close()
    return charge - pay


# ================= HELPERS =================

def get_days_left(booking):
    if not booking["checkout_date"]:
        return None

    checkout = datetime.strptime(booking["checkout_date"], "%Y-%m-%d").date()
    return (checkout - date.today()).days


def get_payment_total(bid):
    db = get_db()
    val = db.execute(
        "SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'",
        (bid,)
    ).fetchone()[0] or 0
    db.close()
    return val


# ================= AUTH =================

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["u"] == "admin" and request.form["p"] == "admin123":
            session["login"] = True
            return redirect("/dashboard")

    return """
    <form method="POST" style="text-align:center;margin-top:100px">
        <input name="u" placeholder="user"><br><br>
        <input name="p" type="password" placeholder="pass"><br><br>
        <button>Login</button>
    </form>
    # ================= DASHBOARD =================

@app.route("/dashboard")
def dashboard():
    if not session.get("login"):
        return redirect("/")

    sync_daily_charges()

    db = get_db()

    rooms = [dict(r) for r in db.execute("SELECT * FROM rooms").fetchall()]
    bookings = [dict(b) for b in db.execute("SELECT * FROM bookings WHERE is_active=1").fetchall()]

    total_beds = sum(r["capacity"] for r in rooms)
    occupied = len(bookings)

    # attach booking to beds
    for r in rooms:
        r["beds"] = []
        for i in range(1, r["capacity"] + 1):
            b = next((x for x in bookings if x["room_id"] == r["id"] and x["bed_number"] == i), None)

            if b:
                b["balance"] = get_balance(b["id"])
                b["paid"] = get_payment_total(b["id"])
                b["days_left"] = get_days_left(b)
                r["beds"].append({"status": "full", "data": b})
            else:
                r["beds"].append({"status": "empty", "bed": i})

    db.close()

    return render_template_string(DASHBOARD_HTML,
                                  rooms=rooms,
                                  total=total_beds,
                                  occupied=occupied,
                                  empty=total_beds - occupied)


# ================= API =================

@app.route("/api/booking/<int:bid>")
def booking_api(bid):
    db = get_db()

    b = dict(db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())

    tx = [dict(t) for t in db.execute("""
        SELECT * FROM transactions
        WHERE booking_id=?
        ORDER BY date DESC
    """, (bid,)).fetchall()]

    db.close()

    return jsonify({
        "booking": b,
        "transactions": tx,
        "balance": get_balance(bid),
        "paid": get_payment_total(bid)
    })


# ================= ACTIONS =================

@app.route("/action/checkin", methods=["POST"])
def checkin():
    db = get_db()
    today = str(date.today())

    cur = db.execute("""
    INSERT INTO bookings(
        room_id,bed_number,customer_name,phone,
        checkin_date,checkout_date,pricing_type,
        daily_rate,last_charge_date
    ) VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        request.form["room_id"],
        request.form["bed"],
        request.form["name"],
        request.form["phone"],
        today,
        request.form.get("checkout"),
        request.form["type"],
        request.form["rate"],
        today
    ))

    bid = cur.lastrowid

    # prepayment
    pay = int(request.form.get("payment", 0))
    if pay > 0:
        db.execute("""
        INSERT INTO transactions(booking_id,type,amount,date,description)
        VALUES (?,?,?,?,?)
        """, (bid, "payment", pay, today, "پیش پرداخت"))

    db.commit()
    db.close()
    return redirect("/dashboard")


@app.route("/action/payment", methods=["POST"])
def payment():
    db = get_db()

    db.execute("""
    INSERT INTO transactions(booking_id,type,amount,date,description)
    VALUES (?,?,?,?,?)
    """, (
        request.form["bid"],
        "payment",
        request.form["amount"],
        str(date.today()),
        request.form.get("desc", "پرداخت")
    ))

    db.commit()
    db.close()
    return redirect("/dashboard")


@app.route("/action/checkout/<int:bid>")
def checkout(bid):
    db = get_db()

    db.execute("""
    UPDATE bookings
    SET is_active=0, checkout_date=?
    WHERE id=?
    """, (str(date.today()), bid))

    db.commit()
    db.close()
    return redirect("/dashboard")


@app.route("/action/extend", methods=["POST"])
def extend():
    db = get_db()

    bid = request.form["bid"]
    days = int(request.form["days"])

    b = db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone()

    if b["checkout_date"]:
        base = datetime.strptime(b["checkout_date"], "%Y-%m-%d").date()
    else:
        base = date.today()

    new_date = base + timedelta(days=days)

    db.execute("UPDATE bookings SET checkout_date=? WHERE id=?",
               (str(new_date), bid))

    db.commit()
    db.close()
    return redirect("/dashboard")


# ================= UI =================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html dir="rtl">
<head>
<meta charset="UTF-8">
<title>ERP</title>
<style>
body{font-family:tahoma;background:#f5f5f5;padding:20px}
.card{background:white;padding:15px;margin:10px;border-radius:10px}
.bed{display:inline-block;width:140px;height:140px;margin:5px;padding:10px;border-radius:10px;cursor:pointer}
.empty{background:#eee}
.full{background:#d1e7ff}
.debt{color:red}
.ok{color:green}
</style>
</head>
<body>

<h2>داشبورد</h2>

<div class="card">
کل تخت: {{total}} |
پر: {{occupied}} |
خالی: {{empty}}
<a href="/report">📄 گزارش</a>
</div>

{% for r in rooms %}
<div class="card">
<h3>{{r.name}}</h3>

{% for b in r.beds %}
    {% if b.status=="empty" %}
        <div class="bed empty" onclick="checkin({{r.id}},{{b.bed}})">
        تخت {{b.bed}}<br>خالی
        </div>
    {% else %}
        <div class="bed full" onclick="ledger({{b.data.id}})">
        {{b.data.customer_name}}<br>
        {% if b.data.balance>0 %}
            <span class="debt">{{b.data.balance}}</span>
        {% else %}
            <span class="ok">تسویه</span>
        {% endif %}
        <br>
        {{b.data.days_left if b.data.days_left!=None else ''}}
        </div>
    {% endif %}
{% endfor %}

</div>
{% endfor %}

<!-- CHECKIN -->
<div id="checkinBox" style="display:none">
<form method="POST" action="/action/checkin">
<input name="room_id" id="r">
<input name="bed" id="b">
<input name="name" placeholder="نام"><br>
<input name="phone" placeholder="شماره"><br>
<input name="rate" placeholder="نرخ"><br>
<select name="type">
<option value="daily">روزانه</option>
<option value="monthly">ماهانه</option>
</select><br>
<input name="checkout" placeholder="تاریخ خروج"><br>
<input name="payment" placeholder="پیش پرداخت"><br>
<button>ثبت</button>
</form>
</div>

<!-- LEDGER -->
<div id="ledgerBox"></div>

<script>
function checkin(r,b){
    document.getElementById("checkinBox").style.display="block"
    document.getElementById("r").value=r
    document.getElementById("b").value=b
}

async function ledger(id){
    let res = await fetch("/api/booking/"+id)
    let data = await res.json()

    let html = `
    <div class="card">
    <h3>${data.booking.customer_name}</h3>
    مانده: ${data.balance}<br>
    پرداختی: ${data.paid}<br>

    <form method="POST" action="/action/payment">
        <input name="bid" value="${id}">
        <input name="amount" placeholder="مبلغ">
        <button>ثبت پرداخت</button>
    </form>

    <form method="POST" action="/action/extend">
        <input name="bid" value="${id}">
        <input name="days" placeholder="روز تمدید">
        <button>تمدید</button>
    </form>

    <a href="/action/checkout/${id}">خروج</a>

    <hr>
    ${data.transactions.map(t=>`
        <div>${t.date} | ${t.type} | ${t.amount}</div>
    `).join("")}
    </div>
    `

    document.getElementById("ledgerBox").innerHTML = html
}
</script>

</body>
</html>
# ================= REPORT (MANAGEMENT) =================

@app.route("/report")
def report():
    if not session.get("login"):
        return redirect("/")

    db = get_db()

    # data
    rows = db.execute("""
    SELECT 
        b.id,
        b.customer_name,
        b.checkin_date,
        b.checkout_date,
        b.daily_rate,
        b.pricing_type,
        r.name as room_name,
        r.capacity,
        b.bed_number
    FROM bookings b
    JOIN rooms r ON r.id = b.room_id
    ORDER BY b.checkin_date DESC
    """).fetchall()

    # stats
    total_beds = db.execute("SELECT SUM(capacity) FROM rooms").fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM bookings WHERE is_active=1").fetchone()[0]

    # enrich data
    final = []
    total_paid_all = 0
    total_debt_all = 0

    for r in rows:
        paid = get_payment_total(r["id"])
        bal = get_balance(r["id"])

        total_paid_all += paid
        if bal > 0:
            total_debt_all += bal

        final.append({
            "name": r["customer_name"],
            "room": r["room_name"],
            "bed": r["bed_number"],
            "checkin": r["checkin_date"],
            "checkout": r["checkout_date"] or "-",
            "rate": r["daily_rate"],
            "type": r["pricing_type"],
            "paid": paid,
            "balance": bal
        })

    db.close()

    return render_template_string(REPORT_HTML,
                                  data=final,
                                  total=total_beds,
                                  active=active,
                                  empty=total_beds - active,
                                  total_paid=total_paid_all,
                                  total_debt=total_debt_all,
                                  now=datetime.now().strftime("%Y-%m-%d %H:%M"))


# ================= REPORT UI =================

REPORT_HTML = """
<!DOCTYPE html>
<html dir="rtl">
<head>
<meta charset="UTF-8">
<title>گزارش مدیریتی</title>

<style>
body{
    font-family:tahoma;
    background:white;
    padding:40px;
}

h1,h2,h3{
    margin:5px 0;
}

.header{
    text-align:center;
    margin-bottom:30px;
}

.stats{
    display:flex;
    justify-content:space-between;
    margin-bottom:20px;
}

.stat{
    border:1px solid #ccc;
    padding:10px;
    border-radius:8px;
    width:23%;
    text-align:center;
}

table{
    width:100%;
    border-collapse:collapse;
    margin-top:20px;
}

th,td{
    border:1px solid #ccc;
    padding:8px;
    text-align:center;
    font-size:13px;
}

th{
    background:#f0f0f0;
}

.debt{color:red;font-weight:bold}
.ok{color:green}

.footer{
    margin-top:30px;
    text-align:left;
    font-size:12px;
}

/* PRINT STYLE */
@media print{
    body{padding:10px}
    .no-print{display:none}
}
</style>
</head>

<body>

<div class="header">
    <h1>گزارش مدیریتی هاستل</h1>
    <small>تاریخ: {{now}}</small>
</div>

<div class="stats">
    <div class="stat">کل تخت<br><b>{{total}}</b></div>
    <div class="stat">پر<br><b>{{active}}</b></div>
    <div class="stat">خالی<br><b>{{empty}}</b></div>
    <div class="stat">کل دریافتی<br><b>{{"{:,}".format(total_paid)}}</b></div>
</div>

<div class="stats">
    <div class="stat" style="width:100%">
        کل بدهکاران<br>
        <b style="color:red">{{"{:,}".format(total_debt)}}</b>
    </div>
</div>

<table>
<tr>
<th>نام</th>
<th>اتاق</th>
<th>تخت</th>
<th>ورود</th>
<th>خروج</th>
<th>نرخ</th>
<th>نوع</th>
<th>پرداختی</th>
<th>مانده</th>
</tr>

{% for r in data %}
<tr>
<td>{{r.name}}</td>
<td>{{r.room}}</td>
<td>{{r.bed}}</td>
<td>{{r.checkin}}</td>
<td>{{r.checkout}}</td>
<td>{{r.rate}}</td>
<td>{{r.type}}</td>
<td>{{"{:,}".format(r.paid)}}</td>
<td>
    {% if r.balance>0 %}
        <span class="debt">{{"{:,}".format(r.balance)}}</span>
    {% else %}
        <span class="ok">تسویه</span>
    {% endif %}
</td>
</tr>
{% endfor %}

</table>

<div class="footer">
    امضا مدیر: ______________________
</div>

<script>
window.print()
</script>

</body>
</html>
