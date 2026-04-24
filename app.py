from flask import Flask, request, redirect, session, render_template_string, jsonify
import sqlite3
from datetime import datetime, date, timedelta
import os

app = Flask(__name__)
app.secret_key = "fin-tech-hostel-key-99"
DB = "hostel_erp.db"

# ================= DATABASE ARCHITECTURE =================
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    
    # 1. Rooms & Beds Structure
    c.execute("""CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY, 
        name TEXT, 
        capacity INTEGER, 
        base_price INTEGER, 
        room_type TEXT)""")

    # 2. Bookings (The Financial Ledger Header)
    c.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY, 
        room_id INTEGER, 
        bed_number INTEGER, 
        customer_name TEXT, 
        whatsapp TEXT,
        checkin_date TEXT, 
        checkout_date TEXT, 
        daily_rate INTEGER,
        is_active INTEGER DEFAULT 1,
        last_charge_date TEXT)""")

    # 3. Transactions (The Accounting Heart)
    # Types: 'charge' (بدهی روزانه), 'payment' (پرداخت مشتری), 'discount' (تخفیف), 'refund' (برگشت)
    c.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY, 
        booking_id INTEGER, 
        type TEXT, 
        amount INTEGER, 
        date TEXT, 
        description TEXT,
        FOREIGN KEY(booking_id) REFERENCES bookings(id))""")

    # 4. General Expenses
    c.execute("""CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY, 
        title TEXT, 
        amount INTEGER, 
        category TEXT, 
        date TEXT)""")

    # Initial Data if empty
    if c.execute("SELECT count(*) FROM rooms").fetchone()[0] == 0:
        rooms_data = [
            ("اتاق ۱۰۱ (VIP)", 1, 180000, "خصوصی"),
            ("اتاق ۱۰۲ (۴ تخته)", 4, 35000, "عمومی"),
            ("اتاق ۱۰۳ (۸ تخته)", 8, 25000, "اقتصادی")
        ]
        c.executemany("INSERT INTO rooms (name, capacity, base_price, room_type) VALUES (?,?,?,?)", rooms_data)
    
    conn.commit()
    conn.close()

init_db()

# ================= ACCOUNTING ENGINE =================

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def sync_daily_charges():
    """ 
    این تابع قلب حسابداری سیستم است. 
    بررسی می‌کند که آیا برای روزهای سپری شده، شارژ روزانه ثبت شده یا خیر.
    """
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
    db.close()

def get_booking_balance(booking_id):
    db = get_db()
    # بدهی‌ها (Charge) مثبت و پرداخت‌ها (Payment) منفی در نظر گرفته می‌شوند تا بالانس نهایی به دست آید
    charges = db.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='charge'", (booking_id,)).fetchone()[0] or 0
    payments = db.execute("SELECT SUM(amount) FROM transactions WHERE booking_id=? AND type='payment'", (booking_id,)).fetchone()[0] or 0
    db.close()
    return charges - payments # Positive = Debt, Negative = Credit
# ================= FINANCE & OPERATIONS ROUTES =================

@app.route("/dashboard")
def dashboard():
    if not session.get("login"): return redirect("/")
    sync_daily_charges() # همگام‌سازی خودکار بدهی‌ها در هر بار بازدید
    
    db = get_db()
    rooms = [dict(r) for r in db.execute("SELECT * FROM rooms").fetchall()]
    all_bookings = [dict(b) for b in db.execute("SELECT * FROM bookings WHERE is_active=1").fetchall()]
    
    # غنی‌سازی داده‌های اتاق با وضعیت مالی تخت‌ها
    for r in rooms:
        r['beds'] = []
        for i in range(1, r['capacity'] + 1):
            booking = next((b for b in all_bookings if b['room_id'] == r['id'] and b['bed_number'] == i), None)
            if booking:
                balance = get_booking_balance(booking['id'])
                booking_data = dict(booking)
                booking_data['balance'] = balance
                r['beds'].append({'status': 'occupied', 'data': booking_data})
            else:
                r['beds'].append({'status': 'empty', 'bed_num': i})
    
    # آمار داشبورد مالی
    stats = {
        "daily_revenue": db.execute("SELECT SUM(amount) FROM transactions WHERE type='payment' AND date=?", (str(date.today()),)).fetchone()[0] or 0,
        "total_debt": sum(get_booking_balance(b['id']) for b in all_bookings if get_booking_balance(b['id']) > 0),
        "active_guests": len(all_bookings),
        "monthly_expenses": db.execute("SELECT SUM(amount) FROM expenses WHERE strftime('%m', date) = strftime('%m', 'now')").fetchone()[0] or 0
    }
    
    db.close()
    return render_template_string(dashboard_html, rooms=rooms, stats=stats, today=str(date.today()))

