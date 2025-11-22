# main.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
import os

# local database helper (uses database.py structure)
DB_PATH = "salon.db"

def get_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db_if_needed():
    # import and run the DB initializer if salon.db doesn't exist or tables missing
    if not os.path.exists(DB_PATH):
        # database.py content expected in same folder; call it
        import database
        database.init_db()
    else:
        # ensure admin exists and tables exist (safe to call init_db)
        try:
            import database
            database.init_db()
        except Exception:
            pass

# Initialize DB at startup
init_db_if_needed()

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # keep your secret key

# ---------------------------
# Helper functions
# ---------------------------

def get_user_by_username(username):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()
    return user

def create_user(username, password, phone=None, gender=None):
    hashed = generate_password_hash(password)
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, 'customer')",
            (username, hashed)
        )
        conn.commit()
        user_id = cur.lastrowid
        # optional: store phone & gender in appointments when booking; users table keeps only username/password/role
    except sqlite3.IntegrityError:
        conn.close()
        return None
    conn.close()
    return user_id

def check_credentials(username, password):
    user = get_user_by_username(username)
    if not user:
        return None
    if check_password_hash(user["password"], password):
        return user
    return None

def save_appointment_to_db(customer_id, name, phone, gender, service, appointment_time, message, cart, total):
    conn = get_db_conn()
    cur = conn.cursor()
    cart_json = json.dumps(cart)
    cur.execute("""
        INSERT INTO appointments
            (customer_id, name, phone, gender, service, appointment_time, message, cart, total, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Upcoming')
    """, (customer_id, name, phone, gender, service, appointment_time, message, cart_json, total))
    conn.commit()
    appt_id = cur.lastrowid
    conn.close()
    return appt_id

