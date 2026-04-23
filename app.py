from flask import Flask, request, redirect, session, render_template_string
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "secure123"

DB = "hostel.db"

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # bookings (نسخه ارتقا یافته بدون حذف قابلیت قبلی)
    c.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY,
        room TEXT,
        bed INTEGER,
        name TEXT,
        days INTEGER,
        paid INTEGER,
        total INTEGER,
        date TEXT,
        whatsapp TEXT DEFAULT ''
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY,
        title TEXT,
        amount INTEGER,
        date TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= AUTH =================
USER = "nima"
PASS = "nima1234"

# ================= ROOMS (OLD + COMPATIBLE) =================
rooms = [
    {"id": 1, "name": "اتاق ۱ (۴ تخته)", "capacity": 4, "base_price": 3000, "room_type": "اشتراکی"},
    {"id": 2, "name": "اتاق ۲ (خصوصی)", "capacity": 1, "base_price": 180000, "room_type": "خصوصی"},
    {"id": 3, "name": "اتاق ۳ (۱۰ تخته)", "capacity": 10, "base_price": 2500, "room_type": "اشتراکی"},
    {"id": 4, "name": "اتاق ۴ (۶ تخته)", "capacity": 6, "base_price": 3500, "room_type": "اشتراکی"},
]

# ================= LOGIN UI =================
login_html = """
<h2>ورود</h2>
<form method="POST">
<input name="username" placeholder="user"><br>
<input name="password" type="password" placeholder="pass"><br>
<button>ورود</button>
</form>
"""

# ================= DASHBOARD (UI PRO VERSION) =================
dashboard_html = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>Hostel Pro</title>

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

<style>
body { background:#f8fafc; font-family:tahoma; }

.sidebar {
    width:260px; height:100vh; position:fixed; right:0;
    background:white; padding:20px;
}

.main { margin-right:260px; padding:30px; }

.room {
    background:white; padding:20px;
    border-radius:20px; margin-bottom:20px;
}

.bed {
    width:120px; height:140px;
    border:2px dashed #ccc;
    border-radius:15px;
    display:inline-block;
    margin:10px;
    text-align:center;
    padding-top:20px;
}

.bed.filled { border:2px solid #4cc9f0; background:#eef7ff; }
.bed.debt { border-color:red; }
.bed.credit { border-color:green; }

.whatsapp {
    background:#25d366;
    color:white;
    padding:3px 8px;
    border-radius:50%;
    text-decoration:none;
}
</style>
</head>

<body>

<div class="sidebar">
<h3>HOSTEL PRO</h3>
<hr>
<a href="/dashboard">داشبورد</a><br>
<a href="/report">گزارش</a><br>
<a href="/logout">خروج</a>
</div>

<div class="main">

<h2>داشبورد هاستل</h2>
<hr>

{% for room in rooms %}
<div class="room">

<h4>{{room.name}} | {{room.base_price}} تومان</h4>

{% for i in range(room.capacity) %}
    {% set found = None %}

    {% for b in bookings %}
        {% if b[1]==room.name and b[2]==i %}
            {% set found = b %}
        {% endif %}
    {% endfor %}

    {% if found %}
        {% set balance = found[6] - found[5] %}

        <div class="bed filled {% if balance>0 %}credit{% elif balance<0 %}debt{% endif %}">
            <b>{{found[3]}}</b><br>
            بدهی: {{balance}}<br>

            <a href="/checkout/{{found[0]}}" style="color:red;">خروج</a><br>

            <a class="whatsapp"
               href="https://wa.me/{{found[8]}}">
               📞
            </a>
        </div>

    {% else %}
        <form method="POST" action="/add" style="display:inline-block">
            <input type="hidden" name="room" value="{{room.name}}">
            <input type="hidden" name="bed" value="{{i}}">
            <input name="name" placeholder="نام">
            <input name="days" placeholder="روز">
            <input name="paid" placeholder="پرداخت">
            <input name="whatsapp" placeholder="واتساپ">
            <button>ثبت</button>
        </form>
    {% endif %}

{% endfor %}

</div>
{% endfor %}

<h3>هزینه</h3>
<form method="POST" action="/expense">
<input name="title" placeholder="عنوان">
<input name="amount" placeholder="مبلغ">
<button>ثبت</button>
</form>

</div>
</body>
</html>
"""

# ================= ROUTES =================

@app.route("/", methods=["GET","POST"])
def login():
    if request.method=="POST":
        if request.form["username"]==USER and request.form["password"]==PASS:
            session["login"]=True
            return redirect("/dashboard")
    return render_template_string(login_html)


@app.route("/dashboard")
def dash():
    if not session.get("login"):
        return redirect("/")

    conn=sqlite3.connect(DB)
    bookings=conn.execute("SELECT * FROM bookings").fetchall()
    conn.close()

    return render_template_string(dashboard_html,rooms=rooms,bookings=bookings)


@app.route("/add", methods=["POST"])
def add():
    room=request.form["room"]
    bed=int(request.form["bed"])
    name=request.form["name"]
    days=int(request.form["days"])
    paid=int(request.form["paid"])
    whatsapp=request.form.get("whatsapp","")

    room_data=next(r for r in rooms if r["name"]==room)
    total=days*room_data["base_price"]

    conn=sqlite3.connect(DB)
    conn.execute("""
    INSERT INTO bookings
    (room,bed,name,days,paid,total,date,whatsapp)
    VALUES (?,?,?,?,?,?,?,?)
    """,(room,bed,name,days,paid,total,str(datetime.now()),whatsapp))

    conn.commit()
    conn.close()

    return redirect("/dashboard")


@app.route("/checkout/<int:id>")
def checkout(id):
    conn=sqlite3.connect(DB)
    conn.execute("DELETE FROM bookings WHERE id=?",(id,))
    conn.commit()
    conn.close()
    return redirect("/dashboard")


@app.route("/expense", methods=["POST"])
def expense():
    conn=sqlite3.connect(DB)
    conn.execute("INSERT INTO expenses(title,amount,date) VALUES (?,?,?)",
                 (request.form["title"],request.form["amount"],str(datetime.now())))
    conn.commit()
    conn.close()
    return redirect("/dashboard")


@app.route("/report")
def report():
    conn=sqlite3.connect(DB)
    bookings=conn.execute("SELECT * FROM bookings").fetchall()
    expenses=conn.execute("SELECT * FROM expenses").fetchall()
    conn.close()

    income=sum(b[5] for b in bookings)
    cost=sum(e[2] for e in expenses)

    return f"""
    <h2>گزارش</h2>
    درآمد: {income}<br>
    هزینه: {cost}<br>
    سود: {income-cost}
    """


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= RUN =================
if __name__ == "__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
