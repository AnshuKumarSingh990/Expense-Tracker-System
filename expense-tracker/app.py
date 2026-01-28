from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import MySQLdb.cursors
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

app = Flask(__name__)
app.secret_key = "your_secret_key"

# =============================
# Database Configuration
# =============================
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'manager'
app.config['MYSQL_DB'] = 'expense_tracker'

mysql = MySQL(app)

# =============================
# Home Page
# =============================
@app.route('/')
def index():
    return render_template('index.html')

# =============================
# Register Page
# =============================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if not name or not email or not password:
            flash("All fields are required!", "danger")
            return render_template('register.html')

        hashed_password = generate_password_hash(password)

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        try:
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                (name, email, hashed_password)
            )
            mysql.connection.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('login'))
        except MySQLdb.IntegrityError:
            flash("Email already exists!", "danger")
            return render_template('register.html')
        finally:
            cursor.close()
    return render_template('register.html')

# =============================
# Login Page
# =============================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        cursor.close()

        if user and check_password_hash(user['password'], password):
            session['loggedin'] = True
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            flash("Login successful!", "success")
            return redirect(url_for('transactions'))
        else:
            flash("Invalid credentials!", "danger")
            return render_template('login.html')

    return render_template('login.html')

# =============================
# Logout
# =============================
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# =============================
# Transactions Page
# =============================
# =============================
# Transactions Page
# =============================
@app.route('/transactions', methods=['GET', 'POST'])
def transactions():
    if 'loggedin' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == 'POST':
        date = request.form.get('date')
        description = request.form.get('description')
        category = request.form.get('category')
        amount = request.form.get('amount')

        # Validate inputs
        if not date or not description or not category or not amount:
            flash("All fields are required!", "danger")
            return redirect(url_for('transactions'))

        try:
            amount = float(amount)
        except ValueError:
            flash("Invalid amount!", "danger")
            return redirect(url_for('transactions'))

        # Insert transaction
        cursor.execute(
            "INSERT INTO transactions (user_id, date, description, category, amount) VALUES (%s, %s, %s, %s, %s)",
            (session['user_id'], date, description, category, amount)
        )
        mysql.connection.commit()
        flash("Transaction added successfully!", "success")
        return redirect(url_for('transactions'))

    # Fetch all transactions for the user
    cursor.execute("SELECT * FROM transactions WHERE user_id=%s ORDER BY date DESC", (session['user_id'],))
    transactions = cursor.fetchall()

    # Category-wise totals for chart/report
    cursor.execute(
        "SELECT category, SUM(amount) as total FROM transactions WHERE user_id=%s GROUP BY category",
        (session['user_id'],)
    )
    report = cursor.fetchall()

    # Get budgets for user
    cursor.execute("SELECT * FROM budgets WHERE user_id=%s", (session['user_id'],))
    budgets = cursor.fetchall()

    # ================================
    # Check for over-budget categories
    # ================================
    over_budget = []
    for budget in budgets:
        category_name = budget['category']
        budget_amount = float(budget['budget_amount'])
        total_spent = sum(float(t['amount']) for t in transactions if t['category'] == category_name)
        if total_spent > budget_amount:
            over_budget.append({
                'category': category_name,
                'spent': total_spent,
                'budget': budget_amount
            })

    cursor.close()
    return render_template(
        'transactions.html',
        transactions=transactions,
        report=report,
        budgets=budgets,
        over_budget=over_budget
    )


def render_transactions(cursor):
    """Fetch transactions, reports, budgets and render template safely"""
    cursor.execute("SELECT * FROM transactions WHERE user_id=%s ORDER BY date DESC", (session['user_id'],))
    transactions = cursor.fetchall()

    cursor.execute(
        "SELECT category, SUM(amount) as total FROM transactions WHERE user_id=%s GROUP BY category",
        (session['user_id'],)
    )
    report = cursor.fetchall()

    cursor.execute("SELECT * FROM budgets WHERE user_id=%s", (session['user_id'],))
    budgets = cursor.fetchall()

    cursor.close()
    return render_template('transactions.html', transactions=transactions, report=report, budgets=budgets)

# =============================
# Set Budget Goals
# =============================
@app.route('/budget', methods=['POST'])
def budget():
    if 'loggedin' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    category = request.form.get('category')
    budget_amount = request.form.get('budget_amount')
    user_id = session['user_id']

    if not category or not budget_amount:
        flash("All fields are required!", "danger")
        return redirect(url_for('transactions'))

    try:
        budget_amount = float(budget_amount)
    except ValueError:
        flash("Invalid amount!", "danger")
        return redirect(url_for('transactions'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM budgets WHERE user_id=%s AND category=%s", (user_id, category))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("UPDATE budgets SET budget_amount=%s WHERE user_id=%s AND category=%s",
                       (budget_amount, user_id, category))
    else:
        cursor.execute("INSERT INTO budgets (user_id, category, budget_amount) VALUES (%s, %s, %s)",
                       (user_id, category, budget_amount))
    mysql.connection.commit()
    cursor.close()
    flash("Budget updated!", "success")
    return redirect(url_for('transactions'))

# =============================
# API endpoint for Chart.js
# =============================
@app.route('/report_data')
def report_data():
    if 'loggedin' not in session:
        return jsonify({})

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(
        "SELECT category, SUM(amount) as total FROM transactions WHERE user_id=%s GROUP BY category",
        (session['user_id'],)
    )
    data = cursor.fetchall()
    cursor.close()
    return jsonify(data)

# =============================
# Optional: Send Email Reminder
# =============================
def send_email_reminder(user_name, user_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    today = datetime.now().strftime('%Y-%m-%d')
    cursor.execute(
        "SELECT category, SUM(amount) as total FROM transactions WHERE user_id=%s AND date=%s GROUP BY category",
        (user_id, today)
    )
    summary = cursor.fetchall()
    cursor.close()

    if not summary:
        return

    body = f"Hello {user_name},\n\nHere is your transaction summary for today:\n"
    for row in summary:
        body += f"{row['category']}: ₹{row['total']}\n"
    body += "\nKeep tracking your expenses!"

    try:
        msg = MIMEText(body)
        msg['Subject'] = 'Daily Expense Summary'
        msg['From'] = 'youremail@example.com'
        msg['To'] = 'useremail@example.com'  # Replace with actual user email

        server = smtplib.SMTP('smtp.example.com', 587)
        server.starttls()
        server.login('youremail@example.com', 'yourpassword')
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("Email sending failed:", e)

# =============================
# Run App
# =============================
if __name__ == "__main__":
    app.run(debug=True)
