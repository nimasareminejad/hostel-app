import os, sqlite3, requests
from datetime import datetime, date, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string

# ==========================================================
# بخش تنظیمات - اطلاعات خود را اینجا وارد کنید
# ==========================================================
CONFIG = {
    "HOSTEL_NAME": "نام هاستل شما",
    "ULTRAMSG_INSTANCE": "YOUR_INSTANCE_ID", # اینجا وارد شود
    "ULTRAMSG_TOKEN": "YOUR_TOKEN",         # اینجا وارد شود
    "MANAGER_PHONE": "989120000000",        # شماره مدیر برای اعلان‌ها
    "BOOKING_ICAL_URL": "YOUR_ICAL_URL"     # لینک آی‌کال بوکینگ
}

app = Flask(__name__)
app.secret_key = "hostel_full_pms_2026"
DB_PATH = "hostel_pro.db"

# ==========================================================
# هسته پایگاه داده
# ==========================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # اتاق‌ها
        conn.execute("CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY, floor INT, name TEXT, capacity INT, base_price INT, type TEXT)")
        # رزروها و مسافران
        conn.execute("CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY, room_id INT, bed_number INT, name TEXT, phone TEXT, passport TEXT, checkin TEXT, checkout TEXT, last_charge TEXT, rate INT, status TEXT DEFAULT 'ACTIVE')")
        # دفتر مالی (Journal)
        conn.execute("CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, ref_id INT, type TEXT, category TEXT, amount INT, date TEXT, desc TEXT)")
        
        if conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
            rooms = [(1,'101 (خصوصی)',1,500000,'VIP'), (1,'102 (3 تخت)',3,200000,'Dorm'), (1,'103 (6 تخت)',6,150000,'Dorm'), (1,'104 (10 تخت)',10,120000,'Dorm'), (2,'201 (پسرانه)',4,180000,'Dorm'), (2,'202 (دخترانه)',4,180000,'Dorm')]
            conn.executemany("INSERT INTO rooms (floor, name, capacity, base_price, type) VALUES (?,?,?,?,?)", rooms)
    conn.commit()

init_db()

# ==========================================================
# ماژول واتساپ (WhatsApp Integration)
# ==========================================================
def send_whatsapp(to, message):
    if "YOUR_" in CONFIG["ULTRAMSG_INSTANCE"]: return 
    url = f"https://api.ultramsg.com/{CONFIG['ULTRAMSG_INSTANCE']}/messages/chat"
    payload = {"token": CONFIG["ULTRAMSG_TOKEN"], "to": to, "body": message}
    try: requests.post(url, data=payload)
    except: print("WhatsApp Error")

# ==========================================================
# حسابداری خودکار بر اساس تاریخ ورود و خروج
# ==========================================================
def run_daily_accounting():
    conn = get_db()
    today = date.today()
    # فقط مسافران فعال را شارژ کن
    guests = conn.execute("SELECT * FROM bookings WHERE status = 'ACTIVE'").fetchall()
    
    for g in guests:
        last = datetime.strptime(g['last_charge'], '%Y-%m-%d').date()
        out_date = datetime.strptime(g['checkout'], '%Y-%m-%d').date()
        
        # تا زمانی که تاریخ امروز از تاریخ خروج بیشتر نشده شارژ کن
        target_date = min(today, out_date)
        days_to_charge = (target_date - last).days
        
        if days_to_charge > 0:
            for i in range(1, days_to_charge + 1):
                charge_day = last + timedelta(days=i)
                conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'DEBIT', 'STAY', ?, ?, ?)", 
                             (g['id'], g['rate'], str(charge_day), f"هزینه اقامت شب {charge_day}"))
            
            conn.execute("UPDATE bookings SET last_charge = ? WHERE id = ?", (str(target_date), g['id']))
            conn.commit()
            
            # ارسال پیامک بدهی به واتساپ مسافر در صورت وجود بدهی
            check_and_notify_debt(g)

def check_and_notify_debt(guest):
    conn = get_db()
    deb = conn.execute("SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='DEBIT'", (guest['id'],)).fetchone()[0] or 0
    cre = conn.execute("SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='CREDIT'", (guest['id'],)).fetchone()[0] or 0
    bal = deb - cre
    if bal > 0 and guest['phone']:
        msg = f"مهمان گرامی {guest['name']}\nمبلغ بدهی شما تا امروز {bal:,} تومان است.\n{CONFIG['HOSTEL_NAME']}"
        send_whatsapp(guest['phone'], msg)

