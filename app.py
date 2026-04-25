from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
import calendar
import sqlite3

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATABASE = 'finance_tracker.db'


def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            payment_method TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    conn.commit()
    conn.close()


init_db()


@app.route('/')
def index():
    if 'username' in session:
        user_id = session['user_id']
        username = session['username']

        today = datetime.now()
        current_month = today.strftime('%Y-%m')
        current_day = today.day
        days_in_month = calendar.monthrange(today.year, today.month)[1]

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        c.execute("SELECT * FROM transactions WHERE user_id = ?", (user_id,))
        transactions = c.fetchall()

        total_amount = sum(transaction[2] for transaction in transactions)
        total_upi = sum(transaction[2] for transaction in transactions if transaction[6] == 'UPI')
        total_cash = sum(transaction[2] for transaction in transactions if transaction[6] == 'Cash')

        c.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ? AND substr(date, 1, 7) = ?
        """, (user_id, current_month))

        current_month_spending = c.fetchone()[0] or 0
        conn.close()

        average_daily_spending = current_month_spending / current_day if current_day > 0 else 0
        predicted_month_end_expense = average_daily_spending * days_in_month

        if current_month_spending == 0:
            spending_status = "No current month spending recorded"
            status_class = "secondary"
        elif predicted_month_end_expense >= current_month_spending * 1.5:
            spending_status = "High spending risk"
            status_class = "danger"
        elif predicted_month_end_expense > current_month_spending:
            spending_status = "Spending may increase by month end"
            status_class = "warning"
        else:
            spending_status = "Normal spending pattern"
            status_class = "success"

        return render_template(
            'index.html',
            username=username,
            total_amount=round(total_amount, 2),
            total_upi=round(total_upi, 2),
            total_cash=round(total_cash, 2),
            current_month_spending=round(current_month_spending, 2),
            average_daily_spending=round(average_daily_spending, 2),
            predicted_month_end_expense=round(predicted_month_end_expense, 2),
            spending_status=spending_status,
            status_class=status_class
        )

    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute(
            "SELECT id, username FROM users WHERE username = ? AND password = ?",
            (username, password)
        )
        user = c.fetchone()
        conn.close()

        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password. Please try again.', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        existing_user = c.fetchone()

        if existing_user:
            flash('Username already exists. Please choose a different one.', 'error')
            conn.close()
        else:
            c.execute(
                "INSERT INTO users (username, email, phone, password) VALUES (?, ?, ?, ?)",
                (username, email, phone, password)
            )
            conn.commit()
            conn.close()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/transactions')
def transactions():
    if 'username' in session:
        user_id = session['user_id']
        username = session['username']
        search_query = request.args.get('q', '').strip()

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        if search_query:
            search_pattern = f"%{search_query}%"
            c.execute("""
                SELECT * FROM transactions
                WHERE user_id = ?
                AND (
                    date LIKE ?
                    OR category LIKE ?
                    OR CAST(amount AS TEXT) LIKE ?
                    OR payment_method LIKE ?
                    OR description LIKE ?
                )
                ORDER BY date DESC
            """, (
                user_id,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern,
                search_pattern
            ))
        else:
            c.execute("""
                SELECT * FROM transactions
                WHERE user_id = ?
                ORDER BY date DESC
            """, (user_id,))

        transactions = c.fetchall()
        conn.close()

        return render_template(
            'transaction.html',
            transactions=transactions,
            username=username,
            search_query=search_query
        )

    return redirect(url_for('login'))


@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    if 'username' in session:
        user_id = session['user_id']

        date = request.form.get('date', '').strip()
        category = request.form.get('category', '').strip()
        amount = request.form.get('amount', '').strip()
        payment_method = request.form.get('payment_method', '').strip()
        description = request.form.get('notes', '').strip()

        try:
            amount = float(amount)
        except ValueError:
            flash('Amount must be a valid number.', 'error')
            return redirect(url_for('transactions'))

        if amount <= 0:
            flash('Amount must be greater than 0. Negative or zero values are not allowed.', 'error')
            return redirect(url_for('transactions'))

        if not date:
            flash('Date is required.', 'error')
            return redirect(url_for('transactions'))

        if not category:
            flash('Category is required.', 'error')
            return redirect(url_for('transactions'))

        if not payment_method:
            flash('Payment method is required.', 'error')
            return redirect(url_for('transactions'))

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        c.execute("""
            INSERT INTO transactions 
            (user_id, date, category, amount, payment_method, description) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, date, category, amount, payment_method, description))

        conn.commit()
        conn.close()

        flash('Transaction added successfully.', 'success')
        return redirect(url_for('transactions'))

    return redirect(url_for('login'))


@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
def delete_transaction(transaction_id):
    if 'username' in session:
        user_id = session['user_id']

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (transaction_id, user_id)
        )
        conn.commit()
        conn.close()

        flash('Transaction deleted successfully.', 'success')
    else:
        flash('You must be logged in to delete a transaction.', 'error')

    return redirect(url_for('transactions'))


@app.route('/daily_spending_data')
def daily_spending_data():
    if 'username' in session:
        user_id = session['user_id']

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        c.execute("""
            SELECT date, SUM(amount)
            FROM transactions
            WHERE user_id = ?
            GROUP BY date
            ORDER BY date
        """, (user_id,))

        data = c.fetchall()
        conn.close()

        labels = [row[0] for row in data]
        amounts = [row[1] for row in data]

        return jsonify({'labels': labels, 'amounts': amounts})

    return redirect(url_for('login'))


@app.route('/monthly_spending_data')
def monthly_spending_data():
    if 'username' in session:
        user_id = session['user_id']

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        c.execute("""
            SELECT strftime('%Y-%m', date) AS month, SUM(amount)
            FROM transactions
            WHERE user_id = ?
            GROUP BY month
            ORDER BY month
        """, (user_id,))

        data = c.fetchall()
        conn.close()

        labels = [datetime.strptime(row[0], '%Y-%m').strftime('%b %Y') for row in data]
        amounts = [row[1] for row in data]

        return jsonify({'labels': labels, 'amounts': amounts})

    return redirect(url_for('login'))


@app.route('/statistics')
def statistics():
    user_id = session.get('user_id')

    if user_id:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        c.execute("SELECT SUM(amount) FROM transactions WHERE user_id = ?", (user_id,))
        total_expenses_result = c.fetchone()
        total_expenses = total_expenses_result[0] if total_expenses_result and total_expenses_result[0] else 0

        c.execute("""
            SELECT category, SUM(amount)
            FROM transactions
            WHERE user_id = ?
            GROUP BY category
        """, (user_id,))
        expense_by_category_result = c.fetchall()
        expense_by_category = dict(expense_by_category_result) if expense_by_category_result else {}

        c.execute("""
            SELECT category, SUM(amount)
            FROM transactions
            WHERE user_id = ?
            GROUP BY category
            ORDER BY SUM(amount) DESC
            LIMIT 5
        """, (user_id,))
        top_spending_categories_result = c.fetchall()
        top_spending_categories = dict(top_spending_categories_result) if top_spending_categories_result else {}

        conn.close()

        return render_template(
            'statistics.html',
            total_expenses=total_expenses,
            expense_by_category=expense_by_category,
            top_spending_categories=top_spending_categories
        )

    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)