def get_all_appointments():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM appointments ORDER BY appointment_time ASC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_appointments_by_customer(customer_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM appointments WHERE customer_id = ? ORDER BY appointment_time DESC", (customer_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_appointment_status(appt_id, status):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("UPDATE appointments SET status = ? WHERE id = ?", (status, appt_id))
    conn.commit()
    conn.close()

def delete_appointment_db(appt_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM appointments WHERE id = ?", (appt_id,))
    conn.commit()
    conn.close()

def save_review_to_db(customer_id, name, rating, comment):
    conn = get_db_conn()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    cur.execute("""
        INSERT INTO reviews (customer_id, name, rating, comment, date)
        VALUES (?, ?, ?, ?, ?)
    """, (customer_id, name, rating, comment, now))
    conn.commit()
    conn.close()

def get_all_reviews():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reviews ORDER BY date DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# utility to convert DB row fields (cart string) back to Python types and apply auto-complete
def normalize_appointments(appts):
    out = []
    for a in appts:
        # convert cart json -> list
        try:
            a_cart = json.loads(a.get("cart")) if a.get("cart") else []
        except Exception:
            a_cart = []
        a["cart"] = a_cart
        # ensure 'total' is float/int
        a["total"] = float(a.get("total") or 0)
        # appointment_time maybe stored as string; try to parse
        appt_time_str = a.get("appointment_time")
        try:
            appt_dt = datetime.fromisoformat(appt_time_str) if appt_time_str else None
        except Exception:
            # try common format
            try:
                appt_dt = datetime.strptime(appt_time_str, "%Y-%m-%dT%H:%M")
            except Exception:
                appt_dt = None
        # Auto-complete status: if not cancelled and appointment time passed -> Completed
        if a.get("status") not in ("Cancelled", "completed", "Completed", "completed", "Cancelled"):
            if appt_dt and appt_dt < datetime.now():
                # update in memory and DB if not already Completed
                if a.get("status") != "Completed":
                    update_appointment_status(a["id"], "Completed")
                    a["status"] = "Completed"
        # Normalize status capitalization
        if a.get("status"):
            a["status"] = str(a["status"]).capitalize()
        else:
            a["status"] = "Upcoming"
        out.append(a)
    return out

# ---------------------------
# ROUTES
# ---------------------------

@app.route('/')
def homepage():
    # show homepage with reviews pulled from DB
    reviews = get_all_reviews()
    return render_template('homepage.html', reviews=reviews)

@app.route('/avail')
def avail():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('avail.html')

@app.route('/form', methods=['GET', 'POST'])
def form():
    # User must be logged in
    if 'username' not in session:
        return redirect(url_for('login'))

    # ---------------------------
    # POST — Customer submits form
    # ---------------------------
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        gender = request.form.get('sex')   # your current form uses "sex"
        service = request.form.get('service') or None
        appointment_time = request.form.get('meeting-time')
        message = request.form.get('message')

        cart = session.get('cart', [])
        total = session.get('total', 0)

        # Get customer ID from DB
        user = get_user_by_username(session.get('username'))
        customer_id = user["id"] if user else None

        # Save appointment to DB
        save_appointment_to_db(
            customer_id,
            name,
            phone,
            gender,
            service,
            appointment_time,
            message,
            cart,
            total
        )

        # Show receipt (your existing design)
        return render_template(
            'receipt.html',
            name=name,
            phone=phone,
            gender=gender,
            service=service,
            appointment_time=appointment_time,
            message=message,
            cart=cart,
            total=total
        )

    # ---------------------------
    # GET — Show form with AUTO-FILL
    # ---------------------------

    username = session['username']

    # Load user info from database
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cur.fetchone()
    conn.close()

    cart = session.get('cart', [])
    total = session.get('total', 0)

    # Pass user info for auto-fill
    return render_template(
        'form.html',
        cart=cart,
        total=total,
        user=user
    )

@app.route('/save_cart', methods=['POST'])
def save_cart():
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 401
    session['cart'] = request.json.get('cart', [])
    session['total'] = request.json.get('total', 0)
    return {'message': 'Cart saved successfully'}

# ---------------------------
# REGISTER
# ---------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        phone = request.form.get('phone') or None
        gender = request.form.get('gender') or None

        if not username or not password:
            error = "Please provide a username and password."
            return render_template('register.html', error=error)

        if get_user_by_username(username):
            error = "Username already taken."
            return render_template('register.html', error=error)

        user_id = create_user(username, password, phone, gender)
        if not user_id:
            error = "Could not create user. Try a different username."
            return render_template('register.html', error=error)

        # auto-login after registration
        user = get_user_by_username(username)
        session['username'] = user['username']
        session['role'] = user['role']
        session['user_id'] = user['id']
        return redirect(url_for('homepage'))

    return render_template('register.html', error=error)

# ---------------------------
# LOGIN / LOGOUT
# ---------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        user = check_credentials(username, password)
        if user:
            session['username'] = user['username']
            session['role'] = user['role']
            session['user_id'] = user['id']
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('homepage'))
        else:
            error = "Invalid username or password"

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------------------------
# CUSTOMER: Booking History & Leave Review
# ---------------------------
@app.route('/customer/history')
def booking_history():
    if 'username' not in session:
        return redirect(url_for('login'))
    user_id = session.get('user_id')
    if not user_id:
        # user not registered (should not happen) -> redirect to login
        return redirect(url_for('login'))
    appts = get_appointments_by_customer(user_id)
    appts = normalize_appointments(appts)
    return render_template('booking_history.html', appointments=appts)

@app.route('/add_review', methods=['GET', 'POST'])
def add_review():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        name = request.form.get('name') or None
        rating = request.form.get('rating')
        comment = request.form.get('comment')
        date = datetime.now().strftime("%Y-%m-%d")

        user = get_user_by_username(session['username'])
        customer_id = user["id"]

        save_review_to_db(customer_id, name, rating, comment, date)

        return redirect(url_for('add_review'))  # reload page after saving

    # Get recent reviews
    reviews = get_all_reviews()

    return render_template("add_review.html", reviews=reviews)

@app.route('/admin', methods=['GET'])
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    # optional filter via query param ?status=Upcoming/Completed/Cancelled/All
    status_filter = request.args.get('status', 'All')
    appts = get_all_appointments()
    appts = normalize_appointments(appts)

    if status_filter and status_filter != 'All':
        appts = [a for a in appts if str(a.get('status')).lower() == status_filter.lower()]

    # counts for quick summary
    counts = {"Upcoming": 0, "Completed": 0, "Cancelled": 0}
    for a in get_all_appointments():
        # re-normalize in-memory
        s = a.get('status') or 'Upcoming'
        s_normal = str(s).capitalize()
        if s_normal in counts:
            counts[s_normal] += 1

    return render_template('admin.html', appointments=appts, counts=counts, current_filter=status_filter)

# Update appointment status (AJAX or form post)
@app.route('/admin/update_status', methods=['POST'])
def admin_update_status():
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 403
    appt_id = request.form.get('appointment_id') or request.json.get('appointment_id')
    new_status = request.form.get('status') or request.json.get('status')
    if not appt_id or not new_status:
        return jsonify({"error": "Missing data"}), 400
    update_appointment_status(int(appt_id), new_status.capitalize())
    return redirect(url_for('admin_dashboard'))

# Delete appointment (admin)
@app.route('/admin/delete/<int:appointment_id>', methods=['GET'])
def admin_delete_appointment(appointment_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    delete_appointment_db(appointment_id)
    return redirect(url_for('admin_dashboard'))

# ---------------------------
# Simple endpoints to view reviews (admin)
# ---------------------------
@app.route('/admin/reviews')
def admin_reviews():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    reviews = get_all_reviews()
    return render_template('admin_review.html', reviews=reviews)

# ---------------------------
# Small helper page to view users (admin) - optional
# ---------------------------
@app.route('/admin/users')
def admin_users():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role FROM users ORDER BY id")
    users = cur.fetchall()
    conn.close()
    return render_template('admin_user.html', users=users)

# ---------------------------
# Run app
# ---------------------------
if __name__ == '__main__':
    # ensure DB initialized
    init_db_if_needed()
    app.run(debug=True)
