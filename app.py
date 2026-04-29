import os, sqlite3, logging
from datetime import datetime, date, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hostel_accounting_pro_2026")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hostel_main.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # ساختار پایه اتاق‌ها
        conn.execute("CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY, floor INT, name TEXT, capacity INT, base_price INT, type TEXT)")
        # سیستم رزرواسیون و اسکان
        conn.execute("CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY, room_id INT, bed_number INT, name TEXT, passport TEXT, checkin TEXT, checkout TEXT, last_charge TEXT, rate INT, active INT DEFAULT 1)")
        # اگر دیتابیس قبلاً با نسخه قدیمی ساخته شده باشد، ستون تاریخ خروج را اضافه می‌کنیم
        cols = [c[1] for c in conn.execute("PRAGMA table_info(bookings)").fetchall()]
        if "checkout" not in cols:
            conn.execute("ALTER TABLE bookings ADD COLUMN checkout TEXT")
        # دفتر روزنامه حسابداری (تمام تراکنش‌ها اینجا ثبت می‌شوند)
        conn.execute("CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, ref_id INT, type TEXT, category TEXT, amount INT, date TEXT, desc TEXT)")
        
        if conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
            rooms = [(1,'101 (خصوصی)',1,500000,'VIP'), (1,'102 (3 تخته)',3,200000,'Standard'), (1,'103 (6 تخته)',6,150000,'Standard'), (1,'104 (10 تخته)',10,120000,'Economy'), (2,'201 (پسرانه)',4,180000,'Male'), (2,'202 (دخترانه)',4,180000,'Female')]
            conn.executemany("INSERT INTO rooms (floor, name, capacity, base_price, type) VALUES (?,?,?,?,?)", rooms)
    conn.commit()

init_db()

# --- توابع کمکی برای محاسبات مشتری ---
def _to_date(value, fallback=None):
    if not value:
        return fallback
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except Exception:
        return fallback

def stay_nights(checkin, checkout=None):
    in_date = _to_date(checkin, date.today())
    out_date = _to_date(checkout, date.today()) if checkout else date.today()
    return max((out_date - in_date).days, 1)

def guest_financial_summary(conn, booking):
    bid = booking['id']
    rate = int(booking['rate'] or 0)
    nights = stay_nights(booking['checkin'], booking['checkout'])
    planned_total = nights * rate

    posted_charges = conn.execute(
        "SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='DEBIT' AND category='STAY_CHARGE'",
        (bid,)
    ).fetchone()[0] or 0

    paid = conn.execute(
        "SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='CREDIT' AND category='PAYMENT'",
        (bid,)
    ).fetchone()[0] or 0

    total = max(planned_total, posted_charges)
    balance = total - paid
    return {
        'nights': nights,
        'rate': rate,
        'total': total,
        'paid': paid,
        'balance': balance,
        'checkout_display': booking['checkout'] or str(date.today())
    }

# --- هسته حسابداری (مشابه سپیدار) ---
def update_financials():
    conn = get_db()
    today = date.today()
    active_bookings = conn.execute("SELECT * FROM bookings WHERE active = 1").fetchall()
    for b in active_bookings:
        last = _to_date(b['last_charge'], _to_date(b['checkin'], today))
        charge_until = today
        checkout_date = _to_date(b['checkout'])
        if checkout_date and checkout_date < today:
            charge_until = checkout_date
        diff = (charge_until - last).days
        if diff > 0:
            for i in range(1, diff + 1):
                day = last + timedelta(days=i)
                # ثبت سند هزینه اقامت در دفتر روزنامه
                conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'DEBIT', 'STAY_CHARGE', ?, ?, ?)", 
                             (b['id'], b['rate'], str(day), f"هزینه اقامت شب {day}"))
            conn.execute("UPDATE bookings SET last_charge = ? WHERE id = ?", (str(charge_until), b['id']))
    conn.commit()

