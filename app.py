import os, sqlite3, logging
from datetime import datetime, date, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string

# تنظیمات اصلی
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hostel_premium_2026")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hostel_enterprise.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # جدول اتاق‌ها و طبقات
        conn.execute("CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY, floor INT, name TEXT, capacity INT, base_price INT, room_type TEXT)")
        # جدول مسافران (پذیرش)
        conn.execute("CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY, room_id INT, bed_number INT, customer_name TEXT, passport TEXT, checkin_date TEXT, last_charge_date TEXT, daily_rate INT, is_active INT DEFAULT 1)")
        # جدول تراکنش‌های مالی (درآمد و شارژ روزانه)
        conn.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY, booking_id INT, type TEXT, amount INT, date TEXT, description TEXT)")
        # جدول هزینه‌ها (خرج‌کرد هاستل)
        conn.execute("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, title TEXT, amount INT, date TEXT, category TEXT, note TEXT)")
        
        if conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
            rooms_data = [
                (1, 'اتاق ۱۰۱ (VIP)', 1, 600000, 'خصوصی'), (1, 'اتاق ۱۰۲ (۳ تخته)', 3, 250000, 'عمومی'),
                (1, 'اتاق ۱۰۳ (۶ تخته)', 6, 180000, 'عمومی'), (1, 'اتاق ۱۰۴ (۱۰ تخته)', 10, 150000, 'اقتصادی'),
                (2, 'اتاق ۲۰۱ (پسرانه)', 4, 200000, 'خوابگاه'), (2, 'اتاق ۲۰۲ (دخترانه)', 4, 200000, 'خوابگاه')
            ]
            conn.executemany("INSERT INTO rooms (floor, name, capacity, base_price, room_type) VALUES (?,?,?,?,?)", rooms_data)
    conn.commit()

init_db()

# --- منطق حسابداری هوشمند ---
def sync_accounts():
    conn = get_db()
    today = date.today()
    active_guests = conn.execute("SELECT * FROM bookings WHERE is_active = 1").fetchall()
    for guest in active_guests:
        last_charge = datetime.strptime(guest['last_charge_date'], '%Y-%m-%d').date()
        days_to_charge = (today - last_charge).days
        if days_to_charge > 0:
            for i in range(1, days_to_charge + 1):
                charge_day = last_charge + timedelta(days=i)
                conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'charge', ?, ?, ?)", 
                             (guest['id'], guest['daily_rate'], str(charge_day), f"شارژ اقامت شب {charge_day}"))
            conn.execute("UPDATE bookings SET last_charge_date = ? WHERE id = ?", (str(today), guest['id']))
    conn.commit()

