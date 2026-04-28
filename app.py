import os
import sqlite3
import logging
from datetime import datetime, date, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hostel-super-secure-key-2026")

# پیدا کردن مسیر دقیق برای دیتابیس در سرور
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hostel_main.db")

# ---------------------------------------------------------
# DATABASE & LOGIC
# ---------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """ایجاد جداول - این تابع حتماً اجرا می‌شود"""
    logger.info("Initializing Database...")
    with get_db_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            base_price INTEGER DEFAULT 0,
            room_type TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER,
            bed_number INTEGER,
            customer_name TEXT NOT NULL,
            whatsapp TEXT,
            checkin_date TEXT,
            checkout_date TEXT,
            last_charge_date TEXT,
            daily_rate INTEGER,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY(room_id) REFERENCES rooms(id))""")

        conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER,
            type TEXT CHECK(type IN ('charge', 'payment', 'discount')),
            amount INTEGER NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY(booking_id) REFERENCES bookings(id))""")

        if conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
            rooms_data = [
                ('VIP 101', 1, 500000, 'خصوصی'),
                ('Dorm 102', 4, 150000, 'عمومی'),
                ('Dorm 103', 8, 120000, 'اقتصادی')
            ]
            conn.executemany("INSERT INTO rooms (name, capacity, base_price, room_type) VALUES (?,?,?,?)", rooms_data)
        conn.commit()

# اجرای خودکار ساخت دیتابیس هنگام بالا آمدن برنامه (بسیار مهم برای Render)
init_db()

def run_daily_accounting():
    conn = get_db_connection()
    today = date.today()
    active_guests = conn.execute("SELECT * FROM bookings WHERE is_active = 1").fetchall()
    for guest in active_guests:
        last_date = datetime.strptime(guest['last_charge_date'], '%Y-%m-%d').date()
        diff = (today - last_date).days
        if diff > 0:
            for i in range(1, diff + 1):
                charge_day = last_date + timedelta(days=i)
                conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'charge', ?, ?, ?)",
                             (guest['id'], guest['daily_rate'], str(charge_day), f"اجاره روزانه {charge_day}"))
            conn.execute("UPDATE bookings SET last_charge_date = ? WHERE id = ?", (str(today), guest['id']))
    conn.commit()
    conn.close()

def get_balance(booking_id):
    conn = get_db_connection()
    c = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (booking_id,)).fetchone()[0] or 0
    p = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type IN ('payment', 'discount')", (booking_id,)).fetchone()[0] or 0
    conn.close()
    return c - p