# ==========================================================
# رابط کاربری (UI)
# ==========================================================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        body { font-family: tahoma; background: #f4f6f9; }
        .bed { width: 70px; height: 70px; border-radius: 8px; border: 1px solid #ddd; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; margin: 4px; background: white; font-size: 10px; }
        .occupied { background: #0d6efd; color: white; border: none; }
        .pending { background: #ffc107; color: black; border: none; animation: blink 1.5s infinite; }
        @keyframes blink { 0% {opacity:1} 50% {opacity:0.5} 100% {opacity:1} }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark p-3 shadow">
        <div class="container-fluid">
            <span class="navbar-brand">{{ config.HOSTEL_NAME }} | پنل مدیریت حرفه‌ای</span>
            <div class="d-flex gap-2">
                <button class="btn btn-warning btn-sm" onclick="new bootstrap.Modal(document.getElementById('expM')).show()">ثبت هزینه</button>
                <button class="btn btn-danger btn-sm" onclick="location.href='/action/reset'">ریست کل دیتابیس</button>
                <a href="/logout" class="btn btn-outline-light btn-sm">خروج</a>
            </div>
        </div>
    </nav>

    <div class="container-fluid py-4">
        <div class="row g-3 mb-4">
            <div class="col-md-4"><div class="card p-3 text-center">صندوق نقد: <h3 class="text-success">{{ "{:,}".format(s.cash) }}</h3></div></div>
            <div class="col-md-4"><div class="card p-3 text-center">مطالبات از بازار: <h3 class="text-primary">{{ "{:,}".format(s.debt) }}</h3></div></div>
            <div class="col-md-4"><div class="card p-3 text-center">هزینه‌های کل: <h3 class="text-danger">{{ "{:,}".format(s.exp) }}</h3></div></div>
        </div>

        <div class="row">
            {% for f in [1, 2] %}
            <div class="col-md-6">
                <h5 class="mb-3">طبقه {{ "اول" if f==1 else "دوم" }}</h5>
                {% for r in rooms if r.floor == f %}
                <div class="card p-3 mb-3">
                    <div class="d-flex justify-content-between mb-2 small"><b>{{ r.name }}</b></div>
                    {% for b in r.beds %}
                        {% if b.status == 'empty' %}
                        <div class="bed" onclick="openCheckin({{ r.id }}, {{ b.num }}, {{ r.base_price }})">تخت {{ b.num }}<br>خالی</div>
                        {% elif b.status == 'PENDING' %}
                        <div class="bed pending" onclick="approveBooking({{ b.info.id }})">رزرو<br>{{ b.info.name[:8] }}</div>
                        {% else %}
                        <div class="bed occupied" onclick="openLedger({{ b.info.id }})">{{ b.info.name[:10] }}<br>{{ "{:,}".format(b.info.bal) }}</div>
                        {% endif %}
                    {% endfor %}
                </div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
    </div>

    <div class="modal fade" id="checkinModal" tabindex="-1"><div class="modal-dialog"><form action="/action/checkin" method="POST" class="modal-content p-4">
        <input type="hidden" name="rid" id="rid"><input type="hidden" name="bnum" id="bnum">
        <h5>پذیرش مسافر</h5>
        <input name="name" placeholder="نام و نام خانوادگی" class="form-control mb-2" required>
        <input name="phone" placeholder="واتساپ (مثال: 989120000000)" class="form-control mb-2" required>
        <div class="row g-2 mb-2">
            <div class="col-6"><label class="small">تاریخ ورود</label><input type="date" name="cin" class="form-control" value="{{ today }}"></div>
            <div class="col-6"><label class="small">تاریخ خروج</label><input type="date" name="cout" class="form-control" required></div>
        </div>
        <input name="rate" id="rate" type="number" class="form-control mb-2" placeholder="نرخ شبانه">
        <input name="pay" type="number" class="form-control mb-3" placeholder="بیعانه / پیش‌پرداخت">
        <button class="btn btn-primary w-100">ثبت قطعی و اسکان</button>
    </form></div></div>

    <div class="modal fade" id="ledgerModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content p-4" id="lBody"></div></div></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function openCheckin(rid, bnum, rate) {
            document.getElementById('rid').value=rid; document.getElementById('bnum').value=bnum; document.getElementById('rate').value=rate;
            new bootstrap.Modal(document.getElementById('checkinModal')).show();
        }
        async function openLedger(bid) {
            const r = await fetch('/api/guest/' + bid); const d = await r.json();
            let html = `<h4>${d.g.name}</h4><p>تلفن: ${d.g.phone} | خروج: ${d.g.checkout}</p><hr>
            <h6>مانده بدهی: <span class="text-danger">${d.bal.toLocaleString()} تومان</span></h6>
            <form action="/action/pay" method="POST" class="input-group my-3">
                <input type="hidden" name="bid" value="${d.g.id}"><input name="amount" type="number" class="form-control" placeholder="دریافت وجه...">
                <button class="btn btn-success">ثبت نقد</button>
            </form>
            <div class="d-flex gap-2">
                <a href="/action/checkout/${d.g.id}" class="btn btn-danger w-100">تصفیه و خروج نهایی</a>
            </div>`;
            document.getElementById('lBody').innerHTML = html;
            new bootstrap.Modal(document.getElementById('ledgerModal')).show();
        }
        function approveBooking(bid) { if(confirm("رزرو بوکینگ تایید و تخت اشغال شود؟")) location.href="/action/approve/"+bid; }
    </script>
</body>
</html>
"""

# ==========================================================
# مسیرهای سرور (Routes)
# ==========================================================
@app.route('/')
def index():
    if not session.get('logged_in'): return render_template_string(LOGIN_UI)
    run_daily_accounting() # آپدیت روزانه فاکتورها
    conn = get_db()
    
    # آمار مالی
    cash = conn.execute("SELECT SUM(amount) FROM journal WHERE type='CREDIT'").fetchone()[0] or 0
    exp = conn.execute("SELECT SUM(amount) FROM journal WHERE category='EXPENSE'").fetchone()[0] or 0
    
    rooms = [dict(r) for r in conn.execute("SELECT * FROM rooms").fetchall()]
    bookings = [dict(b) for b in conn.execute("SELECT * FROM bookings WHERE status IN ('ACTIVE', 'PENDING')").fetchall()]
    
    total_debt = 0
    for r in rooms:
        r['beds'] = []
        for i in range(1, r['capacity'] + 1):
            b_data = next((b for b in bookings if b['room_id']==r['id'] and b['bed_number']==i), None)
            if b_data:
                deb = conn.execute("SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='DEBIT'", (b_data['id'],)).fetchone()[0] or 0
                cre = conn.execute("SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='CREDIT'", (b_data['id'],)).fetchone()[0] or 0
                b_data['bal'] = deb - cre
                if b_data['bal'] > 0: total_debt += b_data['bal']
                r['beds'].append({'status': b_data['status'], 'info': b_data})
            else: r['beds'].append({'status': 'empty', 'num': i})
            
    return render_template_string(DASHBOARD_HTML, rooms=rooms, s={'cash':cash, 'exp':exp, 'debt':total_debt}, today=date.today(), config=CONFIG)

@app.route('/action/checkin', methods=['POST'])
def checkin():
    conn = get_db()
    cur = conn.execute("INSERT INTO bookings (room_id, bed_number, name, phone, checkin, checkout, last_charge, rate, status) VALUES (?,?,?,?,?,?,?,?,'ACTIVE')", 
                 (request.form['rid'], request.form['bnum'], request.form['name'], request.form['phone'], request.form['cin'], request.form['cout'], request.form['cin'], request.form['rate']))
    bid = cur.lastrowid
    if int(request.form.get('pay', 0)) > 0:
        conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'CREDIT', 'PAYMENT', ?, ?, 'بیعانه ورود')", (bid, request.form['pay'], str(date.today())))
    conn.commit()
    send_whatsapp(request.form['phone'], f"سلام {request.form['name']}\nپذیرش شما انجام شد.\nتاریخ خروج: {request.form['cout']}\nاقامت خوشی داشته باشید.")
    return redirect('/')

@app.route('/api/guest/<int:bid>')
def get_guest(bid):
    conn = get_db()
    g = dict(conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())
    l = [dict(t) for t in conn.execute("SELECT * FROM journal WHERE ref_id=? ORDER BY id DESC", (bid,)).fetchall()]
    deb = conn.execute("SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='DEBIT'", (bid,)).fetchone()[0] or 0
    cre = conn.execute("SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='CREDIT'", (bid,)).fetchone()[0] or 0
    return jsonify({'g': g, 'l': l, 'bal': deb - cre})

@app.route('/action/pay', methods=['POST'])
def pay():
    conn = get_db()
    conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'CREDIT', 'PAYMENT', ?, ?, 'دریافت وجه')", (request.form['bid'], request.form['amount'], str(date.today())))
    conn.commit(); return redirect('/')

@app.route('/action/checkout/<int:bid>')
def checkout(bid):
    conn = get_db(); conn.execute("UPDATE bookings SET status='FINISHED' WHERE id=?", (bid,)); conn.commit(); return redirect('/')

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

LOGIN_UI = """<body style="font-family:tahoma; background:#eee; display:flex; justify-content:center; align-items:center; height:100vh;"><form action="/login" method="POST" style="background:#fff; padding:40px; border-radius:10px;"><h4>ورود به پنل هاستل</h4><br><input name="u" placeholder="نام کاربری"><input name="p" type="password" placeholder="رمز عبور"><br><br><button class="btn btn-primary w-100">ورود</button></form></body>"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