# --- UI (ثابت و کاربردی) ---
UI = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        body { font-family: tahoma; background: #f4f7f6; }
        .stat-box { background: white; padding: 20px; border-radius: 10px; border-bottom: 5px solid #222; }
        .bed { width: 165px; min-height: 145px; border-radius: 10px; border: 1px solid #ccc; display: inline-flex; flex-direction: column; align-items: stretch; justify-content: flex-start; cursor: pointer; margin: 5px; background: #fff; font-size: 11px; vertical-align: top; padding: 8px; line-height: 1.7; text-align: right; }
        .bed-empty { align-items: center; justify-content: center; text-align: center; min-height: 75px; }
        .occupied { background: #0d6efd; color: white; border: none; }
        .debtor { border: 3px solid #dc3545 !important; box-shadow: 0 0 0 2px rgba(220,53,69,.15); }
        .settled { border: 3px solid #198754 !important; }
        .bed-title { font-weight: bold; font-size: 12px; border-bottom: 1px solid rgba(255,255,255,.35); margin-bottom: 4px; padding-bottom: 3px; }
        .bed-row { display: flex; justify-content: space-between; gap: 6px; }
        .money { direction: ltr; unicode-bidi: plaintext; }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark mb-4 p-3">
        <div class="container-fluid">
            <span class="navbar-brand">سیستم حسابداری و مدیریت هاستل (نسخه Enterprise)</span>
            <div class="d-flex gap-2">
                <button class="btn btn-warning btn-sm" onclick="new bootstrap.Modal(document.getElementById('expM')).show()">ثبت هزینه (خرید/قبوض)</button>
                <a href="/financial_report" class="btn btn-info btn-sm text-white">گزارش تراز مالی</a>
                <button class="btn btn-danger btn-sm" onclick="confirmReset()">ریست اضطراری</button>
                <a href="/logout" class="btn btn-secondary btn-sm">خروج</a>
            </div>
        </div>
    </nav>

    <div class="container-fluid px-4">
        <div class="row g-3 mb-4">
            <div class="col-md-3"><div class="stat-box" style="border-color: #198754"><b>موجودی نقد صندوق:</b><br><h4>{{ "{:,}".format(s.cash) }}</h4></div></div>
            <div class="col-md-3"><div class="stat-box" style="border-color: #dc3545"><b>کل هزینه‌ها:</b><br><h4>{{ "{:,}".format(s.exp) }}</h4></div></div>
            <div class="col-md-3"><div class="stat-box" style="border-color: #0d6efd"><b>مطالبات (بدهی مشتریان):</b><br><h4>{{ "{:,}".format(s.debt) }}</h4></div></div>
            <div class="col-md-3"><div class="stat-box" style="border-color: #ffc107"><b>سود خالص عملیاتی:</b><br><h4>{{ "{:,}".format(s.cash - s.exp) }}</h4></div></div>
        </div>

        <div class="row">
            {% for f in [1, 2] %}
            <div class="col-md-6">
                <h5 class="p-2 bg-secondary text-white rounded">طبقه {{ "اول" if f==1 else "دوم" }}</h5>
                {% for r in rooms if r.floor == f %}
                <div class="card p-3 mb-3 shadow-sm">
                    <div class="d-flex justify-content-between border-bottom pb-2 mb-2"><b>{{ r.name }}</b> <small>{{ r.type }}</small></div>
                    <div>
                        {% for b in r.beds %}
                            {% if b.status == 'empty' %}
                            <div class="bed bed-empty" onclick="openCheckin({{ r.id }}, {{ b.num }}, {{ r.base_price }})">تخت {{ b.num }}<br>خالی</div>
                            {% else %}
                            <div class="bed occupied {{ 'debtor' if b.info.balance > 0 else 'settled' }}" onclick="openLedger({{ b.info.id }})">
                                <div class="bed-title">{{ b.info.name[:18] }}</div>
                                <div class="bed-row"><span>ورود:</span><b>{{ b.info.checkin }}</b></div>
                                <div class="bed-row"><span>خروج:</span><b>{{ b.info.checkout_display }}</b></div>
                                <div class="bed-row"><span>قیمت کل:</span><b class="money">{{ "{:,}".format(b.info.total) }}</b></div>
                                <div class="bed-row"><span>پرداختی:</span><b class="money">{{ "{:,}".format(b.info.paid) }}</b></div>
                                <div class="bed-row"><span>مانده:</span><b class="money">{{ "{:,}".format(b.info.balance) }}</b></div>
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

    <div class="modal fade" id="expM" tabindex="-1"><div class="modal-dialog"><form action="/action/expense" method="POST" class="modal-content p-4">
        <h5>ثبت سند هزینه (خروجی)</h5>
        <input name="title" placeholder="بابت..." class="form-control mb-2" required>
        <input name="amount" type="number" placeholder="مبلغ (تومان)" class="form-control mb-2" required>
        <select name="cat" class="form-select mb-3"><option>قبوض</option><option>خرید مایحتاج</option><option>تعمیرات</option><option>پرسنل</option></select>
        <button class="btn btn-danger w-100">ثبت در دفتر روزنامه</button>
    </form></div></div>

    <div class="modal fade" id="checkinModal" tabindex="-1"><div class="modal-dialog"><form action="/action/checkin" method="POST" class="modal-content p-4">
        <input type="hidden" name="rid" id="in_rid"><input type="hidden" name="bnum" id="in_bnum">
        <h5>پذیرش و افتتاح حساب</h5>
        <input name="name" placeholder="نام مسافر" class="form-control mb-2" required>
        <input name="passport" placeholder="کد ملی / پاسپورت" class="form-control mb-2" required>
        <div class="row g-2 mb-3">
            <div class="col-6"><label class="small">تاریخ ورود</label><input name="checkin" type="date" class="form-control" value="{{ today }}" required></div>
            <div class="col-6"><label class="small">تاریخ خروج</label><input name="checkout" type="date" class="form-control"></div>
            <div class="col-6"><label class="small">نرخ شبانه</label><input name="rate" id="in_rate" type="number" class="form-control" required></div>
            <div class="col-6"><label class="small">دریافت اول (بیعانه)</label><input name="pay" type="number" class="form-control" value="0"></div>
        </div>
        <button class="btn btn-primary w-100">صدور فاکتور و اسکان</button>
    </form></div></div>

    <div class="modal fade" id="ledgerModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content p-4" id="ledgerBody"></div></div></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function confirmReset() { if(confirm("هشدار: تمام اطلاعات حسابداری و مسافران پاک خواهد شد!")) window.location.href="/action/reset"; }
        function openCheckin(rid, bnum, rate) {
            document.getElementById('in_rid').value=rid; document.getElementById('in_bnum').value=bnum; document.getElementById('in_rate').value=rate;
            new bootstrap.Modal(document.getElementById('checkinModal')).show();
        }
        function toman(n) { return Number(n || 0).toLocaleString(); }

        async function openLedger(bid) {
            const r = await fetch('/api/guest/' + bid); const d = await r.json();
            let html = `<div class="d-flex justify-content-between align-items-start gap-3">
                <div>
                    <h4>صورتحساب: ${d.g.name}</h4>
                    <div class="text-muted">کد ملی / پاسپورت: ${d.g.passport || '-'}</div>
                </div>
                <h4 class="${d.balance > 0 ? 'text-danger' : 'text-success'}">${toman(d.balance)} مانده</h4>
            </div>

            <div class="row g-2 my-3">
                <div class="col-md-3"><div class="border rounded p-2 bg-light"><small>تاریخ ورود</small><br><b>${d.g.checkin}</b></div></div>
                <div class="col-md-3"><div class="border rounded p-2 bg-light"><small>تاریخ خروج</small><br><b>${d.summary.checkout_display}</b></div></div>
                <div class="col-md-3"><div class="border rounded p-2 bg-light"><small>تعداد شب</small><br><b>${d.summary.nights}</b></div></div>
                <div class="col-md-3"><div class="border rounded p-2 bg-light"><small>نرخ شبانه</small><br><b>${toman(d.summary.rate)}</b></div></div>
                <div class="col-md-4"><div class="border rounded p-2"><small>قیمت کل آن بازه</small><br><b>${toman(d.summary.total)}</b></div></div>
                <div class="col-md-4"><div class="border rounded p-2"><small>جمع پرداختی</small><br><b class="text-success">${toman(d.summary.paid)}</b></div></div>
                <div class="col-md-4"><div class="border rounded p-2"><small>باقی‌مانده پرداختی</small><br><b class="${d.balance > 0 ? 'text-danger' : 'text-success'}">${toman(d.balance)}</b></div></div>
            </div>

            <div style="max-height:300px; overflow-y:auto" class="border p-2 my-3 bg-light">
                <table class="table table-sm"><thead><tr><th>تاریخ</th><th>شرح</th><th>نوع</th><th>مبلغ</th></tr></thead>
                <tbody>${d.l.map(t => `<tr><td>${t.date}</td><td>${t.desc}</td><td>${t.type == 'DEBIT' ? 'بدهکار' : 'بستانکار'}</td><td class="${t.type=='DEBIT'?'text-danger':'text-success'}">${toman(t.amount)}</td></tr>`).join('')}</tbody>
                </table>
            </div>
            <form action="/action/pay" method="POST" class="input-group mb-3">
                <input type="hidden" name="bid" value="${d.g.id}"><input name="amount" type="number" class="form-control" placeholder="مبلغ پرداختی مشتری..." required>
                <button class="btn btn-success">ثبت دریافت نقد</button>
            </form>
            <div class="d-flex gap-2"><button onclick="window.print()" class="btn btn-outline-dark w-100">چاپ فاکتور</button>
            <a href="/action/checkout/${d.g.id}" class="btn btn-danger w-100" onclick="return confirm('تصفیه نهایی؟')">تصفیه و خروج نهایی</a></div>`;
            document.getElementById('ledgerBody').innerHTML = html; new bootstrap.Modal(document.getElementById('ledgerModal')).show();
        }
    </script>
</body>
</html>
"""

# --- Routes ---
@app.route('/')
def dashboard():
    if not session.get('logged_in'): return render_template_string(LOGIN_UI)
    update_financials()
    conn = get_db()
    # نقدینگی: تمام پرداخت‌های مشتریان
    cash = conn.execute("SELECT SUM(amount) FROM journal WHERE type='CREDIT'").fetchone()[0] or 0
    # هزینه‌ها: تمام مخارج ثبت شده
    exp = conn.execute("SELECT SUM(amount) FROM journal WHERE category='EXPENSE'").fetchone()[0] or 0
    
    rooms = [dict(r) for r in conn.execute("SELECT * FROM rooms ORDER BY floor ASC").fetchall()]
    bookings = [dict(b) for b in conn.execute("SELECT * FROM bookings WHERE active=1").fetchall()]
    
    total_debt = 0
    for r in rooms:
        r['beds'] = []
        for i in range(1, r['capacity'] + 1):
            b_data = next((b for b in bookings if b['room_id']==r['id'] and b['bed_number']==i), None)
            if b_data:
                # محاسبه خلاصه مالی شخص برای نمایش روی تخت
                summary = guest_financial_summary(conn, b_data)
                b_data.update(summary)
                if b_data['balance'] > 0: total_debt += b_data['balance']
                r['beds'].append({'status': 'occupied', 'info': b_data})
            else: r['beds'].append({'status': 'empty', 'num': i})
            
    stats = {'cash': cash, 'exp': exp, 'debt': total_debt}
    return render_template_string(UI, rooms=rooms, s=stats, today=str(date.today()))

@app.route('/action/checkin', methods=['POST'])
def checkin():
    conn = get_db()
    checkin_date = request.form.get('checkin') or str(date.today())
    checkout_date = request.form.get('checkout') or None
    rate = int(request.form.get('rate') or 0)
    pay_amount = int(request.form.get('pay', 0) or 0)

    cur = conn.execute("INSERT INTO bookings (room_id, bed_number, name, passport, checkin, checkout, last_charge, rate) VALUES (?,?,?,?,?,?,?,?)",
                 (request.form['rid'], request.form['bnum'], request.form['name'], request.form['passport'], checkin_date, checkout_date, checkin_date, rate))
    bid = cur.lastrowid

    # هزینه شب اول همان ابتدا ثبت می‌شود تا مانده روی تخت از لحظه پذیرش درست باشد
    conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'DEBIT', 'STAY_CHARGE', ?, ?, ?)",
                 (bid, rate, checkin_date, f"هزینه اقامت شب اول {checkin_date}"))

    if pay_amount > 0:
        conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'CREDIT', 'PAYMENT', ?, ?, 'دریافت اولیه')", (bid, pay_amount, str(date.today())))
    conn.commit(); return redirect('/')

@app.route('/action/pay', methods=['POST'])
def pay():
    conn = get_db()
    conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'CREDIT', 'PAYMENT', ?, ?, 'دریافت وجه نقد')", (request.form['bid'], request.form['amount'], str(date.today())))
    conn.commit(); return redirect('/')

@app.route('/action/expense', methods=['POST'])
def expense():
    conn = get_db()
    conn.execute("INSERT INTO journal (type, category, amount, date, desc) VALUES ('DEBIT', 'EXPENSE', ?, ?, ?)", (request.form['amount'], str(date.today()), request.form['title']))
    conn.commit(); return redirect('/')

@app.route('/api/guest/<int:bid>')
def get_guest(bid):
    conn = get_db()
    g = dict(conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())
    l = [dict(t) for t in conn.execute("SELECT * FROM journal WHERE ref_id=? ORDER BY id DESC", (bid,)).fetchall()]
    summary = guest_financial_summary(conn, g)
    return jsonify({'g': g, 'l': l, 'summary': summary, 'balance': summary['balance'], 'bal': summary['balance']})

@app.route('/action/checkout/<int:bid>')
def checkout(bid):
    conn = get_db(); conn.execute("UPDATE bookings SET active=0, checkout=COALESCE(checkout, ?) WHERE id=?", (str(date.today()), bid)); conn.commit(); return redirect('/')

@app.route('/action/reset')
def reset():
    if os.path.exists(DB_PATH): os.remove(DB_PATH)
    init_db(); return redirect('/')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('u') == 'admin' and request.form.get('p') == 'admin123': session['logged_in'] = True
    return redirect('/')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

LOGIN_UI = """<body style="font-family:tahoma; background:#eee; display:flex; justify-content:center; align-items:center; height:100vh;"><form action="/login" method="POST" style="background:#fff; padding:40px; border-radius:10px; box-shadow:0 5px 15px rgba(0,0,0,0.1);"><h4>ورود به سیستم مالی</h4><br><input name="u" placeholder="نام کاربری" class="form-control mb-2"><input name="p" type="password" placeholder="رمز عبور" class="form-control mb-3"><button class="btn btn-primary w-100">ورود</button></form></body>"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
