import os
from io import BytesIO
from functools import wraps
from datetime import date, timedelta
from flask import Flask, flash, redirect, render_template, request, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, func
from werkzeug.security import check_password_hash, generate_password_hash
from openpyxl import Workbook

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-me-before-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL', 'mysql+pymysql://root@127.0.0.1:3306/smart_library?charset=utf8mb4')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('admin_id'):
            flash('请先登录管理员账号。', 'danger')
            return redirect(url_for('auth'))
        return view(*args, **kwargs)
    return wrapped


class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.Date, default=date.today, nullable=False)


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
    if Book.query.count() < 30:
        cats = {c.name: c for c in Category.query.all()}
        samples = [
            ('深入理解计算机系统','Randal Bryant','计算机'),('Python 数据分析','Wes McKinney','计算机'),('经济学原理','N. Gregory Mankiw','经济管理'),
            ('算法导论','Thomas Cormen','计算机'),('数据库系统概念','Abraham Silberschatz','计算机'),('操作系统导论','Remzi Arpaci-Dusseau','计算机'),
            ('机器学习','周志华','计算机'),('深度学习','Ian Goodfellow','计算机'),('计算机网络','谢希仁','计算机'),('代码整洁之道','Robert Martin','计算机'),
            ('人类简史','尤瓦尔·赫拉利','文学'),('百年孤独','加西亚·马尔克斯','文学'),('活着','余华','文学'),('围城','钱钟书','文学'),
            ('平凡的世界','路遥','文学'),('解忧杂货店','东野圭吾','文学'),('月亮与六便士','毛姆','文学'),('小王子','圣埃克苏佩里','文学'),
            ('国富论','亚当·斯密','经济管理'),('资本论','马克思','经济管理'),('原则','瑞·达利欧','经济管理'),('穷查理宝典','彼得·考夫曼','经济管理'),
            ('投资学','博迪','经济管理'),('金融学','黄达','经济管理'),('经济解释','张五常','经济管理'),('管理学','斯蒂芬·罗宾斯','经济管理'),
            ('统计学','贾俊平','经济管理'),('时间简史','史蒂芬·霍金','文学'),('苏菲的世界','乔斯坦·贾德','文学'),('思考，快与慢','丹尼尔·卡尼曼','经济管理'),
        ]
        existing = {b.title for b in Book.query.all()}
        db.session.add_all([Book(isbn=f'9787000{i:06d}', title=t, author=a, category=cats[c], total_qty=5+i%6, available_qty=5+i%6) for i,(t,a,c) in enumerate(samples, 1) if t not in existing])
    if Reader.query.count() < 20:
        names = ['李明','陈晓','周宁','王晨','赵琳','刘洋','孙悦','黄磊','吴静','徐涛','何雨','马超','朱莉','郭峰','林清','宋扬','唐薇','罗浩','许诺','邓洁','方宇','谢欣','潘博','程雪','冯凯']
        existing = {r.name for r in Reader.query.all()}
        db.session.add_all([Reader(name=n, phone=f'138{idx:08d}') for idx,n in enumerate(names, 10001) if n not in existing])
        db.session.commit()
    if Loan.query.count() < 25:
        readers, books = Reader.query.order_by(Reader.id).all(), Book.query.order_by(Book.id).all()
        for i in range(min(24, len(readers), len(books))):
            book = books[i]
            if book.available_qty > 0:
                due = date.today() + timedelta(days=(-i if i % 7 == 0 else 7 + i))
                db.session.add(Loan(reader=readers[i], book=book, due_at=due, status='借阅中'))
                book.available_qty -= 1
        db.session.commit()
    # 构造可用于排行榜和趋势图的历史借阅数据：热门书会被多次借阅。
    if Loan.query.count() < 60:
        readers, books = Reader.query.order_by(Reader.id).all(), Book.query.order_by(Book.id).all()
        weights = [12, 10, 8, 6, 5, 4, 3, 3, 2, 2]
        for book, times in zip(books[:10], weights):
            current = Loan.query.filter_by(book_id=book.id).count()
            for n in range(max(0, times - current)):
                borrowed = date.today() - timedelta(days=20 + n * 3)
                db.session.add(Loan(reader=readers[(book.id + n) % len(readers)], book=book,
                                    borrowed_at=borrowed, due_at=borrowed + timedelta(days=30),
                                    returned_at=borrowed + timedelta(days=12), status='已归还'))
        db.session.commit()


@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        action, username, password = request.form['action'], request.form.get('username', '').strip(), request.form.get('password', '')
        if action == 'register':
            if Admin.query.filter_by(username=username).first(): flash('用户名已存在，请换一个。', 'danger')
            elif len(username) < 2 or len(password) < 6: flash('用户名至少 2 位，密码至少 6 位。', 'danger')
            else:
                admin = Admin(username=username, password_hash=generate_password_hash(password)); db.session.add(admin); db.session.commit()
                session['admin_id'], session['admin_name'] = admin.id, admin.username; return redirect(url_for('dashboard'))
        else:
            admin = Admin.query.filter_by(username=username).first()
            if admin and check_password_hash(admin.password_hash, password):
                session['admin_id'], session['admin_name'] = admin.id, admin.username; return redirect(url_for('dashboard'))
            flash('用户名或密码错误。', 'danger')
    return render_template('auth.html')


