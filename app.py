import os, sqlite3, logging
from datetime import datetime, date, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hostel-ultra-safe-2026")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "hostel_main.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY AUTOINCREMENT, floor INTEGER, name TEXT, capacity INTEGER, base_price INTEGER, room_type TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER, bed_number INTEGER, customer_name TEXT, passport TEXT, checkin_date TEXT, last_charge_date TEXT, daily_rate INTEGER, is_active INTEGER DEFAULT 1)")
        conn.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER, type TEXT, amount INTEGER, date TEXT, description TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, amount INTEGER, date TEXT, category TEXT, note TEXT)")
        
        if conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
            rooms_data = [(1,'101 (خصوصی)',1,500000,'Private'), (1,'102 (3 تخت)',3,200000,'Dorm'), (1,'103 (6 تخت)',6,150000,'Dorm'), (1,'104 (10 تخت)',10,120000,'Dorm'), (2,'201 (پسرانه)',4,180000,'Dorm'), (2,'202 (دخترانه)',4,180000,'Dorm')]
            conn.executemany("INSERT INTO rooms (floor, name, capacity, base_price, room_type) VALUES (?,?,?,?,?)", rooms_data)
        conn.commit()

init_db()

# --- سیستم تصفیه و حسابداری ---
def run_accounting():
    conn = get_db_connection()
    today = date.today()
    guests = conn.execute("SELECT * FROM bookings WHERE is_active = 1").fetchall()
    for g in guests:
        last = datetime.strptime(g['last_charge_date'], '%Y-%m-%d').date()
        if (today - last).days > 0:
            for i in range(1, (today - last).days + 1):
                day = last + timedelta(days=i)
                conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'charge', ?, ?, ?)", (g['id'], g['daily_rate'], str(day), f"اجاره شب {day}"))
            conn.execute("UPDATE bookings SET last_charge_date = ? WHERE id = ?", (str(today), g['id']))
    conn.commit()
    conn.close()

