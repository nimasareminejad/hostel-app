import os
import sqlite3
import logging
from datetime import datetime, date, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hostel-super-secure-key-2026")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hostel_main.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            floor INTEGER, name TEXT, capacity INTEGER, base_price INTEGER, room_type TEXT)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER, bed_number INTEGER, customer_name TEXT, 
            passport TEXT, whatsapp TEXT, checkin_date TEXT, 
            expected_checkout TEXT, last_charge_date TEXT, 
            daily_rate INTEGER, is_active INTEGER DEFAULT 1)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER, 
            type TEXT, amount INTEGER, date TEXT, description TEXT)""")

        if conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
            rooms_data = [
                (1, 'اتاق ۱۰۱ (خصوصی)', 1, 500000, 'پرایوت'),
                (1, 'اتاق ۱۰۲ (۳ تخته)', 3, 200000, 'عمومی'),
                (1, 'اتاق ۱۰۳ (۶ تخته)', 6, 150000, 'عمومی'),
                (1, 'اتاق ۱۰۴ (۱۰ تخته)', 10, 120000, 'اقتصادی'),
                (2, 'اتاق ۲۰۱ (پسرانه)', 4, 180000, 'خوابگاه'),
                (2, 'اتاق ۲۰۲ (دخترانه)', 4, 180000, 'خوابگاه')
            ]
            conn.executemany("INSERT INTO rooms (floor, name, capacity, base_price, room_type) VALUES (?,?,?,?,?)", rooms_data)
        conn.commit()

init_db()

# --- Accounting Logic ---
def run_accounting():
    conn = get_db_connection()
    today = date.today()
    guests = conn.execute("SELECT * FROM bookings WHERE is_active = 1").fetchall()
    for g in guests:
        last = datetime.strptime(g['last_charge_date'], '%Y-%m-%d').date()
        diff = (today - last).days
        if diff > 0:
            for i in range(1, diff + 1):
                day = last + timedelta(days=i)
                conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'charge', ?, ?, ?)",
                             (g['id'], g['daily_rate'], str(day), f"شارژ روزانه {day}"))
            conn.execute("UPDATE bookings SET last_charge_date = ? WHERE id = ?", (str(today), g['id']))
    conn.commit()
    conn.close()

def get_balance(bid):
    conn = get_db_connection()
    c = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (bid,)).fetchone()[0] or 0
    p = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'", (bid,)).fetchone()[0] or 0
    conn.close()
    return c - p

# --- UI ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;700&display=swap');
        body { font-family: 'Vazirmatn', sans-serif; background: #f4f7f6; }
        .floor-header { background: #334155; color: white; padding: 10px 20px; border-radius: 10px; margin-top: 30px; }
        .room-card { background: white; border-radius: 15px; padding: 15px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        .bed { width: 85px; height: 85px; border-radius: 12px; border: 2px dashed #cbd5e1; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; font-size: 11px; background: white; transition: 0.2s; }
        .bed.occupied { border: 2px solid #4361ee; background: #eff6ff; }
        .bed:hover { transform: translateY(-3px); }
        .stat-box { background: white; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 4px solid #4361ee; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark mb-4 shadow">
        <div class="container">
            <span class="navbar-brand fw-bold"><i class="fa fa-hotel me-2"></i> سیستم مدیریت طبقات هاستل</span>
            <div class="d-flex gap-2">
                <a href="/report/all" class="btn btn-primary btn-sm"><i class="fa fa-print"></i> گزارش کل مسافران</a>
                <a href="/logout" class="btn btn-outline-light btn-sm">خروج</a>
            </div>
        </div>
    </nav>

    <div class="container pb-5">
        <div class="row g-3 mb-4">
            <div class="col-md-4"><div class="stat-box">وصولی امروز: <br><b class="text-success">{{ "{:,.0f}".format(stats.revenue) }}</b></div></div>
            <div class="col-md-4"><div class="stat-box">مطالبات کل: <br><b class="text-danger">{{ "{:,.0f}".format(stats.debt) }}</b></div></div>
            <div class="col-md-4"><div class="stat-box">تخت‌های پر: <br><b>{{ stats.count }} تخت</b></div></div>
        </div>

        {% for floor in [1, 2] %}
        <h5 class="floor-header"><i class="fa fa-layer-group me-2"></i> طبقه {{ "اول" if floor == 1 else "دوم" }}</h5>
        <div class="row mt-3">
            {% for room in rooms if room.floor == floor %}
            <div class="col-12">
                <div class="room-card">
                    <h6 class="fw-bold mb-3 text-secondary border-bottom pb-2">{{ room.name }} <small class="fw-normal">({{ room.room_type }})</small></h6>
                    <div class="d-flex flex-wrap gap-2">
                        {% for bed in room.beds %}
                            {% if bed.status == 'empty' %}
                            <div class="bed" onclick="openCheckin({{ room.id }}, {{ bed.num }}, {{ room.base_price }})">
                                <i class="fa fa-plus text-muted mb-1"></i> ت{{ bed.num }}
                            </div>
                            {% else %}
                            <div class="bed occupied" onclick="openLedger({{ bed.info.id }})">
                                <b class="text-primary">{{ bed.info.customer_name[:10] }}</b>
                                <span class="badge {{ 'bg-danger' if bed.info.balance > 0 else 'bg-success' }} mt-1" style="font-size: 8px;">
                                    {{ "{:,.0f}".format(bed.info.balance|abs) if bed.info.balance != 0 else 'تسویه' }}
                                </span>
                            </div>
                            {% endif %}
                        {% endfor %}
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        {% endfor %}
    </div>

    <div class="modal fade" id="checkinModal" tabindex="-1"><div class="modal-dialog"><form action="/action/checkin" method="POST" class="modal-content p-4">
        <input type="hidden" name="rid" id="in_rid"><input type="hidden" name="bnum" id="in_bnum">
        <h5 class="fw-bold mb-3">پذیرش تخت جدید</h5>
        <div class="mb-2"><label class="small">نام و نام خانوادگی</label><input type="text" name="name" class="form-control" required></div>
        <div class="mb-2"><label class="small">شماره پاسپورت / کارت ملی</label><input type="text" name="passport" class="form-control" required></div>
        <div class="row g-2 mb-2">
            <div class="col-6"><label class="small">تاریخ ورود</label><input type="date" name="checkin" class="form-control" value="{{ stats.today }}"></div>
            <div class="col-6"><label class="small">خروج احتمالی</label><input type="date" name="checkout" class="form-control"></div>
        </div>
        <div class="row g-2 mb-3">
            <div class="col-6"><label class="small">نرخ هر شب (تومان)</label><input type="number" name="rate" id="in_rate" class="form-control"></div>
            <div class="col-6"><label class="small">پیش‌پرداخت</label><input type="number" name="payment" class="form-control"></div>
        </div>
        <button class="btn btn-primary w-100 py-2 fw-bold">ثبت و ایجاد پرونده</button>
    </form></div></div>

    <div class="modal fade" id="ledgerModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content p-4" id="ledgerBody"></div></div></div>

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
            let html = `
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <div><h4 class="fw-bold m-0">${d.guest.customer_name}</h4><small>پاسپورت: ${d.guest.passport}</small></div>
                    <div class="text-end">مانده بدهی:<br><h4 class="text-danger fw-bold">${d.balance.toLocaleString()}</h4></div>
                </div>
                <div style="max-height:250px; overflow-y:auto" class="border rounded p-3 bg-light mb-3">
                    ${d.ledger.map(t => `<div class="d-flex justify-content-between py-2 border-bottom small"><span>${t.description} <br><small class="text-muted">${t.date}</small></span><b class="${t.type=='charge'?'text-danger':'text-success'}">${t.type=='charge'?'+':'-'}${t.amount.toLocaleString()}</b></div>`).join('')}
                </div>
                <form action="/action/pay" method="POST" class="input-group mb-3"><input type="hidden" name="bid" value="${d.guest.id}"><input type="number" name="amount" class="form-control" placeholder="دریافت مبلغ جدید..." required><button class="btn btn-success">ثبت دریافت</button></form>
                <div class="d-flex gap-2"><button onclick="window.print()" class="btn btn-outline-secondary flex-grow-1">چاپ رسید</button><a href="/action/checkout/${d.guest.id}" class="btn btn-danger" onclick="return confirm('آیا مسافر تسویه کامل کرده و خارج شده است؟')">خروج نهایی</a></div>
            `;
            document.getElementById('ledgerBody').innerHTML = html;
            new bootstrap.Modal(document.getElementById('ledgerModal')).show();
        }
    </script>
</body>
</html>
"""

