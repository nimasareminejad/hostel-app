import os, sqlite3, requests
from datetime import datetime, date, timedelta
from flask import Flask, request, redirect, session, jsonify, render_template_string
# برای اجرای این کد باید کتابخانه icalendar را نصب کنید: pip install icalendar
try:
    from icalendar import Calendar
except ImportError:
    Calendar = None

# ==========================================================
# بخش تنظیمات - اطلاعات خود را اینجا وارد کنید
# ==========================================================
CONFIG = {
    "HOSTEL_NAME": "هاستل مرکزی",
    "ULTRAMSG_INSTANCE": "YOUR_INSTANCE_ID", 
    "ULTRAMSG_TOKEN": "YOUR_TOKEN",         
    "MANAGER_PHONE": "989120000000",        
    "BOOKING_ICAL_URLS": {
        "101": "https://ical.booking.com/v1/export?t=your-link-1",
        "102": "https://ical.booking.com/v1/export?t=your-link-2"
    }
}

app = Flask(__name__)
app.secret_key = "hostel_full_pms_final_2026"
DB_PATH = "hostel_v3.db"

# ==========================================================
# مدیریت دیتابیس
# ==========================================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY, floor INT, name TEXT, capacity INT, base_price INT, type TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY, room_id INT, bed_number INT, name TEXT, phone TEXT, passport TEXT, checkin TEXT, checkout TEXT, last_charge TEXT, rate INT, status TEXT DEFAULT 'ACTIVE', source TEXT DEFAULT 'MANUAL')")
        conn.execute("CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, ref_id INT, type TEXT, category TEXT, amount INT, date TEXT, desc TEXT)")
        
        if conn.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
            rooms = [(1,'101',1,500000,'VIP'), (1,'102',3,200000,'Dorm'), (1,'103',6,150000,'Dorm'), (2,'201',4,180000,'Dorm')]
            conn.executemany("INSERT INTO rooms (floor, name, capacity, base_price, type) VALUES (?,?,?,?,?)", rooms)
    conn.commit()

init_db()

# ==========================================================
# ماژول همگام‌سازی با بوکینگ (Booking.com Sync)
# ==========================================================
def sync_with_booking():
    if not Calendar: return
    conn = get_db()
    for room_name, url in CONFIG["BOOKING_ICAL_URLS"].items():
        try:
            response = requests.get(url, timeout=10)
            cal = Calendar.from_ical(response.content)
            room_id = conn.execute("SELECT id FROM rooms WHERE name LIKE ?", (f"%{room_name}%",)).fetchone()
            if not room_id: continue
            
            for component in cal.walk():
                if component.name == "VEVENT":
                    start = component.get('dtstart').dt.strftime('%Y-%m-%d')
                    end = component.get('dtend').dt.strftime('%Y-%m-%d')
                    summary = str(component.get('summary'))
                    
                    # چک کردن تکراری نبودن رزرو
                    exists = conn.execute("SELECT id FROM bookings WHERE name=? AND checkin=?", (summary, start)).fetchone()
                    if not exists:
                        # پیدا کردن اولین تخت خالی در آن اتاق
                        conn.execute("INSERT INTO bookings (room_id, bed_number, name, checkin, checkout, last_charge, rate, status, source) VALUES (?, 1, ?, ?, ?, ?, 0, 'PENDING', 'BOOKING')",
                                     (room_id['id'], summary, start, end, start))
                        send_whatsapp(CONFIG["MANAGER_PHONE"], f"🔔 رزرو جدید از بوکینگ:\nاتاق: {room_name}\nمهمان: {summary}\nورود: {start}")
            conn.commit()
        except Exception as e:
            print(f"Sync Error for {room_name}: {e}")

# ==========================================================
# سرویس واتساپ
# ==========================================================
def send_whatsapp(to, message):
    if "YOUR_" in CONFIG["ULTRAMSG_INSTANCE"]: return 
    url = f"https://api.ultramsg.com/{CONFIG['ULTRAMSG_INSTANCE']}/messages/chat"
    payload = {"token": CONFIG["ULTRAMSG_TOKEN"], "to": to, "body": message}
    try: requests.post(url, data=payload)
    except: pass

