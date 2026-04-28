from flask import Flask, request, redirect, session, render_template_string, jsonify
import sqlite3
from datetime import datetime, date, timedelta
import os

app = Flask(__name__)
app.secret_key = "fin-tech-hostel-key-2026"
DB = "hostel_erp.db"

# ================= DATABASE & INIT =================
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # ساختار اتاق‌ها
        conn.execute("""CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY, name TEXT, capacity INTEGER, 
            base_price INTEGER, room_type TEXT)""")
        
        # ساختار رزروها
        conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY, room_id INTEGER, bed_number INTEGER, 
            customer_name TEXT, whatsapp TEXT, checkin_date TEXT, 
            checkout_date TEXT, daily_rate INTEGER, is_active INTEGER DEFAULT 1,
            last_charge_date TEXT)""")

        # ساختار تراکنش‌های مالی
        conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY, booking_id INTEGER, type TEXT, 
            amount INTEGER, date TEXT, description TEXT,
            FOREIGN KEY(booking_id) REFERENCES bookings(id))""")

        # داده‌های اولیه اتاق‌ها در صورت خالی بودن دیتابیس
        if conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
            rooms_data = [
                ("اتاق ۱۰۱ (VIP)", 1, 180000, "خصوصی"),
                ("اتاق ۱۰۲ (۴ تخته)", 4, 35000, "عمومی"),
                ("اتاق ۱۰۳ (۸ تخته)", 8, 25000, "اقتصادی")
            ]
            conn.executemany("INSERT INTO rooms (name, capacity, base_price, room_type) VALUES (?,?,?,?)", rooms_data)

init_db()

# ================= CORE LOGIC (ACCOUNTING) =================
def sync_daily_charges():
    """محاسبه خودکار بدهی روزانه برای تمام مسافران مقیم تا امروز"""
    db = get_db()
    active_bookings = db.execute("SELECT * FROM bookings WHERE is_active = 1").fetchall()
    today = date.today()

    for b in active_bookings:
        last_charge = datetime.strptime(b['last_charge_date'], '%Y-%m-%d').date()
        days_to_charge = (today - last_charge).days

        if days_to_charge > 0:
            for i in range(1, days_to_charge + 1):
                charge_date = last_charge + timedelta(days=i)
                db.execute("""INSERT INTO transactions (booking_id, type, amount, date, description) 
                           VALUES (?, 'charge', ?, ?, ?)""", 
                           (b['id'], b['daily_rate'], str(charge_date), f"شارژ اقامت روز {charge_date}"))
            
            db.execute("UPDATE bookings SET last_charge_date = ? WHERE id = ?", (str(today), b['id']))
    db.commit()

def get_booking_balance(booking_id):
    db = get_db()
    charges = db.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (booking_id,)).fetchone()[0] or 0
    payments = db.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'", (booking_id,)).fetchone()[0] or 0
    return charges - payments

# ================= ROUTES =================
@app.route("/")
def index():
    if not session.get("login"):
        return '''<body style="direction:rtl; font-family:tahoma; background:#f0f2f5; display:flex; justify-content:center; align-items:center; height:100vh;">
            <form action="/login" method="POST" style="background:white; padding:40px; border-radius:20px; box-shadow:0 10px 25px rgba(0,0,0,0.1);">
                <h2 style="margin-bottom:20px;">مدیریت هوشمند هاستل</h2>
                <input name="u" placeholder="نام کاربری" style="display:block; width:100%; padding:10px; margin-bottom:10px; border:1px solid #ddd; border-radius:8px;">
                <input name="p" type="password" placeholder="رمز عبور" style="display:block; width:100%; padding:10px; margin-bottom:20px; border:1px solid #ddd; border-radius:8px;">
                <button style="width:100%; padding:12px; background:#4361ee; color:white; border:none; border-radius:8px; cursor:pointer;">ورود به سیستم</button>
            </form></body>'''
    return redirect("/dashboard")

@app.route("/login", methods=["POST"])
def login():
    if request.form["u"] == "admin" and request.form["p"] == "admin123":
        session["login"] = True
    return redirect("/dashboard")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard")
def dashboard():
    if not session.get("login"): return redirect("/")
    sync_daily_charges()
    
    db = get_db()
    rooms = [dict(r) for r in db.execute("SELECT * FROM rooms").fetchall()]
    all_bookings = [dict(b) for b in db.execute("SELECT * FROM bookings WHERE is_active=1").fetchall()]
    
    total_debt = 0
    for r in rooms:
        r['beds'] = []
        for i in range(1, r['capacity'] + 1):
            booking = next((b for b in all_bookings if b['room_id'] == r['id'] and b['bed_number'] == i), None)
            if booking:
                balance = get_booking_balance(booking['id'])
                booking['balance'] = balance
                if balance > 0: total_debt += balance
                r['beds'].append({'status': 'occupied', 'data': booking})
            else:
                r['beds'].append({'status': 'empty', 'bed_num': i})
    
    stats = {
        "daily_revenue": db.execute("SELECT SUM(amount) FROM transactions WHERE type='payment' AND date=?", (str(date.today()),)).fetchone()[0] or 0,
        "total_debt": total_debt,
        "active_guests": len(all_bookings)
    }
    return render_template_string(dashboard_html, rooms=rooms, stats=stats)

