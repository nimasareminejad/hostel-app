import os, sqlite3, logging
from datetime import datetime, date, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string

# تنظیمات اولیه
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hostel_pro_ultra_2026")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hostel_erp.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # جداول استاندارد هتلی
        conn.execute("CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY, floor INT, name TEXT, capacity INT, base_price INT, type TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY, room_id INT, bed_number INT, name TEXT, passport TEXT, checkin TEXT, last_charge TEXT, rate INT, active INT DEFAULT 1)")
        conn.execute("CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY, booking_id INT, type TEXT, amount INT, date TEXT, desc TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, title TEXT, amount INT, date TEXT, cat TEXT)")
        
        if conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
            rooms = [(1, '۱۰۱ (خصوصی)', 1, 500000, 'VIP'), (1, '۱۰۲ (۳ تخته)', 3, 200000, 'Standard'), (1, '۱۰۳ (۶ تخته)', 6, 150000, 'Dorm'), (1, '۱۰۴ (۱۰ تخته)', 10, 120000, 'Economy'), (2, '۲۰۱ (پسرانه)', 4, 180000, 'Male'), (2, '۲۰۲ (دخترانه)', 4, 180000, 'Female')]
            conn.executemany("INSERT INTO rooms (floor, name, capacity, base_price, type) VALUES (?,?,?,?,?)", rooms)
    conn.commit()

init_db()

# --- سیستم حسابداری خودکار روزانه ---
def sync_accounts():
    conn = get_db()
    today = date.today()
    active = conn.execute("SELECT * FROM bookings WHERE active = 1").fetchall()
    for b in active:
        last = datetime.strptime(b['last_charge'], '%Y-%m-%d').date()
        days = (today - last).days
        if days > 0:
            for i in range(1, days + 1):
                cur_day = last + timedelta(days=i)
                conn.execute("INSERT INTO transactions (booking_id, type, amount, date, desc) VALUES (?, 'charge', ?, ?, ?)", (b['id'], b['rate'], str(cur_day), f"شارژ اقامت روز {cur_day}"))
            conn.execute("UPDATE bookings SET last_charge = ? WHERE id = ?", (str(today), b['id']))
    conn.commit()