# ---------------------------------------------------------
# UI TEMPLATES
# ---------------------------------------------------------
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { background: #f0f2f5; font-family: tahoma; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); width: 90%; max-width: 320px; }
        input { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; }
        button { width: 100%; padding: 12px; background: #4361ee; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
    <div class="login-box">
        <h3 style="text-align: center; color: #333;">ورود به سیستم</h3>
        <form action="/login" method="POST">
            <input name="u" placeholder="نام کاربری (admin)" required>
            <input name="p" type="password" placeholder="رمز عبور (admin123)" required>
            <button type="submit">ورود به پنل</button>
        </form>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>هاستل ERP</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap');
        body { font-family: 'Vazirmatn', sans-serif; background: #f8f9fa; }
        .room-box { background: white; border-radius: 15px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
        .bed { width: 100px; height: 100px; border-radius: 12px; border: 2px dashed #ccc; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; background: white; position: relative; }
        .bed.occupied { border: 2px solid #4361ee; background: #f0f3ff; }
        .badge-price { position: absolute; bottom: 5px; font-size: 9px; padding: 2px 5px; border-radius: 8px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-primary mb-3 shadow-sm">
        <div class="container text-white fw-bold">مدیریت هاستل | {{ stats.count }} نفر مقیم</div>
    </nav>
    <div class="container">
        <div class="row g-2 mb-3 text-center">
            <div class="col-6"><div class="bg-white p-2 rounded-3 shadow-sm text-success small">وصولی امروز:<br><b>{{ "{:,.0f}".format(stats.revenue) }}</b></div></div>
            <div class="col-6"><div class="bg-white p-2 rounded-3 shadow-sm text-danger small">کل مطالبات:<br><b>{{ "{:,.0f}".format(stats.debt) }}</b></div></div>
        </div>
        {% for room in rooms %}
        <div class="room-box">
            <h6 class="fw-bold mb-3 border-bottom pb-2">{{ room.name }}</h6>
            <div class="d-flex flex-wrap gap-2">
                {% for bed in room.beds %}
                    {% if bed.status == 'empty' %}
                    <div class="bed" onclick="openCheckin({{ room.id }}, {{ bed.num }}, {{ room.base_price }})">
                        <i class="fa fa-plus text-muted"></i><small>تخت {{ bed.num }}</small>
                    </div>
                    {% else %}
                    <div class="bed occupied" onclick="openLedger({{ bed.info.id }})">
                        <small class="fw-bold">{{ bed.info.customer_name[:10] }}</small>
                        <span class="badge-price {{ 'bg-danger text-white' if bed.info.balance > 0 else 'bg-success text-white' }}">
                            {{ "{:,.0f}".format(bed.info.balance|abs) if bed.info.balance != 0 else 'تسویه' }}
                        </span>
                    </div>
                    {% endif %}
                {% endfor %}
            </div>
        </div>
        {% endfor %}
        <div class="text-center mt-4 mb-5"><a href="/logout" class="btn btn-outline-secondary btn-sm">خروج از سیستم</a></div>
    </div>

    <div class="modal fade" id="checkinModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered"><form action="/action/checkin" method="POST" class="modal-content p-4 shadow">
        <input type="hidden" name="rid" id="in_rid"><input type="hidden" name="bnum" id="in_bnum">
        <h6 class="fw-bold mb-3">پذیرش جدید</h6>
        <input type="text" name="name" class="form-control mb-2" placeholder="نام مسافر" required>
        <input type="number" name="rate" id="in_rate" class="form-control mb-2" placeholder="نرخ شبانه">
        <input type="number" name="payment" class="form-control mb-2" placeholder="دریافتی اول (اختیاری)">
        <button class="btn btn-primary w-100 mt-2">ثبت ورود</button>
    </form></div></div>
    <div class="modal fade" id="ledgerModal" tabindex="-1"><div class="modal-dialog"><div class="modal-content p-4 shadow" id="ledgerBody"></div></div></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function openCheckin(rid, bnum, rate) {
            document.getElementById('in_rid').value = rid;
            document.getElementById('in_bnum').value = bnum;
            document.getElementById('in_rate').value = rate;
            new bootstrap.Modal(document.getElementById('checkinModal')).show();
        }
        async function openLedger(bid) {
            const res = await fetch('/api/guest/' + bid);
            const d = await res.json();
            let html = `<div class="d-flex justify-content-between mb-3"><b>${d.guest.customer_name}</b> <span class="badge bg-warning text-dark">${d.balance.toLocaleString()}</span></div>
                <div style="max-height:180px; overflow-y:auto" class="border p-2 mb-3 bg-light small">
                    ${d.ledger.map(t => `<div class="d-flex justify-content-between border-bottom py-1"><span>${t.description}</span><b class="${t.type=='charge'?'text-danger':'text-success'}">${t.amount.toLocaleString()}</b></div>`).join('')}
                </div>
                <form action="/action/pay" method="POST" class="input-group mb-3"><input type="hidden" name="bid" value="${d.guest.id}"><input type="number" name="amount" class="form-control" placeholder="مبلغ دریافتی" required><button class="btn btn-success">ثبت</button></form>
                <a href="/action/checkout/${d.guest.id}" class="btn btn-danger w-100" onclick="return confirm('خروج؟')">تسویه و خروج نهایی</a>`;
            document.getElementById('ledgerBody').innerHTML = html;
            new bootstrap.Modal(document.getElementById('ledgerModal')).show();
        }
    </script>
</body>
</html>
"""

# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------
@app.route('/')
def login_page():
    if session.get('logged_in'): return redirect('/dashboard')
    return render_template_string(LOGIN_HTML)

@app.route('/login', methods=['POST'])
def do_login():
    if request.form.get('u') == 'admin' and request.form.get('p') == 'admin123':
        session['logged_in'] = True
        return redirect('/dashboard')
    return "ورود ناموفق!"

@app.route('/logout')
def do_logout():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'): return redirect('/')
    run_daily_accounting()
    conn = get_db_connection()
    rooms = [dict(r) for r in conn.execute("SELECT * FROM rooms").fetchall()]
    bookings = [dict(b) for b in conn.execute("SELECT * FROM bookings WHERE is_active=1").fetchall()]
    total_debt = 0
    for r in rooms:
        r['beds'] = []
        for i in range(1, r['capacity'] + 1):
            b_data = next((b for b in bookings if b['room_id'] == r['id'] and b['bed_number'] == i), None)
            if b_data:
                bal = get_balance(b_data['id'])
                b_data['balance'] = bal
                if bal > 0: total_debt += bal
                r['beds'].append({'status': 'occupied', 'info': b_data})
            else:
                r['beds'].append({'status': 'empty', 'num': i})
    stats = {
        'revenue': conn.execute("SELECT SUM(amount) FROM transactions WHERE type='payment' AND date=?", (str(date.today()),)).fetchone()[0] or 0,
        'debt': total_debt,
        'count': len(bookings)
    }
    conn.close()
    return render_template_string(DASHBOARD_HTML, rooms=rooms, stats=stats)

@app.route('/api/guest/<int:bid>')
def api_guest(bid):
    conn = get_db_connection()
    guest = dict(conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())
    ledger = [dict(t) for t in conn.execute("SELECT * FROM transactions WHERE booking_id=? ORDER BY id DESC", (bid,)).fetchall()]
    conn.close()
    return jsonify({'guest': guest, 'ledger': ledger, 'balance': get_balance(bid)})

@app.route('/action/checkin', methods=['POST'])
def action_checkin():
    today = str(date.today())
    conn = get_db_connection()
    cur = conn.execute("INSERT INTO bookings (room_id, bed_number, customer_name, whatsapp, checkin_date, last_charge_date, daily_rate) VALUES (?,?,?,?,?,?,?)", 
                 (request.form['rid'], request.form['bnum'], request.form['name'], "", today, today, request.form['rate']))
    bid = cur.lastrowid
    pay = int(request.form.get('payment', 0) or 0)
    if pay > 0:
        conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'payment', ?, ?, ?)", (bid, pay, today, "پیش‌پرداخت"))
    conn.commit()
    return redirect('/dashboard')

@app.route('/action/pay', methods=['POST'])
def action_pay():
    conn = get_db_connection()
    conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'payment', ?, ?, ?)", (request.form['bid'], int(request.form['amount']), str(date.today()), "دریافت وجه"))
    conn.commit()
    return redirect('/dashboard')

@app.route('/action/checkout/<int:bid>')
def action_checkout(bid):
    conn = get_db_connection()
    conn.execute("UPDATE bookings SET is_active=0, checkout_date=? WHERE id=?", (str(date.today()), bid))
    conn.commit()
    return redirect('/dashboard')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
