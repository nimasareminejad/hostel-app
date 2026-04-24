from flask import Flask, request, redirect, session, render_template_string
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "secure123"
DB = "hostel_pro.db"

# ================= DATABASE INIT =================
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY, name TEXT, capacity INTEGER, price INTEGER, type TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY, room_id INTEGER, bed_number INTEGER, 
        customer_name TEXT, days INTEGER, paid INTEGER, total INTEGER, 
        whatsapp TEXT, date TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY, title TEXT, amount INTEGER, date TEXT)""")
    
    # اضافه کردن اتاق‌های پیش‌فرض در صورت خالی بودن دیتابیس
    if c.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
        rooms_data = [
            ("اتاق ۱ (۴ تخته)", 4, 3000, "خوابگاه عمومی"),
            ("اتاق ۲ (خصوصی)", 1, 180000, "ویژه VIP"),
            ("اتاق ۳ (۱۰ تخته)", 10, 2500, "اقتصادی"),
            ("اتاق ۴ (۶ تخته)", 6, 3500, "خوابگاه بانوان")
        ]
        c.executemany("INSERT INTO rooms (name, capacity, price, type) VALUES (?,?,?,?)", rooms_data)
    
    conn.commit()
    conn.close()

init_db()

# ================= AUTH =================
USER, PASS = "nima", "nima1234"

# ================= ROUTES =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == USER and request.form.get("password") == PASS:
            session["login"] = True
            return redirect("/dashboard")
    return render_template_string('''<body style="direction:rtl;font-family:tahoma;text-align:center;padding-top:100px;">
        <h2>ورود به پنل HOSTEL PRO</h2>
        <form method="POST"><input name="username" placeholder="نام کاربری"><br><br>
        <input name="password" type="password" placeholder="رمز عبور"><br><br>
        <button type="submit" style="padding:10px 40px">ورود</button></form></body>''')

@app.route("/dashboard")
def dashboard():
    if not session.get("login"): return redirect("/")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    
    rooms = [dict(r) for r in conn.execute("SELECT * FROM rooms").fetchall()]
    bookings = [dict(b) for b in conn.execute("SELECT * FROM bookings").fetchall()]
    expenses = conn.execute("SELECT SUM(amount) FROM expenses").fetchone()[0] or 0
    
    # پردازش داده‌ها برای قالب
    total_income = 0
    occupied_count = 0
    total_beds = sum(r['capacity'] for r in rooms)
    
    for b in bookings:
        b['balance'] = b['paid'] - b['total']
        total_income += b['paid']
        occupied_count += 1
        
    for r in rooms:
        r['base_price'] = r['price']
        r['room_type'] = r['type']
        r['occupied_count'] = len([b for b in bookings if b['room_id'] == r['id']])

    stats = {
        "total_income": total_income,
        "total_expense": expenses,
        "net_profit": total_income - expenses,
        "occupied_beds": occupied_count,
        "total_beds": total_beds
    }

    return render_template_string(dashboard_html, 
                                 rooms=rooms, bookings=bookings, stats=stats, 
                                 current_date=datetime.now().strftime("%Y/%m/%d"))

@app.route("/action/checkin", methods=["POST"])
def checkin():
    r_id = request.form["room_id"]
    bed = request.form["bed_number"]
    name = request.form["customer_name"]
    days = int(request.form["days"])
    paid = int(request.form["received_amount"])
    wa = request.form["whatsapp"]
    
    conn = sqlite3.connect(DB)
    price = conn.execute("SELECT price FROM rooms WHERE id=?", (r_id,)).fetchone()[0]
    total = price * days
    conn.execute("INSERT INTO bookings (room_id, bed_number, customer_name, days, paid, total, whatsapp, date) VALUES (?,?,?,?,?,?,?,?)",
                 (r_id, bed, name, days, paid, total, wa, str(datetime.now())))
    conn.commit()
    return redirect("/dashboard")

@app.route("/checkout/<int:id>")
def checkout(id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM bookings WHERE id=?", (id,))
    conn.commit()
    return redirect("/dashboard")

@app.route("/expense", methods=["POST"])
def add_expense():
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO expenses (title, amount, date) VALUES (?,?,?)",
                 (request.form["title"], request.form["amount"], str(datetime.now())))
    conn.commit()
    return redirect("/dashboard")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
    # ================= UI DESIGN =================
dashboard_html = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>Hostel Pro | داشبورد هوشمند مدیریت</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@100;400;700;900&display=swap');
        :root {
            --primary: #4361ee; --secondary: #4cc9f0; --sidebar: #ffffff;
            --bg: #f8fafc; --accent: #6366f1; --danger: #f72585;
            --success: #06d6a0; --warning: #ffd166;
        }
        body { background: var(--bg); font-family: 'Vazirmatn', sans-serif; color: #1e293b; overflow-x: hidden; }
        .sidebar {
            width: 280px; height: 100vh; background: var(--sidebar);
            position: fixed; right: 0; top: 0; padding: 30px 20px;
            border-left: 1px solid rgba(0,0,0,0.05); z-index: 1000;
            box-shadow: -10px 0 30px rgba(0,0,0,0.02);
        }
        .main-wrapper { margin-right: 280px; padding: 40px; transition: 0.3s; }
        .stat-card {
            background: white; border-radius: 28px; padding: 25px;
            border: 1px solid rgba(255,255,255,0.8); box-shadow: 0 10px 25px rgba(0,0,0,0.02);
            position: relative; overflow: hidden;
        }
        .room-container {
            background: white; border-radius: 35px; padding: 35px;
            margin-bottom: 35px; border: 1px solid rgba(0,0,0,0.03);
        }
        .bed-unit {
            width: 130px; min-height: 160px; border-radius: 25px;
            display: flex; flex-direction: column; align-items: center;
            padding: 15px; cursor: pointer; transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            border: 2px dashed #e2e8f0; position: relative; background: #fff;
        }
        .bed-unit.occupied {
            background: linear-gradient(145deg, #ffffff, #f1f5ff);
            border: 2px solid var(--primary); box-shadow: 0 10px 20px rgba(67, 97, 238, 0.1);
        }
        .bed-unit.debtor { border-color: var(--danger); background: #fff5f8; }
        .bed-unit.creditor { border-color: var(--success); background: #f0fff4; }
        .bed-unit:hover { transform: translateY(-8px) scale(1.02); }
        .badge-finance { font-size: 10px; padding: 4px 8px; border-radius: 10px; margin-top: 5px; }
        .whatsapp-btn {
            width: 32px; height: 32px; border-radius: 50%; background: #25d366;
            color: white; display: flex; align-items: center; justify-content: center;
            position: absolute; top: 10px; left: 10px; font-size: 14px; text-decoration: none !important;
        }
        .nav-link-custom {
            padding: 14px 20px; border-radius: 18px; color: #64748b;
            text-decoration: none; display: flex; align-items: center;
            margin-bottom: 8px; font-weight: 600; transition: 0.3s;
        }
        .nav-link-custom.active { background: var(--primary); color: white; }
        .price-tag { font-family: 'monospace'; font-weight: 900; letter-spacing: -1px; }
    </style>
</head>
<body>
    <aside class="sidebar">
        <div class="text-center mb-5">
            <h2 class="fw-black text-primary">HOSTEL <span class="text-dark">PRO</span></h2>
            <span class="badge bg-light text-muted border">Enterprise v2.6</span>
        </div>
        <nav>
            <a href="/dashboard" class="nav-link-custom active"><i class="fas fa-chart-pie ms-3"></i> پیشخوان هوشمند</a>
            <a href="/logout" class="nav-link-custom text-danger"><i class="fas fa-power-off ms-3"></i> خروج از سیستم</a>
        </nav>
    </aside>

    <main class="main-wrapper">
        <header class="d-flex justify-content-between align-items-center mb-5 animate__animated animate__fadeIn">
            <div>
                <h1 class="fw-black display-6">سلام، مدیر عزیز 👑</h1>
                <p class="text-muted fs-5">امروز: {{ current_date }} | <span class="text-primary">وضعیت هاستل: ایده‌آل</span></p>
            </div>
            <div class="d-flex gap-3">
                <button class="btn btn-white shadow-sm rounded-pill px-4 py-2 fw-bold" data-bs-toggle="modal" data-bs-target="#expenseModal">
                    <i class="fas fa-minus-circle text-danger me-2"></i> ثبت هزینه
                </button>
                <button class="btn btn-primary rounded-pill px-4 py-2 fw-bold shadow" onclick="location.reload()">
                    <i class="fas fa-sync-alt me-2"></i> بروزرسانی
                </button>
            </div>
        </header>

        <div class="row g-4 mb-5">
            <div class="col-md-3">
                <div class="stat-card">
                    <small class="text-muted d-block">ورودی مالی</small>
                    <h2 class="fw-black price-tag">{{ "{:,.0f}".format(stats.total_income) }}</h2>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <small class="text-muted d-block">هزینه‌ها</small>
                    <h2 class="fw-black price-tag text-danger">{{ "{:,.0f}".format(stats.total_expense) }}</h2>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card" style="background: var(--primary); color:white">
                    <small class="text-white-50 d-block">تخت‌های اشغال شده</small>
                    <h2 class="fw-black">{{ stats.occupied_beds }} / {{ stats.total_beds }}</h2>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <small class="text-muted d-block">سود خالص</small>
                    <h2 class="fw-black price-tag text-success">{{ "{:,.0f}".format(stats.net_profit) }}</h2>
                </div>
            </div>
        </div>

        {% for room in rooms %}
        <div class="room-container">
            <div class="d-flex justify-content-between mb-4 border-bottom pb-3">
                <h4 class="fw-bold">{{ room.name }} <small class="fs-6 text-muted">({{ room.type }})</small></h4>
                <div class="text-end fw-bold">{{ room.price }} تومان / شب</div>
            </div>
            <div class="d-flex flex-wrap gap-4">
                {% for i in range(1, room.capacity + 1) %}
                    {% set ns = namespace(booking=none) %}
                    {% for b in bookings %}{% if b.room_id == room.id and b.bed_number == i %}{% set ns.booking = b %}{% endif %}{% endfor %}

                    {% if ns.booking %}
                        <div class="bed-unit occupied {{ 'debtor' if ns.booking.balance < 0 else 'creditor' if ns.booking.balance > 0 }}">
                            <a href="https://wa.me/{{ ns.booking.whatsapp }}" class="whatsapp-btn" target="_blank"><i class="fab fa-whatsapp"></i></a>
                            <div class="mt-3 text-center">
                                <i class="fas fa-user-circle fs-2 mb-2 text-primary"></i>
                                <div class="fw-bold small">{{ ns.booking.customer_name[:12] }}</div>
                                <span class="badge-finance {{ 'bg-danger' if ns.booking.balance < 0 else 'bg-success' }}">
                                    {{ ns.booking.balance|abs }} تومان
                                </span>
                                <div class="mt-2 pt-2 border-top w-100"><a href="/checkout/{{ ns.booking.id }}" class="text-danger small">تخلیه</a></div>
                            </div>
                        </div>
                    {% else %}
                        <div class="bed-unit" onclick="openCheckin({{ room.id }}, {{ i }}, {{ room.price }})">
                            <i class="fas fa-plus-circle mb-2 fs-3 text-light"></i>
                            <span class="text-muted fw-bold">تخت {{ i }}</span>
                        </div>
                    {% endif %}
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </main>

    <div class="modal fade" id="checkinModal" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content p-4" style="border-radius:30px;">
                <form action="/action/checkin" method="POST">
                    <input type="hidden" name="room_id" id="m_room_id">
                    <input type="hidden" name="bed_number" id="m_bed_num">
                    <h4 class="fw-black mb-4">پذیرش مهمان جدید</h4>
                    <input type="text" name="customer_name" class="form-control mb-3" placeholder="نام مهمان" required>
                    <input type="text" name="whatsapp" class="form-control mb-3" placeholder="شماره واتساپ (98...)" required>
                    <div class="row">
                        <div class="col-6"><input type="number" name="days" class="form-control mb-3" value="1" placeholder="تعداد شب"></div>
                        <div class="col-6"><input type="number" name="received_amount" id="m_price" class="form-control mb-3" placeholder="مبلغ دریافتی"></div>
                    </div>
                    <button type="submit" class="btn btn-primary w-100 rounded-pill py-3">ثبت نهایی</button>
                </form>
            </div>
        </div>
    </div>

    <div class="modal fade" id="expenseModal" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content p-4" style="border-radius:30px;">
                <form action="/expense" method="POST">
                    <h4 class="fw-black mb-4">ثبت هزینه جدید</h4>
                    <input type="text" name="title" class="form-control mb-3" placeholder="عنوان هزینه (مثلاً قبوض)" required>
                    <input type="number" name="amount" class="form-control mb-3" placeholder="مبلغ (تومان)" required>
                    <button type="submit" class="btn btn-danger w-100 rounded-pill py-3">ثبت هزینه</button>
                </form>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function openCheckin(roomId, bedNum, basePrice) {
            document.getElementById('m_room_id').value = roomId;
            document.getElementById('m_bed_num').value = bedNum;
            document.getElementById('m_price').value = basePrice;
            new bootstrap.Modal(document.getElementById('checkinModal')).show();
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