# ==========================================================
# حسابداری هوشمند
# ==========================================================
def run_accounting():
    conn = get_db()
    today = date.today()
    guests = conn.execute("SELECT * FROM bookings WHERE status = 'ACTIVE'").fetchall()
    for g in guests:
        last = datetime.strptime(g['last_charge'], '%Y-%m-%d').date()
        out_date = datetime.strptime(g['checkout'], '%Y-%m-%d').date()
        target = min(today, out_date)
        days = (target - last).days
        if days > 0:
            for i in range(1, days + 1):
                day = last + timedelta(days=i)
                conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'DEBIT', 'STAY', ?, ?, ?)", (g['id'], g['rate'], str(day), f"اقامت شب {day}"))
            conn.execute("UPDATE bookings SET last_charge = ? WHERE id = ?", (str(target), g['id']))
    conn.commit()

# ==========================================================
# مسیرهای اصلی (Routes)
# ==========================================================
@app.route('/')
def index():
    if not session.get('logged_in'): return render_template_string(LOGIN_UI)
    sync_with_booking() # همگام‌سازی خودکار با بوکینگ
    run_accounting()    # محاسبه مالیات و اجاره روزانه
    
    conn = get_db()
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
            
    return render_template_string(UI, rooms=rooms, s={'cash':cash, 'exp':exp, 'debt':total_debt}, today=date.today())

@app.route('/action/checkin', methods=['POST'])
def checkin():
    conn = get_db()
    cur = conn.execute("INSERT INTO bookings (room_id, bed_number, name, phone, checkin, checkout, last_charge, rate, status) VALUES (?,?,?,?,?,?,?,?,'ACTIVE')", 
                 (request.form['rid'], request.form['bnum'], request.form['name'], request.form['phone'], request.form['cin'], request.form['cout'], request.form['cin'], request.form['rate']))
    bid = cur.lastrowid
    if int(request.form.get('pay', 0)) > 0:
        conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'CREDIT', 'PAYMENT', ?, ?, 'بیعانه')", (bid, request.form['pay'], str(date.today())))
    conn.commit()
    send_whatsapp(request.form['phone'], f"سلام {request.form['name']} عزیز، خوش آمدید. فاکتور شما فعال شد.")
    return redirect('/')

@app.route('/action/approve/<int:bid>')
def approve(bid):
    conn = get_db()
    # در اینجا نرخ اتاق را برای رزرو بوکینگ ست کنید (مثلاً ۲۰۰ هزار تومان)
    conn.execute("UPDATE bookings SET status='ACTIVE', rate=200000 WHERE id=?", (bid,))
    conn.commit()
    return redirect('/')

@app.route('/api/guest/<int:bid>')
def api_guest(bid):
    conn = get_db()
    g = dict(conn.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())
    deb = conn.execute("SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='DEBIT'", (bid,)).fetchone()[0] or 0
    cre = conn.execute("SELECT SUM(amount) FROM journal WHERE ref_id=? AND type='CREDIT'", (bid,)).fetchone()[0] or 0
    return jsonify({'g': g, 'bal': deb - cre})

@app.route('/action/pay', methods=['POST'])
def pay():
    conn = get_db()
    conn.execute("INSERT INTO journal (ref_id, type, category, amount, date, desc) VALUES (?, 'CREDIT', 'PAYMENT', ?, ?, 'پرداخت نقد')", (request.form['bid'], request.form['amount'], str(date.today())))
    conn.commit(); return redirect('/')

@app.route('/action/checkout/<int:bid>')
def checkout(bid):
    conn = get_db(); conn.execute("UPDATE bookings SET status='FINISHED' WHERE id=?", (bid,)); conn.commit(); return redirect('/')

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('u') == 'admin' and request.form.get('p') == 'admin123': session['logged_in'] = True
    return redirect('/')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

@app.route('/action/reset')
def reset():
    if os.path.exists(DB_PATH): os.remove(DB_PATH)
    init_db(); return redirect('/')

