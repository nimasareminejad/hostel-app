from flask import Flask, request, redirect, session, render_template_string
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "secure123"

DB = "hostel.db"

# ---------------- DB ----------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY,
        room TEXT,
        bed INTEGER,
        name TEXT,
        days INTEGER,
        paid INTEGER,
        total INTEGER,
        date TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY,
        title TEXT,
        amount INTEGER,
        date TEXT
    )""")

    conn.commit()
    conn.close()

init_db()

# ---------------- AUTH ----------------
USER = "nima"
PASS = "nima1234"

# ---------------- ROOMS ----------------
rooms = [
    {"name": "اتاق ۱ (۴ تخته)", "beds": 4, "price": 3000},
    {"name": "اتاق ۲ (خصوصی)", "beds": 1, "price": 180000},
    {"name": "اتاق ۳ (۱۰ تخته)", "beds": 10, "price": 2500},
    {"name": "اتاق ۴ (۶ تخته)", "beds": 6, "price": 3500},
    {"name": "اتاق دختران", "beds": 4, "price": 3500},
    {"name": "اتاق پسران", "beds": 4, "price": 3500},
]

# ---------------- LOGIN ----------------
login_html = """
<h2>ورود</h2>
<form method="POST">
<input name="username" placeholder="user"><br>
<input name="password" type="password" placeholder="pass"><br>
<button>ورود</button>
</form>
"""

# ---------------- DASHBOARD ----------------
dashboard_html = """
<h2>داشبورد هاستل</h2>
<a href="/logout">خروج</a>
<hr>

{% for room in rooms %}
<h3>{{room.name}} ({{room.price}})</h3>

{% for i in range(room.beds) %}
    {% set found = None %}

    {% for b in bookings %}
        {% if b[1]==room.name and b[2]==i %}
            {% set found = b %}
        {% endif %}
    {% endfor %}

    {% if found %}
        {% set balance = found[6] - found[5] %}

        <div style="border:2px solid {{'red' if balance>0 else 'green'}};padding:10px;margin:5px">
            تخت {{i+1}} | {{found[3]}} | بدهی: {{balance}} تومان
            <a href="/checkout/{{found[0]}}">❌ خروج</a>
            <a target="_blank" href="https://wa.me/{{found[3]}}">📞 واتساپ</a>
        </div>

    {% else %}
        <form method="POST" action="/add">
            <input type="hidden" name="room" value="{{room.name}}">
            <input type="hidden" name="bed" value="{{i}}">

            <input name="name" placeholder="نام">
            <input name="days" placeholder="روز">
            <input name="paid" placeholder="پرداخت">

            <button>ثبت</button>
        </form>
    {% endif %}

{% endfor %}
<hr>
{% endfor %}

<h3>ثبت هزینه</h3>
<form method="POST" action="/expense">
<input name="title" placeholder="عنوان">
<input name="amount" placeholder="مبلغ">
<button>ثبت</button>
</form>

<a href="/report">گزارش</a>
"""

# ---------------- REPORT ----------------
report_html = """
<h2>گزارش مالی</h2>

<h3>درآمد</h3>
{% for b in bookings %}
<div>{{b[3]}} - {{b[5]}} تومان</div>
{% endfor %}

<h3>هزینه</h3>
{% for e in expenses %}
<div>{{e[1]}} - {{e[2]}} تومان</div>
{% endfor %}

<hr>

<h3>جمع</h3>
درآمد: {{income}} <br>
هزینه: {{cost}} <br>
سود: {{income-cost}}

<br><br>
<button onclick="window.print()">پرینت PDF</button>
"""

# ---------------- ROUTES ----------------

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

    room_data = next(r for r in rooms if r["name"] == room)
    price = room_data["price"]
    total = days * price

    conn=sqlite3.connect(DB)
    conn.execute("""INSERT INTO bookings 
    (room,bed,name,days,paid,total,date)
    VALUES (?,?,?,?,?,?,?)""",
    (room,bed,name,days,paid,total,str(datetime.now())))

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
    conn.execute("INSERT INTO expenses (title,amount,date) VALUES (?,?,?)",
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

    return render_template_string(report_html,
                                  bookings=bookings,
                                  expenses=expenses,
                                  income=income,
                                  cost=cost)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- RUN (Render Compatible) ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