# --- Routes ---
@app.route('/')
def index():
    if not session.get('logged_in'): return render_template_string(LOGIN_HTML)
    return redirect('/dashboard')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('u') == 'admin' and request.form.get('p') == 'admin123':
        session['logged_in'] = True
        return redirect('/dashboard')
    return "نام کاربری یا رمز عبور اشتباه است!"

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'): return redirect('/')
    run_accounting()
    conn = get_db_connection()
    rooms = [dict(r) for r in conn.execute("SELECT * FROM rooms ORDER BY floor ASC").fetchall()]
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
        'count': len(bookings),
        'today': str(date.today())
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
    conn = get_db_connection()
    checkin = request.form['checkin']
    cur = conn.execute("""INSERT INTO bookings (room_id, bed_number, customer_name, passport, checkin_date, expected_checkout, last_charge_date, daily_rate) 
                 VALUES (?,?,?,?,?,?,?,?)""", (request.form['rid'], request.form['bnum'], request.form['name'], request.form['passport'], checkin, request.form['checkout'], checkin, request.form['rate']))
    bid = cur.lastrowid
    pay = int(request.form.get('payment', 0) or 0)
    if pay > 0:
        conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'payment', ?, ?, ?)", (bid, pay, str(date.today()), "پیش‌پرداخت ورود"))
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
    conn.execute("UPDATE bookings SET is_active=0, last_charge_date=? WHERE id=?", (str(date.today()), bid))
    conn.commit()
    return redirect('/dashboard')

