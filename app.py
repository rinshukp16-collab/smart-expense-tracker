from flask import Flask, render_template, request, redirect, url_for, Response, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import csv
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'my-secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = 'login' 
login_manager.init_app(app)

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    expenses = db.relationship('Expense', backref='author', lazy=True)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)    
    category = db.Column(db.String(50), nullable=False, default='General')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# --- ROUTES ---

@app.route('/')
@login_required
def index():
    # 1. സെർച്ച് & ഫിൽട്ടർ ലോജിക്
    search_query = request.args.get('search')
    category_filter = request.args.get('category')
    
    query = Expense.query.filter_by(user_id=current_user.id)

    if search_query:
        query = query.filter(Expense.item.contains(search_query))
    
    if category_filter and category_filter != 'All':
        query = query.filter_by(category=category_filter)

    expenses = query.order_by(Expense.date.desc()).all()
    total = sum(exp.amount for exp in expenses)
    
    # 2. ബഡ്ജറ്റ് ലിമിറ്റ് ലോജിക്
    budget_limit = 5000 
    over_budget = total > budget_limit
    
    return render_template('index.html', 
                           expenses=expenses, 
                           total=total, 
                           name=current_user.username,
                           over_budget=over_budget,
                           budget_limit=budget_limit)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        if User.query.filter_by(username=username).first():
            flash('Username already exists!')
            return redirect(url_for('signup'))
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash('Login failed. Check your credentials.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add', methods=['POST'])
@login_required
def add():
    item = request.form.get('item')
    amount = request.form.get('amount')
    category = request.form.get('category')
    if item and amount:
        new_expense = Expense(item=item, amount=float(amount), category=category, user_id=current_user.id)
        db.session.add(new_expense)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard_view():
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    category_data = {}
    for exp in expenses:
        category_data[exp.category] = category_data.get(exp.category, 0) + exp.amount
    labels = list(category_data.keys())
    values = list(category_data.values())
    return render_template('dashboard.html', labels=labels, values=values)

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    expense = Expense.query.get_or_404(id)
    if expense.user_id != current_user.id:
        return redirect(url_for('index'))
    if request.method == 'POST':
        expense.item = request.form.get('item')
        expense.amount = float(request.form.get('amount'))
        expense.category = request.form.get('category')
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('edit.html', expense=expense)

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    expense = Expense.query.get_or_404(id)
    if expense.user_id == current_user.id:
        db.session.delete(expense)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/export/csv')
@login_required
def export_csv():
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Item', 'Category', 'Amount', 'Date'])
    for exp in expenses:
        writer.writerow([exp.item, exp.category, exp.amount, exp.date.strftime('%Y-%m-%d')])
    output.seek(0)
    return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=expenses.csv"})

if __name__ == "__main__":
    app.run(debug=True)