# --- رابط کاربری (UI) ---
UI = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <style>
        body { font-family: tahoma; background: #f8f9fa; }
        .bed { width: 65px; height: 65px; border-radius: 10px; border: 1px solid #ccc; display: inline-flex; align-items: center; justify-content: center; cursor: pointer; margin: 5px; background: white; font-size: 10px; vertical-align: top; }
        .occupied { background: #0d6efd; color: white; }
        .pending { background: #ffc107; animation: pulse 2s infinite; }
        @keyframes pulse { 0% {opacity: 1} 50% {opacity: 0.5} 100% {opacity: 1} }
    </style>
</head>
<body>
    <nav class="navbar navbar-dark bg-dark p-3">
        <div class="container-fluid">
            <span class="navbar-brand">مدیریت هاستل حرفه‌ای</span>
            <div class="d-flex gap-2">
                <button class="btn btn-danger btn-sm" onclick="location.href='/action/reset'">ریست کل سیستم</button>
                <a href="/logout" class="btn btn-secondary btn-sm">خروج</a>
            </div>
        </div>
    </nav>
    <div class="container py-4">
        <div class="row g-3 mb-4 text-center">
            <div class="col-md-4"><div class="card p-3">نقدینگی: <h4>{{ "{:,}".format(s.cash) }}</h4></div></div>
            <div class="col-md-4"><div class="card p-3">بدهی مهمانان: <h4>{{ "{:,}".format(s.debt) }}</h4></div></div>
            <div class="col-md-4"><div class="card p-3">هزینه‌ها: <h4>{{ "{:,}".format(s.exp) }}</h4></div></div>
        </div>
        <div class="row">
            {% for f in [1, 2] %}
            <div class="col-md-6">
                <h5>طبقه {{ "اول" if f==1 else "دوم" }}</h5>
                {% for r in rooms if r.floor == f %}
                <div class="card p-3 mb-3">
                    <b>{{ r.name }}</b>
                    <div class="mt-2">
                        {% for b in r.beds %}
                            {% if b.status == 'empty' %}
                            <div class="bed" onclick="openCheckin({{ r.id }}, {{ b.num }}, {{ r.base_price }})">تخت {{ b.num }}</div>
                            {% elif b.status == 'PENDING' %}
                            <div class="bed pending" onclick="approveB({{ b.info.id }})">رزرو موقت</div>
                            {% else %}
                            <div class="bed occupied" onclick="openL({{ b.info.id }})">{{ b.info.name[:10] }}</div>
                            {% endif %}
                        {% endfor %}
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
    </div>

    <div class="modal fade" id="checkinM" tabindex="-1"><div class="modal-dialog"><form action="/action/checkin" method="POST" class="modal-content p-4">
        <input type="hidden" name="rid" id="rid"><input type="hidden" name="bnum" id="bnum">
        <input name="name" placeholder="نام مهمان" class="form-control mb-2" required>
        <input name="phone" placeholder="شماره واتساپ" class="form-control mb-2">
        <div class="row g-2 mb-2">
            <div class="col-6"><label>ورود</label><input type="date" name="cin" class="form-control" value="{{ today }}"></div>
            <div class="col-6"><label>خروج</label><input type="date" name="cout" class="form-control" required></div>
        </div>
        <input name="rate" id="rate" type="number" class="form-control mb-2" placeholder="نرخ شبانه">
        <input name="pay" type="number" class="form-control mb-3" placeholder="بیعانه">
        <button class="btn btn-primary w-100">ثبت</button>
    </form></div></div>

    <div class="modal fade" id="ledgerM" tabindex="-1"><div class="modal-dialog"><div class="modal-content p-4" id="lBody"></div></div></div>

    <script>
        function openCheckin(rid, bnum, rate) {
            document.getElementById('rid').value=rid; document.getElementById('bnum').value=bnum; document.getElementById('rate').value=rate;
            new bootstrap.Modal(document.getElementById('checkinM')).show();
        }
        async function openL(bid) {
            const r = await fetch('/api/guest/' + bid); const d = await r.json();
            document.getElementById('lBody').innerHTML = `
                <h5>${d.g.name}</h5><p>بدهی: ${d.bal.toLocaleString()}</p>
                <form action="/action/pay" method="POST" class="input-group mb-3">
                    <input type="hidden" name="bid" value="${d.g.id}"><input name="amount" type="number" class="form-control"><button class="btn btn-success">دریافت نقد</button>
                </form>
                <a href="/action/checkout/${d.g.id}" class="btn btn-danger w-100">تصفیه نهایی</a>`;
            new bootstrap.Modal(document.getElementById('ledgerM')).show();
        }
        function approveB(bid) { if(confirm("رزرو بوکینگ تایید شود؟")) location.href="/action/approve/"+bid; }
    </script>
</body>
</html>
"""

LOGIN_UI = """<body style="font-family:tahoma; background:#eee; display:flex; justify-content:center; align-items:center; height:100vh;"><form action="/login" method="POST" style="background:#fff; padding:40px; border-radius:10px;"><h4>ورود</h4><input name="u" placeholder="user"><input name="p" type="password" placeholder="pass"><button>ورود</button></form></body>"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