@app.route("/api/booking/<int:bid>")
def get_booking_details(bid):
    """دریافت ریز تراکنش‌های یک رزرو برای نمایش در پروفایل مالی"""
    db = get_db()
    booking = dict(db.execute("SELECT * FROM bookings WHERE id=?", (bid,)).fetchone())
    transactions = [dict(t) for t in db.execute("SELECT * FROM transactions WHERE booking_id=? ORDER BY date DESC", (bid,)).fetchall()]
    balance = get_booking_balance(bid)
    db.close()
    return jsonify({'booking': booking, 'ledger': transactions, 'balance': balance})

@app.route("/action/checkin", methods=["POST"])
def action_checkin():
    db = get_db()
    # ثبت رزرو جدید
    c_date = str(date.today())
    cursor = db.execute("""INSERT INTO bookings 
        (room_id, bed_number, customer_name, whatsapp, checkin_date, last_charge_date, daily_rate) 
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (request.form['room_id'], request.form['bed_num'], request.form['name'], 
         request.form['whatsapp'], c_date, c_date, request.form['rate']))
    
    booking_id = cursor.lastrowid
    
    # ثبت اولین پرداخت (در صورت وجود)
    payment = int(request.form.get('payment', 0))
    if payment > 0:
        db.execute("""INSERT INTO transactions (booking_id, type, amount, date, description) 
                   VALUES (?, 'payment', ?, ?, ?)""", 
                   (booking_id, payment, c_date, "پیش‌پرداخت هنگام پذیرش"))
    
    db.commit()
    db.close()
    return redirect("/dashboard")

@app.route("/action/add-payment", methods=["POST"])
def add_payment():
    db = get_db()
    bid = request.form['booking_id']
    amount = int(request.form['amount'])
    db.execute("""INSERT INTO transactions (booking_id, type, amount, date, description) 
               VALUES (?, 'payment', ?, ?, ?)""", 
               (bid, amount, str(date.today()), request.form.get('desc', 'دریافت نقدی')))
    db.commit()
    db.close()
    return redirect("/dashboard")

@app.route("/action/checkout/<int:bid>")
def action_checkout(bid):
    db = get_db()
    # غیرفعال کردن رزرو (بایگانی مالی)
    db.execute("UPDATE bookings SET is_active=0, checkout_date=? WHERE id=?", (str(date.today()), bid))
    db.commit()
    db.close()
    return redirect("/dashboard")
    # ================= ANALYTICS & REPORTING ENGINE =================

@app.route("/reports/ledger/<int:bid>")
def customer_ledger_report(bid):
    """گزارش تفصیلی تراکنش‌های یک مشتری (مناسب برای چاپ فاکتور)"""
    if not session.get("login"): return redirect("/")
    db = get_db()
    booking = dict(db.execute("""
        SELECT b.*, r.name as room_name 
        FROM bookings b JOIN rooms r ON b.room_id = r.id 
        WHERE b.id = ?""", (bid,)).fetchone())
    
    transactions = [dict(t) for t in db.execute("""
        SELECT * FROM transactions 
        WHERE booking_id = ? ORDER BY date ASC""", (bid,)).fetchall()]
    
    total_charges = sum(t['amount'] for t in transactions if t['type'] == 'charge')
    total_payments = sum(t['amount'] for t in transactions if t['type'] == 'payment')
    balance = total_charges - total_payments
    
    db.close()
    return render_template_string(ledger_print_html, 
                                 b=booking, tx=transactions, 
                                 total_c=total_charges, total_p=total_payments, 
                                 balance=balance, now=datetime.now().strftime("%Y-%m-%d %H:%M"))

@app.route("/api/analytics/revenue")
def api_revenue_chart():
    """تأمین داده برای نمودار درآمد ۷ روز اخیر"""
    db = get_db()
    chart_data = []
    for i in range(6, -1, -1):
        day = str(date.today() - timedelta(days=i))
        revenue = db.execute("SELECT SUM(amount) FROM transactions WHERE type='payment' AND date=?", (day,)).fetchone()[0] or 0
        chart_data.append({"date": day, "value": revenue})
    db.close()
    return jsonify(chart_data)

@app.route("/reports/general")
def general_financial_report():
    """گزارش سود و زیان کلی"""
    db = get_db()
    # تفکیک درآمد بر اساس اتاق‌ها
    room_performance = db.execute("""
        SELECT r.name, SUM(t.amount) as revenue
        FROM transactions t
        JOIN bookings b ON t.booking_id = b.id
        JOIN rooms r ON b.room_id = r.id
        WHERE t.type = 'payment'
        GROUP BY r.id
    """).fetchall()
    
    # تفکیک هزینه‌ها بر اساس دسته‌بندی
    expense_cats = db.execute("SELECT category, SUM(amount) as total FROM expenses GROUP BY category").fetchall()
    db.close()
    return render_template_string(report_page_html, rooms=room_performance, expenses=expense_cats)

# ================= AUTH & SYSTEM =================

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["u"] == "admin" and request.form["p"] == "admin123":
            session["login"] = True
            return redirect("/dashboard")
    return '''<body style="direction:rtl; font-family:tahoma; background:#f0f2f5; display:flex; justify-content:center; align-items:center; height:100vh;">
        <form method="POST" style="background:white; padding:40px; border-radius:20px; box-shadow:0 10px 25px rgba(0,0,0,0.1);">
            <h2 style="margin-bottom:20px;">مدیریت هوشمند هاستل</h2>
            <input name="u" placeholder="نام کاربری" style="display:block; width:100%; padding:10px; margin-bottom:10px; border:1px solid #ddd; border-radius:8px;">
            <input name="p" type="password" placeholder="رمز عبور" style="display:block; width:100%; padding:10px; margin-bottom:20px; border:1px solid #ddd; border-radius:8px;">
            <button style="width:100%; padding:12px; background:#4361ee; color:white; border:none; border-radius:8px; cursor:pointer;">ورود به سیستم حسابداری</button>
        </form></body>'''

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")
    dashboard_html = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>Hostel ERP | سیستم جامع مالی و عملیاتی</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;500;800&display=swap');
        :root {
            --stripe-blue: #635bff; --bg-soft: #f6f9fc;
            --glass: rgba(255, 255, 255, 0.8);
        }
        body { background: var(--bg-soft); font-family: 'Vazirmatn', sans-serif; color: #424770; overflow-x: hidden; }
        
        /* Sidebar Glassmorphism */
        .sidebar {
            width: 280px; height: 100vh; position: fixed; right: 0; top: 0;
            background: white; border-left: 1px solid #e6ebf1; padding: 30px 20px;
            z-index: 1000;
        }
        .main-content { margin-right: 280px; padding: 40px; }

        /* Premium Cards */
        .stat-card {
            background: white; border-radius: 16px; padding: 24px;
            box-shadow: 0 7px 14px rgba(50,50,93,.1), 0 3px 6px rgba(0,0,0,.08);
            border: none; transition: transform 0.2s;
        }
        .stat-card:hover { transform: translateY(-5px); }

        /* Bed Grid System */
        .room-section { background: white; border-radius: 20px; padding: 30px; margin-bottom: 30px; border: 1px solid #e6ebf1; }
        .bed-unit {
            width: 140px; height: 160px; border-radius: 18px; 
            border: 2px dashed #dce2e9; display: flex; flex-direction: column;
            align-items: center; justify-content: center; cursor: pointer;
            transition: all 0.3s cubic-bezier(0.165, 0.84, 0.44, 1);
            background: #fff; position: relative;
        }
        .bed-unit.occupied { border: 2px solid var(--stripe-blue); background: #fbfbff; box-shadow: 0 4px 6px rgba(50,50,93,.11); }
        .bed-unit .balance-badge {
            position: absolute; bottom: 12px; font-size: 11px; padding: 2px 8px; border-radius: 10px;
        }
        .debtor { background: #fee2e2; color: #ef4444; }
        .settled { background: #f3f4f6; color: #6b7280; }
        .credit { background: #dcfce7; color: #22c55e; }

        /* Ledger Table in Modal */
        .ledger-row { font-size: 13px; border-bottom: 1px solid #f6f9fc; padding: 10px 0; }
        .type-charge { color: #f59e0b; }
        .type-payment { color: #10b981; }

        /* Chart Container */
        .chart-container { background: white; border-radius: 16px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,.05); }
    </style>
</head>
<body>

    <aside class="sidebar">
        <div class="mb-5 text-center">
            <h3 class="fw-bold text-primary">HOSTEL<span class="text-dark">ERP</span></h3>
            <small class="text-muted">Accountant Edition v3.0</small>
        </div>
        <nav class="nav flex-column">
            <a href="/dashboard" class="nav-link text-dark py-3 fw-medium"><i class="fas fa-th-large me-2"></i> داشبورد مالی</a>
            <a href="/reports/general" class="nav-link text-muted py-3"><i class="fas fa-chart-line me-2"></i> گزارشات کل</a>
            <a href="/logout" class="nav-link text-danger mt-5"><i class="fas fa-sign-out-alt me-2"></i> خروج</a>
        </nav>
    </aside>

    <main class="main-content">
        <div class="row g-4 mb-5">
            <div class="col-md-3">
                <div class="stat-card">
                    <small class="text-muted">وصولی امروز</small>
                    <h3 class="fw-bold mb-0 text-success">{{ "{:,.0f}".format(stats.daily_revenue) }} <small class="fs-6">تومان</small></h3>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <small class="text-muted">کل مطالبات (بدهکاران)</small>
                    <h3 class="fw-bold mb-0 text-danger">{{ "{:,.0f}".format(stats.total_debt) }}</h3>
                </div>
            </div>
            <div class="col-md-3">
                <div class="stat-card">
                    <small class="text-muted">مهمانان مقیم</small>
                    <h3 class="fw-bold mb-0">{{ stats.active_guests }} <small class="fs-6">نفر</small></h3>
                </div>
            </div>
            <div class="col-md-3">
                <div class="chart-container py-2 text-center">
                    <canvas id="miniChart" height="80"></canvas>
                </div>
            </div>
        </div>

        <h4 class="fw-bold mb-4">نقشه عملیاتی هاستل</h4>
        {% for room in rooms %}
        <div class="room-section">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <h5 class="fw-bold m-0">{{ room.name }} <span class="badge bg-light text-dark fs-6 ms-2">{{ room.room_type }}</span></h5>
                <span class="text-muted small">نرخ پایه: {{ room.base_price }}</span>
            </div>
            <div class="d-flex flex-wrap gap-4">
                {% for bed in room.beds %}
                    {% if bed.status == 'empty' %}
                        <div class="bed-unit" onclick="openCheckin({{ room.id }}, {{ bed.bed_num }}, {{ room.base_price }})">
                            <i class="fas fa-plus text-muted mb-2"></i>
                            <span class="small fw-bold text-muted">تخت {{ bed.bed_num }}</span>
                        </div>
                    {% else %}
                        <div class="bed-unit occupied" onclick="openLedger({{ bed.data.id }})">
                            <i class="fas fa-user-check text-primary mb-2 fs-4"></i>
                            <span class="small fw-bold">{{ bed.data.customer_name[:12] }}</span>
                            <span class="balance-badge {% if bed.data.balance > 0 %}debtor{% elif bed.data.balance < 0 %}credit{% else %}settled{% endif %}">
                                {{ bed.data.balance|abs if bed.data.balance != 0 else 'تسویه' }}
                            </span>
                        </div>
                    {% endif %}
                {% endfor %}
            </div>
        </div>
        {% endfor %}
    </main>

    <div class="modal fade" id="ledgerModal" tabindex="-1">
        <div class="modal-dialog modal-lg modal-dialog-centered">
            <div class="modal-content border-0 shadow-lg" style="border-radius:24px;">
                <div class="modal-body p-4">
                    <div id="ledgerContent">
                        </div>
                </div>
            </div>
        </div>
    </div>

    <div class="modal fade" id="checkinModal" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content border-0 shadow" style="border-radius:24px;">
                <form action="/action/checkin" method="POST" class="p-4">
                    <input type="hidden" name="room_id" id="m_room_id">
                    <input type="hidden" name="bed_num" id="m_bed_num">
                    <h5 class="fw-bold mb-4">پذیرش و ایجاد پرونده مالی</h5>
                    <input type="text" name="name" class="form-control mb-3" placeholder="نام و نام خانوادگی" required>
                    <input type="text" name="whatsapp" class="form-control mb-3" placeholder="شماره تماس (بدون صفر)">
                    <div class="row g-2">
                        <div class="col-6"><input type="number" name="rate" id="m_rate" class="form-control" placeholder="نرخ شبانه"></div>
                        <div class="col-6"><input type="number" name="payment" class="form-control" placeholder="پیش‌پرداخت"></div>
                    </div>
                    <button type="submit" class="btn btn-primary w-100 mt-4 py-3 rounded-4 fw-bold">تایید و ثبت در دفتر کل</button>
                </form>
            </div>
        </div>
    </div>

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
                <div class="d-flex justify-content-between mb-4">
                    <div>
                        <h4 class="fw-bold mb-1">${b.customer_name}</h4>
                        <span class="text-muted">ورود: ${b.checkin_date} | نرخ: ${b.daily_rate}</span>
                    </div>
                    <div class="text-end">
                        <span class="badge ${data.balance > 0 ? 'bg-danger' : 'bg-success'} fs-5">مانده: ${Math.abs(data.balance)}</span>
                    </div>
                </div>
                <div class="mb-4" style="max-height:300px; overflow-y:auto">
                    ${data.ledger.map(t => `
                        <div class="ledger-row d-flex justify-content-between">
                            <span>${t.description} <small class="text-muted d-block">${t.date}</small></span>
                            <span class="${t.type == 'charge' ? 'type-charge' : 'type-payment'} fw-bold">
                                ${t.type == 'charge' ? '+' : '-'}${t.amount}
                            </span>
                        </div>
                    `).join('')}
                </div>
                <form action="/action/add-payment" method="POST" class="row g-2">
                    <input type="hidden" name="booking_id" value="${b.id}">
                    <div class="col-8"><input type="number" name="amount" class="form-control" placeholder="مبلغ دریافتی جدید"></div>
                    <div class="col-4"><button class="btn btn-success w-100">ثبت قبض</button></div>
                </form>
                <div class="mt-4 pt-3 border-top d-flex gap-2">
                    <a href="/reports/ledger/${b.id}" class="btn btn-light flex-grow-1"><i class="fas fa-print me-1"></i> چاپ فاکتور</a>
                    <a href="/action/checkout/${b.id}" class="btn btn-outline-danger" onclick="return confirm('آیا تسویه نهایی انجام شده است؟')">تسویه و خروج</a>
                </div>
            `;
            document.getElementById('ledgerContent').innerHTML = html;
            new bootstrap.Modal(document.getElementById('ledgerModal')).show();
        }

        // Mini Analytics
        const ctx = document.getElementById('miniChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['6d', '5d', '4d', '3d', '2d', '1d', 'Now'],
                datasets: [{ 
                    label: 'درآمد', data: [12, 19, 3, 5, 2, 3, 15], 
                    borderColor: '#635bff', tension: 0.4, borderWidth: 2, pointRadius: 0 
                }]
            },
            options: { plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { display: false } } }
        });
    </script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# HTML لازم برای گزارشات چاپی و تحلیل کل (خلاصه شده برای پارت نهایی)
ledger_print_html = ""
report_page_html = ""

if __name__ == "__main__":
    app.run(debug=True, port=5000)