# --- رابط کاربری (UI) ---
MAIN_UI = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        body { font-family: tahoma; background: #f8f9fa; }
        .card { border: none; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); }
        .bed { width: 75px; height: 75px; border-radius: 10px; border: 2px dashed #ddd; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; font-size: 11px; margin: 4px; background: white; transition: 0.3s; }
        .occupied { background: #4361ee; color: white; border: none; box-shadow: 0 4px 8px rgba(67,97,238,0.3); }
        .stat-val { font-size: 22px; font-weight: bold; }
        .nav-link { color: #fff; opacity: 0.8; } .nav-link:hover { opacity: 1; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4 p-3 shadow-sm">
        <div class="container-fluid">
            <a class="navbar-brand fw-bold" href="#">سیستم جامع هاستل (نسخه هتلی)</a>
            <div class="navbar-nav ms-auto">
                <button class="btn btn-warning btn-sm mx-1" onclick="new bootstrap.Modal(document.getElementById('expM')).show()">+ ثبت هزینه</button>
                <a href="/ledger_all" class="btn btn-info btn-sm mx-1 text-white">دفتر مالی</a>
                <button class="btn btn-danger btn-sm mx-1" onclick="confirmReset()">ریست سیستم</button>
                <a href="/logout" class="btn btn-outline-light btn-sm mx-1">خروج</a>
            </div>
        </div>
    </nav>

    <div class="container-fluid px-4">
        <div class="row g-3 mb-4">
            <div class="col-md-3"><div class="card p-3 text-center border-start border-success border-5">صندوق (نقد): <br><span class="text-success stat-val">{{ "{:,}".format(s.income) }}</span></div></div>
            <div class="col-md-3"><div class="card p-3 text-center border-start border-danger border-5">هزینه‌ها: <br><span class="text-danger stat-val">{{ "{:,}".format(s.exp) }}</span></div></div>
            <div class="col-md-3"><div class="card p-3 text-center border-start border-primary border-5">سود خالص: <br><span class="text-primary stat-val">{{ "{:,}".format(s.profit) }}</span></div></div>
            <div class="col-md-3"><div class="card p-3 text-center border-start border-warning border-5">طلب از مسافر: <br><span class="text-warning stat-val">{{ "{:,}".format(s.debt) }}</span></div></div>
        </div>

        <div class="row">
            {% for f in [1, 2] %}
            <div class="col-lg-6">
                <h5 class="mb-3 text-secondary">طبقه {{ "اول" if f==1 else "دوم" }}</h5>
                {% for r in rooms if r.floor == f %}
                <div class="card p-3 mb-3">
                    <div class="d-flex justify-content-between mb-2"><strong>{{ r.name }}</strong> <span class="badge bg-light text-dark">{{ r.type }}</span></div>
                    <div class="d-flex flex-wrap">
                        {% for b in r.beds %}
                            {% if b.status == 'empty' %}
                            <div class="bed" onclick="openCheckin({{ r.id }}, {{ b.num }}, {{ r.base_price }})">تخت {{ b.num }}<br>خالی</div>
                            {% else %}
                            <div class="bed occupied" onclick="openLedger({{ b.info.id }})">{{ b.info.name[:10] }}<br>{{ "{:,}".format(b.info.bal) if b.info.bal > 0 else 'تصفیه' }}</div>
                            {% endif %}
                        {% endfor %}
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
    </div>

    <div class="modal fade" id="expM" tabindex="-1"><div class="modal-dialog"><form action="/add_exp" method="POST" class="modal-content p-4">
        <h5>ثبت هزینه جدید</h5>
        <input name="t" placeholder="عنوان (مثلاً قبض برق)" class="form-control mb-2" required>
        <input name="a" type="number" placeholder="مبلغ" class="form-control mb-2" required>
        <select name="c" class="form-select mb-3"><option>اجاره/قبوض</option><option>خرید لوازم</option><option>نظافت</option><option>سایر</option></select>
        <button class="btn btn-danger w-100">ثبت خروجی</button>
    </form></div></div>

    <div class="modal fade" id="checkM" tabindex="-1"><div class="modal-dialog"><form action="/checkin" method="POST" class="modal-content p-4">
        <input type="hidden" name="rid" id="rid"><input type="hidden" name="bnum" id="bnum">
        <h5>پذیرش مسافر - تخت <span id="btxt"></span></h5>
        <input name="n" placeholder="نام مسافر" class="form-control mb-2" required>
        <input name="p" placeholder="پاسپورت / کد ملی" class="form-control mb-2" required>
        <div class="row g-2 mb-3">
            <div class="col-6"><label class="small text-muted">نرخ شبانه</label><input name="r" id="rate" type="number" class="form-control"></div>
            <div class="col-6"><label class="small text-muted">پیش‌پرداخت</label><input name="pay" type="number" class="form-control" value="0"></div>
        </div>
        <button class="btn btn-primary w-100">تایید و اسکان</button>
    </form></div></div>

    <div class="modal fade" id="ledgerM" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content p-4" id="lBody"></div></div></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function confirmReset() { if(confirm("آیا از پاک کردن کل دیتابیس اطمینان دارید؟")) window.location.href="/reset"; }
        function openCheckin(rid, bnum, rate) {
            document.getElementById('rid').value=rid; document.getElementById('bnum').value=bnum;
            document.getElementById('btxt').innerText=bnum; document.getElementById('rate').value=rate;
            new bootstrap.Modal(document.getElementById('checkM')).show();
        }
        async function openLedger(bid) {
            const r = await fetch('/guest/' + bid); const d = await r.json();
            let html = `<div class="d-flex justify-content-between"><h4>${d.g.name}</h4><h4 class="text-danger">${d.bal.toLocaleString()} بدهی</h4></div>
            <div style="max-height:250px; overflow-y:auto" class="border p-2 my-3 bg-light">
                ${d.l.map(t => `<div class="d-flex justify-content-between border-bottom py-1 small"><span>${t.desc}</span><b>${t.amount.toLocaleString()}</b></div>`).join('')}
            </div>
            <form action="/pay" method="POST" class="input-group mb-3"><input type="hidden" name="bid" value="${d.g.id}"><input name="a" type="number" class="form-control" placeholder="دریافت وجه..."><button class="btn btn-success">ثبت پول</button></form>
            <div class="d-flex gap-2"><a href="/checkout/${d.g.id}" class="btn btn-outline-danger w-100" onclick="return confirm('تصفیه نهایی؟')">تصفیه و خروج</a></div>`;
            document.getElementById('lBody').innerHTML = html; new bootstrap.Modal(document.getElementById('ledgerM')).show();
        }
    </script>
</body>
</html>
"""

# --- مسیرها (Routes) ---
@app.route('/')
def dashboard():
    if not session.get('logged_in'): return render_template_string(LOGIN_UI)
    sync_accounts()
    conn = get_db()
    inc = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='payment'").fetchone()[0] or 0
    exp = conn.execute("SELECT SUM(amount) FROM expenses").fetchone()[0] or 0
    
    rooms = [dict(r) for r in conn.execute("SELECT * FROM rooms ORDER BY floor ASC").fetchall()]
    bookings = [dict(b) for b in conn.execute("SELECT * FROM bookings WHERE active=1").fetchall()]
    
    total_debt = 0
    for r in rooms:
        r['beds'] = []
        for i in range(1, r['capacity'] + 1):
            b_data = next((b for b in bookings if b['room_id']==r['id'] and b['bed_number']==i), None)
            if b_data:
                c = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (b_data['id'],)).fetchone()[0] or 0
                p = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'", (b_data['id'],)).fetchone()[0] or 0
                b_data['bal'] = c - p
                if b_data['bal'] > 0: total_debt += b_data['bal']
                r['beds'].append({'status': 'occupied', 'info': b_data})
            else: r['beds'].append({'status': 'empty', 'num': i})
            
    stats = {'income': inc, 'exp': exp, 'profit': inc - exp, 'debt': total_debt}
    return render_template_string(MAIN_UI, rooms=rooms, s=stats)

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('u') == 'admin' and request.form.get('p') == 'admin123':
        session['logged_in'] = True
    return redirect('/')

@app.route('/checkin', methods=['POST'])
def checkin():
    conn = get_db()
    cur = conn.execute("INSERT INTO bookings (room_id, bed_number, name, passport, checkin, last_charge, rate) VALUES (?,?,?,?,?,?,?)", 
                 (request.form['rid'], request.form['bnum'], request.form['n'], request.form['p'], str(date.today()), str(date.today()), request.form['r']))
    if int(request.form.get('pay', 0)) > 0:
        conn.execute("INSERT INTO transactions (booking_id, type, amount, date, desc) VALUES (?, 'payment', ?, ?, 'پیش‌پرداخت')", (cur.lastrowid, request.form['pay'], str(date.today())))
    conn.commit(); return redirect('/')

@app.route('/pay', methods=['POST'])
def pay():
    conn = get_db()
    conn.execute("INSERT INTO transactions (booking_id, type, amount, date, desc) VALUES (?, 'payment', ?, ?, 'دریافت وجه')", (request.form['bid'], request.form['a'], str(date.today())))
    conn.commit(); return redirect('/')

@app.route('/add_exp', methods=['POST'])
def add_exp():
    conn = get_db(); conn.execute("INSERT INTO expenses (title, amount, date, cat) VALUES (?, ?, ?, ?)", (request.form['t'], request.form['a'], str(date.today()), request.form['c']))
    conn.commit(); return redirect('/')

@app.route('/guest/<int:bid>')
def get_guest(bid):
    conn = get_db()
    g = dict(conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())
    l = [dict(t) for t in conn.execute("SELECT * FROM transactions WHERE booking_id=? ORDER BY id DESC", (bid,)).fetchall()]
    c = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (bid,)).fetchone()[0] or 0
    p = conn.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'", (bid,)).fetchone()[0] or 0
    return jsonify({'g': g, 'l': l, 'bal': c-p})

@app.route('/checkout/<int:bid>')
def checkout(bid):
    conn = get_db(); conn.execute("UPDATE bookings SET active=0 WHERE id=?", (bid,)); conn.commit(); return redirect('/')

@app.route('/reset')
def reset():
    if session.get('logged_in') and os.path.exists(DB_PATH): os.remove(DB_PATH); init_db()
    return redirect('/')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

LOGIN_UI = """<body style="font-family:tahoma; background:#f0f2f5; display:flex; justify-content:center; align-items:center; height:100vh;"><form action="/login" method="POST" style="background:white; padding:40px; border-radius:15px; box-shadow:0 10px 25px rgba(0,0,0,0.1);"><h4>ورود به مدیریت هاستل</h4><input name="u" placeholder="Admin" class="form-control mb-2"><input name="p" type="password" placeholder="Pass" class="form-control mb-3"><button class="btn btn-primary w-100">ورود</button></form></body>"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