@app.route("/api/booking/<int:bid>")
def get_booking_details(bid):
    db = get_db()
    booking = dict(db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())
    ledger = [dict(t) for t in db.execute("SELECT * FROM transactions WHERE booking_id=? ORDER BY date DESC", (bid,)).fetchall()]
    balance = get_booking_balance(bid)
    return jsonify({'booking': booking, 'ledger': ledger, 'balance': balance})

@app.route("/action/checkin", methods=["POST"])
def action_checkin():
    db = get_db()
    c_date = str(date.today())
    cursor = db.execute("""INSERT INTO bookings 
        (room_id, bed_number, customer_name, whatsapp, checkin_date, last_charge_date, daily_rate) 
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (request.form['room_id'], request.form['bed_num'], request.form['name'], 
         request.form['whatsapp'], c_date, c_date, request.form['rate']))
    
    booking_id = cursor.lastrowid
    payment = int(request.form.get('payment', 0))
    if payment > 0:
        db.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'payment', ?, ?, ?)", 
                   (booking_id, payment, c_date, "پیش‌پرداخت هنگام پذیرش"))
    db.commit()
    return redirect("/dashboard")

@app.route("/action/add-payment", methods=["POST"])
def add_payment():
    db = get_db()
    db.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'payment', ?, ?, ?)", 
               (request.form['booking_id'], int(request.form['amount']), str(date.today()), "دریافت نقدی / کارت"))
    db.commit()
    return redirect("/dashboard")

@app.route("/action/checkout/<int:bid>")
def action_checkout(bid):
    db = get_db()
    db.execute("UPDATE bookings SET is_active=0, checkout_date=? WHERE id=?", (str(date.today()), bid))
    db.commit()
    return redirect("/dashboard")

# ================= UI DESIGN (HTML) =================
dashboard_html = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>پنل هوشمند هاستل</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;500;800&display=swap');
        :root { --primary: #635bff; --bg: #f8fafc; }
        body { background: var(--bg); font-family: 'Vazirmatn', sans-serif; padding-top: 20px; }
        .sidebar { width: 260px; height: 100vh; position: fixed; right: 0; top: 0; background: white; border-left: 1px solid #e2e8f0; padding: 25px; }
        .main-content { margin-right: 260px; padding: 0 30px 50px 30px; }
        .stat-card { background: white; border-radius: 15px; padding: 20px; border: 1px solid #e2e8f0; }
        .room-section { background: white; border-radius: 15px; padding: 20px; margin-bottom: 25px; border: 1px solid #e2e8f0; }
        .bed-unit { 
            width: 130px; height: 140px; border-radius: 12px; border: 2px dashed #cbd5e1; 
            display: flex; flex-direction: column; align-items: center; justify-content: center; 
            cursor: pointer; transition: 0.2s; background: #fff; position: relative;
        }
        .bed-unit.occupied { border: 2px solid var(--primary); background: #f8faff; }
        .balance-badge { position: absolute; bottom: 8px; font-size: 10px; padding: 2px 8px; border-radius: 20px; }
        .debt { background: #fee2e2; color: #ef4444; }
        .credit { background: #dcfce7; color: #22c55e; }
        .settled { background: #f1f5f9; color: #64748b; }
        .ledger-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
    </style>
</head>
<body>
    <aside class="sidebar">
        <h4 class="fw-bold text-primary mb-4">هاستل سیستم</h4>
        <nav class="nav flex-column gap-2">
            <a href="/dashboard" class="nav-link active"><i class="fas fa-home me-2"></i> داشبورد مدیریتی</a>
            <a href="#" class="nav-link text-muted"><i class="fas fa-users me-2"></i> لیست تمام مهمانان</a>
            <a href="/logout" class="nav-link text-danger mt-5"><i class="fas fa-power-off me-2"></i> خروج</a>
        </nav>
    </aside>

    <main class="main-content">
        <div class="row g-4 mb-4">
            <div class="col-md-4">
                <div class="stat-card">
                    <small class="text-muted">وصولی نقدی امروز</small>
                    <h3 class="fw-bold text-success">{{ "{:,.0f}".format(stats.daily_revenue) }}</h3>
                </div>
            </div>
            <div class="col-md-4">
                <div class="stat-card">
                    <small class="text-muted">کل مطالبات لحظه‌ای</small>
                    <h3 class="fw-bold text-danger">{{ "{:,.0f}".format(stats.total_debt) }}</h3>
                </div>
            </div>
            <div class="col-md-4">
                <div class="stat-card">
                    <small class="text-muted">تخت‌های اشغال شده</small>
                    <h3 class="fw-bold">{{ stats.active_guests }} تخت</h3>
                </div>
            </div>
        </div>

        <h5 class="fw-bold mb-3">نقشه اتاق‌ها و وضعیت تخت‌ها</h5>
        {% for room in rooms %}
        <div class="room-section">
            <h6 class="fw-bold mb-3">{{ room.name }} <span class="badge bg-light text-muted">{{ room.room_type }}</span></h6>
            <div class="d-flex flex-wrap gap-3">
                {% for bed in room.beds %}
                    {% if bed.status == 'empty' %}
                    <div class="bed-unit" onclick="openCheckin({{ room.id }}, {{ bed.bed_num }}, {{ room.base_price }})">
                        <i class="fas fa-plus text-muted mb-2"></i>
                        <span class="small">تخت {{ bed.bed_num }}</span>
                    </div>
                    {% else %}
                    <div class="bed-unit occupied" onclick="openLedger({{ bed.data.id }})">
                        <i class="fas fa-user text-primary mb-2"></i>
                        <span class="small fw-bold">{{ bed.data.customer_name[:15] }}</span>
                        <span class="balance-badge {% if bed.data.balance > 0 %}debt{% elif bed.data.balance < 0 %}credit{% else %}settled{% endif %}">
                            {{ "{:,.0f}".format(bed.data.balance|abs) if bed.data.balance != 0 else 'تسویه' }}
                        </span>
                    </div>
                    {% endif %}
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </main>

    <div class="modal fade" id="checkinModal" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered">
            <form action="/action/checkin" method="POST" class="modal-content border-0 p-4 rounded-4">
                <input type="hidden" name="room_id" id="m_room_id">
                <input type="hidden" name="bed_num" id="m_bed_num">
                <h5 class="fw-bold mb-3">پذیرش سریع مسافر</h5>
                <input type="text" name="name" class="form-control mb-2" placeholder="نام مسافر" required>
                <input type="text" name="whatsapp" class="form-control mb-2" placeholder="واتس‌اپ">
                <div class="row g-2">
                    <div class="col-6"><input type="number" name="rate" id="m_rate" class="form-control" placeholder="نرخ شبی"></div>
                    <div class="col-6"><input type="number" name="payment" class="form-control" placeholder="دریافتی اول"></div>
                </div>
                <button class="btn btn-primary w-100 mt-3 py-2 fw-bold">ثبت و ورود</button>
            </form>
        </div>
    </div>

    <div class="modal fade" id="ledgerModal" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered modal-lg">
            <div class="modal-content border-0 p-4 rounded-4" id="ledgerContent">
                </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function openCheckin(rid, bnum, rate) {
            document.getElementById('m_room_id').value = rid;
            document.getElementById('m_bed_num').value = bnum;
            document.getElementById('m_rate').value = rate;
            new bootstrap.Modal(document.getElementById('checkinModal')).show();
        }

        async function openLedger(bid) {
            const res = await fetch('/api/booking/' + bid);
            const data = await res.json();
            const b = data.booking;
            
            let html = `
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <div>
                        <h4 class="fw-bold mb-0">${b.customer_name}</h4>
                        <small class="text-muted">ورود: ${b.checkin_date} | نرخ: ${b.daily_rate} تومان</small>
                    </div>
                    <span class="badge ${data.balance > 0 ? 'bg-danger' : 'bg-success'} fs-5">مانده: ${Math.abs(data.balance)}</span>
                </div>
                <div style="max-height: 250px; overflow-y: auto" class="mb-3">
                    ${data.ledger.map(t => `
                        <div class="ledger-row">
                            <span>${t.description} <small class="text-muted">${t.date}</small></span>
                            <span class="${t.type=='charge'?'text-warning':'text-success'} fw-bold">${t.type=='charge'?'+':'-'}${t.amount}</span>
                        </div>
                    `).join('')}
                </div>
                <form action="/action/add-payment" method="POST" class="input-group mb-3">
                    <input type="hidden" name="booking_id" value="${b.id}">
                    <input type="number" name="amount" class="form-control" placeholder="مبلغ دریافتی جدید..." required>
                    <button class="btn btn-success">ثبت دریافت</button>
                </form>
                <div class="d-flex gap-2">
                    <button class="btn btn-outline-secondary flex-grow-1">چاپ فاکتور</button>
                    <a href="/action/checkout/${b.id}" class="btn btn-danger" onclick="return confirm('تسویه نهایی انجام شود؟')">خروج مسافر</a>
                </div>
            `;
            document.getElementById('ledgerContent').innerHTML = html;
            new bootstrap.Modal(document.getElementById('ledgerModal')).show();
        }
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True, port=5000)