# --- UI ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { font-family: tahoma; background: #f0f2f5; }
        .stat-card { background: white; border-radius: 12px; padding: 15px; border-right: 5px solid #4361ee; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .bed { width: 65px; height: 65px; border-radius: 8px; border: 1px solid #ddd; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; margin: 3px; font-size: 10px; background: white; transition: 0.2s; vertical-align: top; }
        .bed.occupied { background: #4361ee; color: white; border: none; }
        .room-box { background: white; border-radius: 15px; padding: 15px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark mb-4 p-3 shadow">
        <div class="container-fluid">
            <span class="navbar-brand fw-bold">HOSTEL ERP v3.0</span>
            <div class="d-flex gap-2">
                <button class="btn btn-warning btn-sm" onclick="new bootstrap.Modal(document.getElementById('expModal')).show()">+ ثبت هزینه</button>
                <a href="/report/all" class="btn btn-info btn-sm text-white">گزارشات</a>
                <button class="btn btn-danger btn-sm" onclick="confirmReset()">ریست کل سیستم</button>
                <a href="/logout" class="btn btn-outline-light btn-sm">خروج</a>
            </div>
        </div>
    </nav>

    <div class="container-fluid px-4">
        <div class="row g-3 mb-4">
            <div class="col-md-3"><div class="stat-card"><b>نقدینگی کل:</b><br><span class="text-success h4">{{ "{:,.0f}".format(stats.income) }}</span></div></div>
            <div class="col-md-3"><div class="stat-card" style="border-color:#e63946"><b>مجموع هزینه‌ها:</b><br><span class="text-danger h4">{{ "{:,.0f}".format(stats.exp) }}</span></div></div>
            <div class="col-md-3"><div class="stat-card" style="border-color:#2a9d8f"><b>سود خالص فعلی:</b><br><span class="text-primary h4">{{ "{:,.0f}".format(stats.profit) }}</span></div></div>
            <div class="col-md-3"><div class="stat-card" style="border-color:#f4a261"><b>مطالبات از مسافران:</b><br><span class="text-warning h4">{{ "{:,.0f}".format(stats.debt) }}</span></div></div>
        </div>

        <div class="row">
            {% for floor in [1, 2] %}
            <div class="col-md-6">
                <h5 class="mb-3 px-2">طبقه {{ "اول" if floor == 1 else "دوم" }}</h5>
                {% for room in rooms if room.floor == floor %}
                <div class="room-box shadow-sm">
                    <div class="d-flex justify-content-between border-bottom mb-2 pb-1">
                        <small class="fw-bold">{{ room.name }}</small>
                        <small class="text-muted">{{ room.room_type }}</small>
                    </div>
                    {% for bed in room.beds %}
                        {% if bed.status == 'empty' %}
                        <div class="bed" onclick="openCheckin({{ room.id }}, {{ bed.num }}, {{ room.base_price }})">خالی<br>تخت {{ bed.num }}</div>
                        {% else %}
                        <div class="bed occupied" onclick="openLedger({{ bed.info.id }})">{{ bed.info.customer_name[:10] }}<br>{{ "{:,.0f}".format(bed.info.balance) if bed.info.balance > 0 else 'تصفیه' }}</div>
                        {% endif %}
                    {% endfor %}
                </div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
    </div>

    <div class="modal fade" id="expModal" tabindex="-1"><div class="modal-dialog"><form action="/action/expense" method="POST" class="modal-content p-4">
        <h5>ثبت هزینه جدید</h5>
        <input name="title" placeholder="بابت..." class="form-control mb-2" required>
        <input name="amount" type="number" placeholder="مبلغ (تومان)" class="form-control mb-2" required>
        <select name="cat" class="form-select mb-2"><option>اجاره/قبوض</option><option>نظافت</option><option>تعمیرات</option><option>غذا/سرویس</option></select>
        <textarea name="note" placeholder="توضیحات اضافه..." class="form-control mb-3"></textarea>
        <button class="btn btn-danger w-100">ثبت خروجی مالی</button>
    </form></div></div>

    <div class="modal fade" id="checkinModal" tabindex="-1"><div class="modal-dialog"><form action="/action/checkin" method="POST" class="modal-content p-4">
        <input type="hidden" name="rid" id="in_rid"><input type="hidden" name="bnum" id="in_bnum">
        <h5>پذیرش تخت <span id="b_txt"></span></h5>
        <input name="name" placeholder="نام مسافر" class="form-control mb-2" required>
        <input name="passport" placeholder="پاسپورت / کد ملی" class="form-control mb-2" required>
        <input name="rate" id="in_rate" type="number" placeholder="اجاره هر شب" class="form-control mb-2" required>
        <input name="pay" type="number" placeholder="پیش‌پرداخت (اختیاری)" class="form-control mb-3">
        <button class="btn btn-primary w-100">تایید و ورود</button>
    </form></div></div>

    <div class="modal fade" id="ledgerModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content p-4" id="ledgerBody"></div></div></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function confirmReset() {
            if(confirm("هشدار بسیار جدی: آیا می‌خواهید کل اطلاعات سیستم (مسافران و مالی) را پاک کنید؟ این عمل برگشت‌ناپذیر است!")) {
                window.location.href = "/action/reset-all";
            }
        }
        function openCheckin(rid, bnum, rate) {
            document.getElementById('in_rid').value = rid;
            document.getElementById('in_bnum').value = bnum;
            document.getElementById('b_txt').innerText = bnum;
            document.getElementById('in_rate').value = rate;
            new bootstrap.Modal(document.getElementById('checkinModal')).show();
        }
        async function openLedger(bid) {
            const res = await fetch('/api/guest/' + bid);
            const d = await res.json();
            let html = `
                <div class="d-flex justify-content-between mb-3">
                    <h4>${d.guest.customer_name}</h4>
                    <h4 class="text-danger">${d.balance.toLocaleString()} تومان بدهی</h4>
                </div>
                <div style="max-height:200px; overflow-y:auto" class="border p-2 mb-3 bg-light small">
                    ${d.ledger.map(t => `<div class="d-flex justify-content-between border-bottom py-1"><span>${t.description}</span><b>${t.amount.toLocaleString()}</b></div>`).join('')}
                </div>
                <form action="/action/pay" method="POST" class="input-group mb-3">
                    <input type="hidden" name="bid" value="${d.guest.id}">
                    <input type="number" name="amount" class="form-control" placeholder="مبلغ دریافتی جدید..." required>
                    <button class="btn btn-success">ثبت پول</button>
                </form>
                <div class="d-flex gap-2">
                    <a href="/action/checkout/${d.guest.id}" class="btn btn-danger w-100" onclick="return confirm('تصفیه و خروج نهایی؟')">تصفیه و خروج</a>
                </div>`;
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
    return "ورود ناموفق"

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'): return redirect('/')
    run_accounting()
    conn = get_db_connection()
    income = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='payment'").fetchone()[0] or 0
    exp = conn.execute("SELECT SUM(amount) FROM expenses").fetchone()[0] or 0
    
    rooms = [dict(r) for r in conn.execute("SELECT * FROM rooms ORDER BY floor ASC").fetchall()]
    bookings = [dict(b) for b in conn.execute("SELECT * FROM bookings WHERE is_active=1").fetchall()]
    
    total_debt = 0
    for r in rooms:
        r['beds'] = []
        for i in range(1, r['capacity'] + 1):
            b_data = next((b for b in bookings if b['room_id'] == r['id'] and b['bed_number'] == i), None)
            if b_data:
                # محاسبه مانده حساب برای هر نفر
                c = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (b_data['id'],)).fetchone()[0] or 0
                p = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'", (b_data['id'],)).fetchone()[0] or 0
                b_data['balance'] = c - p
                if b_data['balance'] > 0: total_debt += b_data['balance']
                r['beds'].append({'status': 'occupied', 'info': b_data})
            else:
                r['beds'].append({'status': 'empty', 'num': i})
    
    stats = {'income': income, 'exp': exp, 'profit': income - exp, 'debt': total_debt, 'today': str(date.today())}
    conn.close()
    return render_template_string(DASHBOARD_HTML, rooms=rooms, stats=stats)

@app.route('/action/checkin', methods=['POST'])
def action_checkin():
    conn = get_db_connection()
    cur = conn.execute("INSERT INTO bookings (room_id, bed_number, customer_name, passport, checkin_date, last_charge_date, daily_rate) VALUES (?,?,?,?,?,?,?)", 
                 (request.form['rid'], request.form['bnum'], request.form['name'], request.form['passport'], str(date.today()), str(date.today()), request.form['rate']))
    if int(request.form.get('pay', 0)) > 0:
        conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'payment', ?, ?, 'پیش‌پرداخت')", (cur.lastrowid, request.form['pay'], str(date.today())))
    conn.commit()
    return redirect('/dashboard')

@app.route('/action/expense', methods=['POST'])
def action_expense():
    conn = get_db_connection()
    conn.execute("INSERT INTO expenses (title, amount, date, category, note) VALUES (?, ?, ?, ?, ?)", (request.form['title'], request.form['amount'], str(date.today()), request.form['cat'], request.form['note']))
    conn.commit()
    return redirect('/dashboard')

@app.route('/action/reset-all')
def reset_all():
    if not session.get('logged_in'): return redirect('/')
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    return redirect('/')

@app.route('/api/guest/<int:bid>')
def api_guest(bid):
    conn = get_db_connection()
    guest = dict(conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())
    ledger = [dict(t) for t in conn.execute("SELECT * FROM transactions WHERE booking_id=? ORDER BY id DESC", (bid,)).fetchall()]
    c = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (bid,)).fetchone()[0] or 0
    p = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'", (bid,)).fetchone()[0] or 0
    conn.close()
    return jsonify({'guest': guest, 'ledger': ledger, 'balance': c - p})

@app.route('/action/pay', methods=['POST'])
def action_pay():
    conn = get_db_connection()
    conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'payment', ?, ?, 'دریافت وجه')", (request.form['bid'], request.form['amount'], str(date.today())))
    conn.commit()
    return redirect('/dashboard')

@app.route('/action/checkout/<int:bid>')
def action_checkout(bid):
    conn = get_db_connection()
    conn.execute("UPDATE bookings SET is_active=0 WHERE id=?", (bid,))
    conn.commit()
    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

LOGIN_HTML = """<body style="font-family:tahoma; background:#f0f2f5; display:flex; justify-content:center; align-items:center; height:100vh;"><form action="/login" method="POST" style="background:white; padding:40px; border-radius:15px; box-shadow:0 10px 25px rgba(0,0,0,0.1);"><h3>مدیریت هاستل</h3><input name="u" placeholder="نام کاربری" class="form-control mb-2" required><input name="p" type="password" placeholder="رمز عبور" class="form-control mb-3" required><button class="btn btn-primary w-100">ورود</button></form></body>"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