@app.get('/logout')
def logout():
    session.clear(); return redirect(url_for('auth'))


@app.get('/')
@login_required
def dashboard():
    today = date.today()
    stats = {'books': Book.query.count(), 'readers': Reader.query.count(),
             'active': Loan.query.filter_by(status='借阅中').count(),
             'overdue': Loan.query.filter(Loan.status == '借阅中', Loan.due_at < today).count()}
    popular = db.session.query(Book.title, func.count(Loan.id).label('n')).join(Loan).group_by(Book.id).order_by(func.count(Loan.id).desc()).limit(5).all()
    return render_template('dashboard.html', stats=stats, popular=popular)


@app.route('/books', methods=['GET', 'POST'])
@login_required
def books():
    if request.method == 'POST':
        book = Book(isbn=request.form.get('isbn') or None, title=request.form['title'], author=request.form['author'],
                    category_id=request.form['category_id'], total_qty=int(request.form['qty']), available_qty=int(request.form['qty']))
        db.session.add(book); db.session.commit(); flash('图书已入库', 'success'); return redirect(url_for('books'))
    q = request.args.get('q', '')
    rows = Book.query.filter(Book.title.contains(q) | Book.author.contains(q)).order_by(Book.id.desc()).all() if q else Book.query.order_by(Book.id.desc()).all()
    return render_template('books.html', books=rows, categories=Category.query.all(), q=q)


@app.post('/books/<int:id>/delete')
@login_required
def delete_book(id):
    book = db.get_or_404(Book, id)
    if book.loans: flash('存在借阅历史，不能删除', 'danger')
    else: db.session.delete(book); db.session.commit(); flash('图书已删除', 'success')
    return redirect(url_for('books'))


@app.route('/readers', methods=['GET', 'POST'])
@login_required
def readers():
    if request.method == 'POST':
        db.session.add(Reader(name=request.form['name'], phone=request.form.get('phone'), status=request.form.get('status', '正常')))
        db.session.commit(); flash('读者已登记', 'success'); return redirect(url_for('readers'))
    return render_template('readers.html', readers=Reader.query.order_by(Reader.id.desc()).all())


@app.post('/readers/<int:id>/toggle')
@login_required
def toggle_reader(id):
    reader = db.get_or_404(Reader, id); reader.status = '冻结' if reader.status == '正常' else '正常'; db.session.commit()
    return redirect(url_for('readers'))


@app.route('/loans', methods=['GET', 'POST'])
@login_required
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
@login_required
def return_loan(id):
    loan = db.get_or_404(Loan, id)
    if loan.status == '借阅中': loan.status = '已归还'; loan.returned_at = date.today(); loan.book.available_qty += 1; db.session.commit(); flash('归还成功', 'success')
    return redirect(url_for('loans'))


@app.get('/ai-insights')
@login_required
def ai_insights():
    today = date.today(); overdue = Loan.query.filter(Loan.status == '借阅中', Loan.due_at < today).count(); out = Book.query.filter(Book.available_qty == 0).count()
    return render_template('ai.html', overdue=overdue, out=out, active=Loan.query.filter_by(status='借阅中').count())


@app.route('/admins', methods=['GET', 'POST'])
@login_required
def admins():
    if request.method == 'POST':
        username, password = request.form.get('username', '').strip(), request.form.get('password', '')
        if Admin.query.filter_by(username=username).first(): flash('用户名已存在。', 'danger')
        elif len(username) < 2 or len(password) < 6: flash('用户名至少 2 位，密码至少 6 位。', 'danger')
        else: db.session.add(Admin(username=username, password_hash=generate_password_hash(password))); db.session.commit(); flash('管理员已新增。', 'success')
        return redirect(url_for('admins'))
    return render_template('admins.html', admins=Admin.query.order_by(Admin.id.desc()).all())


@app.post('/admins/<int:id>/delete')
@login_required
def delete_admin(id):
    if id == session['admin_id']: flash('不能删除当前登录账号。', 'danger')
    else:
        admin = db.get_or_404(Admin, id); db.session.delete(admin); db.session.commit(); flash('管理员已删除。', 'success')
    return redirect(url_for('admins'))


@app.get('/export/<kind>')
@login_required
def export_data(kind):
    wb, ws = Workbook(), Workbook().active
    wb = ws.parent
    if kind == 'books':
        ws.title='图书数据'; ws.append(['ID','ISBN','书名','作者','分类','总量','可借量'])
        for b in Book.query.order_by(Book.id).all(): ws.append([b.id,b.isbn,b.title,b.author,b.category.name,b.total_qty,b.available_qty])
    elif kind == 'readers':
        ws.title='读者数据'; ws.append(['ID','姓名','电话','状态'])
        for r in Reader.query.order_by(Reader.id).all(): ws.append([r.id,r.name,r.phone,r.status])
    else:
        ws.title='借阅数据'; ws.append(['ID','读者','图书','借出日','应还日','归还日','状态'])
        for x in Loan.query.order_by(Loan.id).all(): ws.append([x.id,x.reader.name,x.book.title,x.borrowed_at,x.due_at,x.returned_at,x.status])
    stream = BytesIO(); wb.save(stream); stream.seek(0)
    return send_file(stream, as_attachment=True, download_name=f'{kind}_export.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


if __name__ == '__main__':
    with app.app_context(): db.create_all(); seed()
    app.run(debug=True)
