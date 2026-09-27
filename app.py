import os
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db_connection, init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "spendly-dev-secret-change-this")

init_db()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


@app.context_processor
def inject_user():
    return {"current_user_name": session.get("user_name", "Vaibhavi")}


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill in all required fields.", "error")
            return render_template("signup.html")

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "error")
            return render_template("signup.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")

        conn = get_db_connection()
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing:
            conn.close()
            flash("An account with this email already exists.", "error")
            return render_template("signup.html")

        cursor = conn.execute(
            """
            INSERT INTO users (name, email, password)
            VALUES (?, ?, ?)
            """,
            (name, email, generate_password_hash(password))
        )
        user_id = cursor.lastrowid

        conn.execute(
            """
            INSERT INTO budgets (user_id, monthly_budget)
            VALUES (?, ?)
            """,
            (user_id, 12000)
        )

        conn.commit()
        conn.close()

        session.clear()
        session["user_id"] = user_id
        session["user_name"] = name

        return redirect(url_for("dashboard"))

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    current_month = datetime.now().strftime("%Y-%m")
    today = date.today().isoformat()

    conn = get_db_connection()

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    expenses = conn.execute(
        """
        SELECT *
        FROM expenses
        WHERE user_id = ?
        ORDER BY date DESC, id DESC
        """,
        (user_id,)
    ).fetchall()

    total_spent = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE user_id = ?
        AND substr(date, 1, 7) = ?
        """,
        (user_id, current_month)
    ).fetchone()[0]

    today_spent, today_transactions = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0), COUNT(*)
        FROM expenses
        WHERE user_id = ? AND date = ?
        """,
        (user_id, today)
    ).fetchone()

    budget_row = conn.execute(
        "SELECT monthly_budget FROM budgets WHERE user_id = ?",
        (user_id,)
    ).fetchone()

    monthly_budget = budget_row["monthly_budget"] if budget_row else 12000
    remaining = monthly_budget - total_spent
    budget_percentage = round((total_spent / monthly_budget) * 100) if monthly_budget else 0
    progress_percentage = min(max(budget_percentage, 0), 100)

    category_colors = {
        "Food": "#ff7f9f",
        "Shopping": "#a66cff",
        "Travel": "#55c98b",
        "Education": "#ffd21c",
        "Bills": "#76b5f0",
        "Others": "#d28ce8",
    }

    category_rows = conn.execute(
        """
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ?
        AND substr(date, 1, 7) = ?
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id, current_month)
    ).fetchall()

    categories = []
    for row in category_rows:
        percentage = round((row["total"] / total_spent) * 100) if total_spent else 0
        categories.append({
            "name": row["category"],
            "amount": row["total"],
            "percentage": percentage,
            "color": category_colors.get(row["category"], "#d28ce8"),
        })

    if categories:
        # Build the donut from actual amounts rather than rounded percentages.
        current_angle = 0
        parts = []
        for category in categories:
            angle = (category["amount"] / total_spent) * 360
            end_angle = current_angle + angle
            parts.append(
                f'{category["color"]} {current_angle:.2f}deg {end_angle:.2f}deg'
            )
            current_angle = end_angle
        donut_gradient = "conic-gradient(" + ", ".join(parts) + ")"
    else:
        donut_gradient = "conic-gradient(#e9e4ee 0deg 360deg)"

    start_of_week = date.today() - timedelta(days=date.today().weekday())
    weekly_data = []

    for i in range(7):
        current_day = start_of_week + timedelta(days=i)
        amount = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM expenses
            WHERE user_id = ? AND date = ?
            """,
            (user_id, current_day.isoformat())
        ).fetchone()[0]

        weekly_data.append({
            "day": current_day.strftime("%a"),
            "amount": amount,
        })

    max_weekly_amount = max((item["amount"] for item in weekly_data), default=0)

    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        expenses=expenses,
        total_spent=total_spent,
        today_spent=today_spent,
        today_transactions=today_transactions,
        monthly_budget=monthly_budget,
        remaining=remaining,
        budget_percentage=progress_percentage,
        actual_budget_percentage=budget_percentage,
        categories=categories,
        donut_gradient=donut_gradient,
        weekly_data=weekly_data,
        max_weekly_amount=max_weekly_amount,
    )


