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

# ================= ROOMS =================
rooms = [
    {"name": "اتاق ۱ (۴ تخته)", "beds": 4, "price": 3000},
    {"name": "اتاق ۲ (خصوصی)", "beds": 1, "price": 180000},
    {"name": "اتاق ۳ (۱۰ تخته)", "beds": 10, "price": 2500},
    {"name": "اتاق ۴ (۶ تخته)", "beds": 6, "price": 3500},
]

# ================= LOGIN =================
login_html = """
<h2>ورود</h2>
<form method="POST">
<input name="username" placeholder="user"><br>
<input name="password" type="password" placeholder="pass"><br>
<button>ورود</button>
</form>
"""

# ================= UI حرفه‌ای کامل =================
dashboard_html = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="UTF-8">
<title>Hostel Pro</title>

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

<style>
body {background:#f8fafc;font-family:tahoma;}

.sidebar {
    width:280px;height:100vh;position:fixed;right:0;
    background:white;padding:30px;
}

.main {margin-right:280px;padding:30px;}

.room-box {
    background:white;padding:25px;
    border-radius:25px;margin-bottom:30px;
}

.bed {
    width:130px;height:150px;
    border-radius:20px;
    border:2px dashed #ddd;
    display:flex;flex-direction:column;
    align-items:center;justify-content:center;
    margin:10px;
    position:relative;
}

.bed.full {background:#eef2ff;border:2px solid #4361ee;}
.bed.debt {border-color:red;background:#fff5f5;}
.bed.ok {border-color:green;background:#f0fff4;}

.whatsapp {
    position:absolute;
    top:8px;left:8px;
    background:#25d366;
    color:white;
    border-radius:50%;
    padding:5px 8px;
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

<h2>داشبورد</h2>

<div class="row mb-4">
<div class="col">درآمد: {{income}}</div>
<div class="col">هزینه: {{cost}}</div>
<div class="col">سود: {{income-cost}}</div>
</div>

{% for room in rooms %}
<div class="room-box">

<h4>{{room.name}} | {{room.price}}</h4>

<div style="display:flex;flex-wrap:wrap">

{% for i in range(room.beds) %}
    {% set found=None %}

    {% for b in bookings %}
        {% if b[1]==room.name and b[2]==i %}
            {% set found=b %}
        {% endif %}
    {% endfor %}

    {% if found %}
        {% set balance=found[6]-found[5] %}

        <div class="bed full {% if balance>0 %}ok{% elif balance<0 %}debt{% endif %}">
            <a class="whatsapp" href="https://wa.me/{{found[8]}}">📞</a>

            <b>{{found[3]}}</b>
            <small>{{balance}} تومان</small>

            <a href="/checkout/{{found[0]}}" style="color:red;">خروج</a>
        </div>

    {% else %}
        <form method="POST" action="/add" class="bed">
            <input type="hidden" name="room" value="{{room.name}}">
            <input type="hidden" name="bed" value="{{i}}">

            <input name="name" placeholder="نام" style="width:90px">
            <input name="days" placeholder="روز" style="width:60px">
            <input name="paid" placeholder="پرداخت" style="width:80px">
            <input name="whatsapp" placeholder="واتساپ" style="width:90px">

            <button>ثبت</button>
        </form>
    {% endif %}

{% endfor %}

</div>
</div>
{% endfor %}

<h3>ثبت هزینه</h3>
<form method="POST" action="/expense">
<input name="title">
<input name="amount">
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
    expenses=conn.execute("SELECT * FROM expenses").fetchall()
    conn.close()

    income=sum(b[5] for b in bookings)
    cost=sum(e[2] for e in expenses)

    return render_template_string(
        dashboard_html,
        rooms=rooms,
        bookings=bookings,
        income=income,
        cost=cost
    )


@app.route("/add", methods=["POST"])
def add():
    room=request.form["room"]
    bed=int(request.form["bed"])
    name=request.form["name"]
    days=int(request.form["days"])
    paid=int(request.form["paid"])
    whatsapp=request.form.get("whatsapp","")

    room_data=next(r for r in rooms if r["name"]==room)
    total=days*room_data["price"]

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
    conn.execute("DELETE FROM bookings WHERE id=?", (id,))
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

    return f"<h2>درآمد:{income} | هزینه:{cost} | سود:{income-cost}</h2>"


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= RUN =================
if __name__ == "__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