@app.route('/report/all')
def report_all():
    if not session.get('logged_in'): return redirect('/')
    conn = get_db_connection()
    guests = conn.execute("""SELECT b.*, r.name as rname FROM bookings b 
                           JOIN rooms r ON b.room_id = r.id 
                           WHERE b.is_active = 1""").fetchall()
    html = """
    <body style="font-family:tahoma; direction:rtl; padding:30px;">
        <h2>گزارش کل مسافران مقیم - مورخ {{ today }}</h2>
        <table border="1" style="width:100%; border-collapse:collapse; text-align:center;">
            <tr style="background:#eee;">
                <th>نام</th><th>پاسپورت</th><th>اتاق</th><th>تخت</th><th>تاریخ ورود</th><th>مانده بدهی</th>
            </tr>
            {% for g in guests %}
            <tr>
                <td>{{ g.customer_name }}</td><td>{{ g.passport }}</td><td>{{ g.rname }}</td>
                <td>{{ g.bed_number }}</td><td>{{ g.checkin_date }}</td><td>...</td>
            </tr>
            {% endfor %}
        </table>
        <button onclick="window.print()" style="margin-top:20px; padding:10px 20px;">پرینت گزارش</button>
    </body>
    """
    return render_template_string(html, guests=guests, today=date.today())

LOGIN_HTML = """
<body style="background:#f0f2f5; display:flex; justify-content:center; align-items:center; height:100vh; font-family:tahoma;">
    <form action="/login" method="POST" style="background:white; padding:40px; border-radius:15px; box-shadow:0 10px 20px rgba(0,0,0,0.1);">
        <h3>ورود به پنل هاستل</h3>
        <input name="u" placeholder="نام کاربری" style="display:block; width:250px; margin:10px 0; padding:10px;">
        <input name="p" type="password" placeholder="رمز عبور" style="display:block; width:250px; margin:10px 0; padding:10px;">
        <button style="width:100%; padding:10px; background:#4361ee; color:white; border:none; border-radius:5px;">ورود</button>
    </form>
</body>


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