# --- رابط کاربری حرفه‌ای ---
UI_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { font-family: 'Tahoma', sans-serif; background: #f4f6f9; }
        .navbar { background: #1e293b !important; box-shadow: 0 2px 10px rgba(0,0,0,0.2); }
        .card { border: none; border-radius: 15px; transition: 0.3s; }
        .stat-card { border-right: 5px solid #3b82f6; }
        .bed { width: 80px; height: 80px; border-radius: 12px; border: 2px dashed #cbd5e1; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; font-size: 11px; margin: 5px; background: white; vertical-align: top; }
        .bed.occupied { background: #3b82f6; color: white; border: none; box-shadow: 0 4px 10px rgba(59,130,246,0.4); }
        .room-title { font-weight: bold; color: #475569; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 15px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark p-3">
        <div class="container-fluid">
            <a class="navbar-brand fw-bold" href="#"><i class="fa fa-hotel me-2"></i> پنل جامع مدیریت هاستل</a>
            <div class="d-flex gap-2">
                <button class="btn btn-warning btn-sm" onclick="new bootstrap.Modal(document.getElementById('expModal')).show()">+ ثبت هزینه</button>
                <a href="/financial_report" class="btn btn-info btn-sm text-white">دفتر مالی</a>
                <button class="btn btn-outline-danger btn-sm" onclick="confirmReset()">ریست سیستم</button>
                <a href="/logout" class="btn btn-secondary btn-sm">خروج</a>
            </div>
        </div>
    </nav>

    <div class="container-fluid py-4 px-4">
        <div class="row g-3 mb-5">
            <div class="col-md-3"><div class="card p-3 stat-card">صندوق نقد (درآمد): <br><span class="h4 text-success fw-bold">{{ "{:,}".format(stats.income) }}</span></div></div>
            <div class="col-md-3"><div class="card p-3 stat-card" style="border-color:#ef4444">هزینه‌های کل: <br><span class="h4 text-danger fw-bold">{{ "{:,}".format(stats.exp) }}</span></div></div>
            <div class="col-md-3"><div class="card p-3 stat-card" style="border-color:#10b981">سود خالص: <br><span class="h4 text-primary fw-bold">{{ "{:,}".format(stats.profit) }}</span></div></div>
            <div class="col-md-3"><div class="card p-3 stat-card" style="border-color:#f59e0b">طلب از مسافران: <br><span class="h4 text-warning fw-bold">{{ "{:,}".format(stats.debt) }}</span></div></div>
        </div>

        <div class="row">
            {% for floor in [1, 2] %}
            <div class="col-lg-6">
                <h4 class="mb-4"><i class="fa fa-layer-group"></i> طبقه {{ "اول" if floor == 1 else "دوم" }}</h4>
                {% for room in rooms if room.floor == floor %}
                <div class="card p-3 mb-4 shadow-sm">
                    <div class="room-title d-flex justify-content-between align-items-center">
                        <span>{{ room.name }}</span>
                        <span class="badge bg-light text-dark small fw-normal">{{ room.room_type }}</span>
                    </div>
                    <div class="d-flex flex-wrap">
                        {% for bed in room.beds %}
                            {% if bed.status == 'empty' %}
                            <div class="bed" onclick="openCheckin({{ room.id }}, {{ bed.num }}, {{ room.base_price }})">تخت {{ bed.num }}<br>خالی</div>
                            {% else %}
                            <div class="bed occupied" onclick="openLedger({{ bed.info.id }})">
                                <strong>{{ bed.info.customer_name[:10] }}</strong>
                                <small class="d-block mt-1">{{ "{:,}".format(bed.info.balance) if bed.info.balance > 0 else 'تصفیه' }}</small>
                            </div>
                            {% endif %}
                        {% endfor %}
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
    </div>

    <div class="modal fade" id="checkinModal" tabindex="-1"><div class="modal-dialog"><form action="/action/checkin" method="POST" class="modal-content p-4">
        <input type="hidden" name="rid" id="in_rid"><input type="hidden" name="bnum" id="in_bnum">
        <h5 class="fw-bold mb-3 text-primary">ورود مسافر جدید</h5>
        <input name="name" placeholder="نام و نام خانوادگی" class="form-control mb-2" required>
        <input name="passport" placeholder="کد ملی / پاسپورت" class="form-control mb-2" required>
        <div class="row g-2 mb-3">
            <div class="col-6"><label class="small">نرخ هر شب (تومان)</label><input name="rate" id="in_rate" type="number" class="form-control"></div>
            <div class="col-6"><label class="small">پیش‌پرداخت نقد</label><input name="pay" type="number" class="form-control" value="0"></div>
        </div>
        <button class="btn btn-primary w-100">تایید پذیرش</button>
    </form></div></div>

    <div class="modal fade" id="expModal" tabindex="-1"><div class="modal-dialog"><form action="/action/expense" method="POST" class="modal-content p-4">
        <h5 class="fw-bold mb-3 text-danger">ثبت هزینه جدید هاستل</h5>
        <input name="title" placeholder="بابت..." class="form-control mb-2" required>
        <input name="amount" type="number" placeholder="مبلغ (تومان)" class="form-control mb-2" required>
        <select name="cat" class="form-select mb-3"><option>قبوض و اجاره</option><option>خرید مایحتاج</option><option>تعمیرات</option><option>پرسنل</option></select>
        <button class="btn btn-danger w-100">ثبت خروجی از صندوق</button>
    </form></div></div>

    <div class="modal fade" id="ledgerModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content p-4" id="ledgerBody"></div></div></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function confirmReset() { if(confirm("آیا مطمئن هستید که می‌خواهید تمام اطلاعات پاک شود؟")) window.location.href="/action/reset"; }
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
                <div class="d-flex justify-content-between align-items-center border-bottom pb-2">
                    <h5>صورتحساب: ${d.guest.customer_name}</h5>
                    <h5 class="text-danger">بدهی: ${d.balance.toLocaleString()}</h5>
                </div>
                <div style="max-height:250px; overflow-y:auto" class="my-3 p-2 bg-light small">
                    ${d.ledger.map(t => `<div class="d-flex justify-content-between border-bottom py-1"><span>${t.description}</span><b>${t.amount.toLocaleString()}</b></div>`).join('')}
                </div>
                <form action="/action/pay" method="POST" class="input-group mb-3">
                    <input type="hidden" name="bid" value="${d.guest.id}">
                    <input name="amount" type="number" class="form-control" placeholder="مبلغ دریافتی جدید..." required>
                    <button class="btn btn-success">ثبت دریافت</button>
                </form>
                <div class="d-flex gap-2">
                    <button onclick="window.print()" class="btn btn-outline-secondary w-100">چاپ فاکتور</button>
                    <a href="/action/checkout/${d.guest.id}" class="btn btn-danger w-100" onclick="return confirm('تصفیه نهایی و خروج؟')">تصفیه و خروج</a>
                </div>`;
            document.getElementById('ledgerBody').innerHTML = html;
            new bootstrap.Modal(document.getElementById('ledgerModal')).show();
        }
    </script>
</body>
</html>
"""

# --- مسیرهای سیستم ---
@app.route('/')
def dashboard():
    if not session.get('logged_in'): return render_template_string(LOGIN_UI)
    sync_accounts()
    conn = get_db()
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
                c = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (b_data['id'],)).fetchone()[0] or 0
                p = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'", (b_data['id'],)).fetchone()[0] or 0
                b_data['balance'] = c - p
                if b_data['balance'] > 0: total_debt += b_data['balance']
                r['beds'].append({'status': 'occupied', 'info': b_data})
            else:
                r['beds'].append({'status': 'empty', 'num': i})
    
    stats = {'income': income, 'exp': exp, 'profit': income - exp, 'debt': total_debt}
    return render_template_string(UI_TEMPLATE, rooms=rooms, stats=stats)

@app.route('/action/checkin', methods=['POST'])
def action_checkin():
    conn = get_db()
    cur = conn.execute("INSERT INTO bookings (room_id, bed_number, customer_name, passport, checkin_date, last_charge_date, daily_rate) VALUES (?,?,?,?,?,?,?)", 
                 (request.form['rid'], request.form['bnum'], request.form['name'], request.form['passport'], str(date.today()), str(date.today()), request.form['rate']))
    if int(request.form.get('pay', 0)) > 0:
        conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'payment', ?, ?, 'پیش‌پرداخت ورود')", (cur.lastrowid, request.form['pay'], str(date.today())))
    conn.commit(); return redirect('/')

@app.route('/action/expense', methods=['POST'])
def action_expense():
    conn = get_db(); conn.execute("INSERT INTO expenses (title, amount, date, category) VALUES (?, ?, ?, ?)", (request.form['title'], request.form['amount'], str(date.today()), request.form['cat']))
    conn.commit(); return redirect('/')

@app.route('/api/guest/<int:bid>')
def api_guest(bid):
    conn = get_db()
    guest = dict(conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())
    ledger = [dict(t) for t in conn.execute("SELECT * FROM transactions WHERE booking_id=? ORDER BY id DESC", (bid,)).fetchall()]
    c = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (bid,)).fetchone()[0] or 0
    p = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'", (bid,)).fetchone()[0] or 0
    return jsonify({'guest': guest, 'ledger': ledger, 'balance': c - p})

@app.route('/action/pay', methods=['POST'])
def action_pay():
    conn = get_db(); conn.execute("INSERT INTO transactions (booking_id, type, amount, date, description) VALUES (?, 'payment', ?, ?, 'دریافت وجه')", (request.form['bid'], request.form['amount'], str(date.today())))
    conn.commit(); return redirect('/')

@app.route('/action/checkout/<int:bid>')
def action_checkout(bid):
    conn = get_db(); conn.execute("UPDATE bookings SET is_active=0 WHERE id=?", (bid,)); conn.commit(); return redirect('/')

@app.route('/action/reset')
def reset():
    if os.path.exists(DB_PATH): os.remove(DB_PATH)
    init_db(); return redirect('/')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('u') == 'admin' and request.form.get('p') == 'admin123':
        session['logged_in'] = True
    return redirect('/')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

LOGIN_UI = """<body style="font-family:tahoma; background:#e2e8f0; display:flex; justify-content:center; align-items:center; height:100vh;"><form action="/login" method="POST" style="background:white; padding:40px; border-radius:15px; box-shadow:0 10px 25px rgba(0,0,0,0.1);"><h4>مدیریت هوشمند هاستل</h4><br><input name="u" placeholder="نام کاربری" class="form-control mb-2"><input name="p" type="password" placeholder="رمز عبور" class="form-control mb-3"><button class="btn btn-primary w-100">ورود به سیستم</button></form></body>"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
