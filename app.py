import os
from datetime import date, timedelta
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, func

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-me-before-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL', 'mysql+pymysql://root@127.0.0.1:3306/smart_library?charset=utf8mb4')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    books = db.relationship('Book', back_populates='category')


class Book(db.Model):
    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True)
    isbn = db.Column(db.String(20), unique=True)
    title = db.Column(db.String(120), nullable=False)
    author = db.Column(db.String(80), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    total_qty = db.Column(db.Integer, default=1, nullable=False)
    available_qty = db.Column(db.Integer, default=1, nullable=False)
    category = db.relationship('Category', back_populates='books')
    loans = db.relationship('Loan', back_populates='book')
    __table_args__ = (Index('idx_books_title', 'title'), Index('idx_books_category_stock', 'category_id', 'available_qty'))


class Reader(db.Model):
    __tablename__ = 'readers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20))
    status = db.Column(db.String(12), default='正常', nullable=False)
    loans = db.relationship('Loan', back_populates='reader')
    __table_args__ = (Index('idx_readers_name', 'name'), Index('idx_readers_status', 'status'))


class Loan(db.Model):
    __tablename__ = 'loans'
    id = db.Column(db.Integer, primary_key=True)
    reader_id = db.Column(db.Integer, db.ForeignKey('readers.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    borrowed_at = db.Column(db.Date, default=date.today, nullable=False)
    due_at = db.Column(db.Date, nullable=False)
    returned_at = db.Column(db.Date)
    status = db.Column(db.String(12), default='借阅中', nullable=False)
    reader = db.relationship('Reader', back_populates='loans')
    book = db.relationship('Book', back_populates='loans')
    __table_args__ = (Index('idx_loans_status_due', 'status', 'due_at'), Index('idx_loans_reader_status', 'reader_id', 'status'))


def seed():
    if not Category.query.first():
        db.session.add_all([Category(name='计算机'), Category(name='经济管理'), Category(name='文学')])
        db.session.commit()


@app.get('/')
def dashboard():
    today = date.today()
    stats = {'books': Book.query.count(), 'readers': Reader.query.count(),
             'active': Loan.query.filter_by(status='借阅中').count(),
             'overdue': Loan.query.filter(Loan.status == '借阅中', Loan.due_at < today).count()}
    popular = db.session.query(Book.title, func.count(Loan.id).label('n')).join(Loan).group_by(Book.id).order_by(func.count(Loan.id).desc()).limit(5).all()
    return render_template('dashboard.html', stats=stats, popular=popular)


@app.route('/books', methods=['GET', 'POST'])
def books():
    if request.method == 'POST':
        book = Book(isbn=request.form.get('isbn') or None, title=request.form['title'], author=request.form['author'],
                    category_id=request.form['category_id'], total_qty=int(request.form['qty']), available_qty=int(request.form['qty']))
        db.session.add(book); db.session.commit(); flash('图书已入库', 'success'); return redirect(url_for('books'))
    q = request.args.get('q', '')
    rows = Book.query.filter(Book.title.contains(q) | Book.author.contains(q)).order_by(Book.id.desc()).all() if q else Book.query.order_by(Book.id.desc()).all()
    return render_template('books.html', books=rows, categories=Category.query.all(), q=q)


@app.post('/books/<int:id>/delete')
def delete_book(id):
    book = db.get_or_404(Book, id)
    if book.loans: flash('存在借阅历史，不能删除', 'danger')
    else: db.session.delete(book); db.session.commit(); flash('图书已删除', 'success')
    return redirect(url_for('books'))


@app.route('/readers', methods=['GET', 'POST'])
def readers():
    if request.method == 'POST':
        db.session.add(Reader(name=request.form['name'], phone=request.form.get('phone'), status=request.form.get('status', '正常')))
        db.session.commit(); flash('读者已登记', 'success'); return redirect(url_for('readers'))
    return render_template('readers.html', readers=Reader.query.order_by(Reader.id.desc()).all())


@app.post('/readers/<int:id>/toggle')
def toggle_reader(id):
    reader = db.get_or_404(Reader, id); reader.status = '冻结' if reader.status == '正常' else '正常'; db.session.commit()
    return redirect(url_for('readers'))


@app.route('/loans', methods=['GET', 'POST'])
def loans():
    if request.method == 'POST':
        reader, book = db.get_or_404(Reader, request.form['reader_id']), db.get_or_404(Book, request.form['book_id'])
        if reader.status != '正常' or book.available_qty <= 0: flash('读者不可借或库存不足', 'danger')
        else:
            db.session.add(Loan(reader=reader, book=book, due_at=date.today() + timedelta(days=30))); book.available_qty -= 1; db.session.commit(); flash('借阅成功', 'success')
        return redirect(url_for('loans'))
    rows = Loan.query.order_by(Loan.id.desc()).all()
    return render_template('loans.html', loans=rows, readers=Reader.query.filter_by(status='正常').all(), books=Book.query.filter(Book.available_qty > 0).all(), today=date.today())


@app.post('/loans/<int:id>/return')
def return_loan(id):
    loan = db.get_or_404(Loan, id)
    if loan.status == '借阅中': loan.status = '已归还'; loan.returned_at = date.today(); loan.book.available_qty += 1; db.session.commit(); flash('归还成功', 'success')
    return redirect(url_for('loans'))


@app.get('/ai-insights')
def ai_insights():
    today = date.today(); overdue = Loan.query.filter(Loan.status == '借阅中', Loan.due_at < today).count(); out = Book.query.filter(Book.available_qty == 0).count()
    return render_template('ai.html', overdue=overdue, out=out, active=Loan.query.filter_by(status='借阅中').count())


if __name__ == '__main__':
    with app.app_context(): db.create_all(); seed()
    app.run(debug=True)