@app.route("/add-expense", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", 0))
        except ValueError:
            amount = 0

        category = request.form.get("category", "").strip()
        title = request.form.get("description", "").strip()
        expense_date = request.form.get("date", "").strip()

        if amount <= 0 or not category or not title or not expense_date:
            flash("Please enter valid expense details.", "error")
            return render_template("add_expense.html")

        conn = get_db_connection()
        conn.execute(
            """
            INSERT INTO expenses (user_id, title, amount, category, date)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session["user_id"], title, amount, category, expense_date)
        )
        conn.commit()
        conn.close()

        flash("Expense added successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("add_expense.html", today=date.today().isoformat())


@app.route("/expenses")
@login_required
def expenses():
    search = request.args.get("search", "").strip()

    conn = get_db_connection()

    if search:
        like = f"%{search}%"
        rows = conn.execute(
            """
            SELECT *
            FROM expenses
            WHERE user_id = ?
            AND (title LIKE ? OR category LIKE ? OR date LIKE ?)
            ORDER BY date DESC, id DESC
            """,
            (session["user_id"], like, like, like)
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM expenses
            WHERE user_id = ?
            ORDER BY date DESC, id DESC
            """,
            (session["user_id"],)
        ).fetchall()

    conn.close()

    total = sum(row["amount"] for row in rows)
    return render_template(
        "expenses.html",
        expenses=rows,
        search=search,
        total=total,
    )


@app.route("/edit-expense/<int:expense_id>", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    conn = get_db_connection()

    expense = conn.execute(
        """
        SELECT *
        FROM expenses
        WHERE id = ? AND user_id = ?
        """,
        (expense_id, session["user_id"])
    ).fetchone()

    if expense is None:
        conn.close()
        flash("Expense not found.", "error")
        return redirect(url_for("expenses"))

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount", 0))
        except ValueError:
            amount = 0

        category = request.form.get("category", "").strip()
        title = request.form.get("description", "").strip()
        expense_date = request.form.get("date", "").strip()

        if amount <= 0 or not category or not title or not expense_date:
            conn.close()
            flash("Please enter valid expense details.", "error")
            return render_template("edit_expense.html", expense=expense)

        conn.execute(
            """
            UPDATE expenses
            SET title = ?, amount = ?, category = ?, date = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                title,
                amount,
                category,
                expense_date,
                expense_id,
                session["user_id"],
            )
        )
        conn.commit()
        conn.close()

        flash("Expense updated successfully.", "success")
        return redirect(url_for("expenses"))

    conn.close()
    return render_template("edit_expense.html", expense=expense)


@app.route("/delete-expense/<int:expense_id>", methods=["POST"])
@login_required
def delete_expense(expense_id):
    conn = get_db_connection()
    conn.execute(
        """
        DELETE FROM expenses
        WHERE id = ? AND user_id = ?
        """,
        (expense_id, session["user_id"])
    )
    conn.commit()
    conn.close()

    flash("Expense deleted.", "success")
    return redirect(url_for("expenses"))


@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    conn = get_db_connection()

    if request.method == "POST":
        try:
            new_budget = float(request.form.get("budget", 0))
        except ValueError:
            new_budget = 0

        if new_budget <= 0:
            conn.close()
            flash("Budget must be greater than zero.", "error")
            return redirect(url_for("budget"))

        conn.execute(
            """
            UPDATE budgets
            SET monthly_budget = ?
            WHERE user_id = ?
            """,
            (new_budget, session["user_id"])
        )
        conn.commit()
        conn.close()

        flash("Monthly budget updated.", "success")
        return redirect(url_for("dashboard"))

    budget_row = conn.execute(
        "SELECT monthly_budget FROM budgets WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()

    monthly_budget = budget_row["monthly_budget"] if budget_row else 12000
    conn.close()

    return render_template("budget.html", monthly_budget=monthly_budget)


@app.route("/analytics")
@login_required
def analytics():
    user_id = session["user_id"]
    current_month = datetime.now().strftime("%Y-%m")

    conn = get_db_connection()

    total_spent = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM expenses
        WHERE user_id = ?
        AND substr(date, 1, 7) = ?
        """,
        (user_id, current_month)
    ).fetchone()[0]

    category_rows = conn.execute(
        """
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ?
        AND substr(date, 1, 7) = ?
        GROUP BY category
        ORDER BY total DESC
        """,
        (user_id, current_month)
    ).fetchall()

    daily_rows = conn.execute(
        """
        SELECT date, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ?
        AND substr(date, 1, 7) = ?
        GROUP BY date
        ORDER BY date
        """,
        (user_id, current_month)
    ).fetchall()

    conn.close()

    category_data = []
    for row in category_rows:
        percentage = round((row["total"] / total_spent) * 100) if total_spent else 0
        category_data.append({
            "name": row["category"],
            "amount": row["total"],
            "percentage": percentage,
        })

    return render_template(
        "analytics.html",
        total_spent=total_spent,
        categories=category_data,
        daily_data=daily_rows,
        month_name=datetime.now().strftime("%B %Y"),
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db_connection()

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            conn.close()
            flash("Name cannot be empty.", "error")
            return redirect(url_for("profile"))

        conn.execute(
            "UPDATE users SET name = ? WHERE id = ?",
            (name, session["user_id"])
        )
        conn.commit()
        conn.close()

        session["user_name"] = name
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    conn.close()
    return render_template("profile.html", user=user)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        theme = request.form.get("theme", "light")
        session["theme"] = theme
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))

    return render_template(
        "settings.html",
        theme=session.get("theme", "light")
    )


if __name__ == "__main__":
    app.run(debug=True)
