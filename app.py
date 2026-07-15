import os
import json
import base64
import hashlib
from io import BytesIO
from functools import wraps
from datetime import date, timedelta
from urllib import error as urlerror
from urllib import request as urlrequest
from flask import Flask, flash, redirect, render_template, request, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, case, func
from werkzeug.security import check_password_hash, generate_password_hash
from openpyxl import Workbook
from dotenv import load_dotenv
from cryptography.fernet import Fernet, InvalidToken

load_dotenv()
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


class ApiCredential(db.Model):
    """每位管理员各自保存的 AI 密钥；数据库中只保留加密后的内容。"""
    __tablename__ = 'api_credentials'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    encrypted_key = db.Column(db.String(500), nullable=False)
    updated_at = db.Column(db.Date, default=date.today, onupdate=date.today, nullable=False)


def credential_cipher():
    secret = app.config['SECRET_KEY'].encode('utf-8')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def current_admin_api_key():
    """优先使用当前管理员的私有密钥；未保存时才回退到部署环境变量。"""
    credential = ApiCredential.query.filter_by(admin_id=session['admin_id']).first()
    if credential:
        try:
            return credential_cipher().decrypt(credential.encrypted_key.encode('utf-8')).decode('utf-8')
        except (InvalidToken, ValueError):
            return None
    return os.getenv('DEEPSEEK_API_KEY') or os.getenv('AI_API_KEY')


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
    active = Loan.query.filter_by(status='借阅中').count()
    overdue = Loan.query.filter(Loan.status == '借阅中', Loan.due_at < today).count()
    total_qty, available_qty = db.session.query(
        func.coalesce(func.sum(Book.total_qty), 0),
        func.coalesce(func.sum(Book.available_qty), 0),
    ).one()
    normal_readers = Reader.query.filter_by(status='正常').count()
    stats = {'books': Book.query.count(), 'readers': Reader.query.count(),
             'active': active, 'overdue': overdue, 'loan_rate': round(active / total_qty * 100, 1) if total_qty else 0,
             'available_qty': available_qty, 'total_qty': total_qty, 'normal_readers': normal_readers}
    popular = db.session.query(Book.title, func.count(Loan.id).label('n')).join(Loan).group_by(Book.id).order_by(func.count(Loan.id).desc()).limit(5).all()
    category_rows = db.session.query(Category.name, func.coalesce(func.sum(Book.total_qty), 0)).outerjoin(Book).group_by(Category.id, Category.name).order_by(Category.id).all()
    loan_status = [('借阅中', active), ('已归还', Loan.query.filter_by(status='已归还').count()), ('逾期未还', overdue)]
    trend = [{'label': (today - timedelta(days=offset)).strftime('%m/%d'), 'count': Loan.query.filter(Loan.borrowed_at == today - timedelta(days=offset)).count()} for offset in range(6, -1, -1)]
    inventory = [('可借库存', available_qty), ('已借出', max(total_qty - available_qty, 0))]
    return render_template('dashboard.html', stats=stats, popular=popular, category_rows=category_rows,
                           loan_status=loan_status, trend=trend, inventory=inventory)


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
    # 先展示仍在借阅的记录，再展示已归还记录；各分组内按借出日期倒序。
    rows = Loan.query.order_by(
        case((Loan.status == '借阅中', 0), else_=1),
        Loan.borrowed_at.desc(),
        Loan.id.desc(),
    ).all()
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
    report = borrowing_report()
    own_credential = ApiCredential.query.filter_by(admin_id=session['admin_id']).first()
    return render_template(
        'ai.html',
        **report,
        ai_api_configured=bool(current_admin_api_key()),
        own_api_configured=bool(own_credential),
        generated_advice=session.pop('ai_generated_advice', None),
    )


def borrowing_report():
    """将 MySQL 借阅数据聚合成可解释的运营指标。"""
    today = date.today()

    def count_for(days, before_days=0):
        end = today - timedelta(days=before_days)
        start = end - timedelta(days=days - 1)
        return Loan.query.filter(Loan.borrowed_at.between(start, end)).count()

    last_7, previous_7 = count_for(7), count_for(7, 7)
    last_30, previous_30 = count_for(30), count_for(30, 30)
    trend = None if previous_7 == 0 else round((last_7 - previous_7) / previous_7 * 100)
    popular_now = (
        db.session.query(Book.title, func.count(Loan.id).label('borrow_count'))
        .join(Loan)
        .filter(Loan.borrowed_at >= today - timedelta(days=29))
        .group_by(Book.id, Book.title)
        .order_by(func.count(Loan.id).desc(), Book.title)
        .limit(5)
        .all()
    )
    popular_all = (
        db.session.query(Book.title, func.count(Loan.id).label('borrow_count'))
        .join(Loan)
        .group_by(Book.id, Book.title)
        .order_by(func.count(Loan.id).desc(), Book.title)
        .first()
    )
    overdue = Loan.query.filter(Loan.status == '借阅中', Loan.due_at < today).count()
    out = Book.query.filter(Book.available_qty == 0).count()
    active = Loan.query.filter_by(status='借阅中').count()
    lead_title = popular_now[0].title if popular_now else (popular_all.title if popular_all else '暂无借阅数据')
    return {
        'today': today,
        'active': active,
        'overdue': overdue,
        'out': out,
        'last_7': last_7,
        'previous_7': previous_7,
        'last_30': last_30,
        'previous_30': previous_30,
        'trend': trend,
        'popular_now': popular_now,
        'popular_all': popular_all,
        'lead_title': lead_title,
    }


@app.post('/ai-insights/api-key')
@login_required
def save_ai_api_key():
    api_key = request.form.get('api_key', '').strip()
    if len(api_key) < 12:
        flash('请输入有效的 DeepSeek API Key。', 'danger')
        return redirect(url_for('ai_insights'))
    credential = ApiCredential.query.filter_by(admin_id=session['admin_id']).first()
    encrypted_key = credential_cipher().encrypt(api_key.encode('utf-8')).decode('utf-8')
    if credential:
        credential.encrypted_key = encrypted_key
    else:
        db.session.add(ApiCredential(admin_id=session['admin_id'], encrypted_key=encrypted_key))
    db.session.commit()
    flash('你的 DeepSeek API Key 已加密保存，仅当前管理员账号可用。', 'success')
    return redirect(url_for('ai_insights'))


@app.post('/ai-insights/generate')
@login_required
def generate_ai_advice():
    """调用 DeepSeek Chat API；未配置密钥时不会发出网络请求。"""
    api_key = current_admin_api_key()
    if not api_key:
        flash('请先在 AI 洞察页填写你的 DeepSeek API Key。', 'danger')
        return redirect(url_for('ai_insights'))

    report = borrowing_report()
    prompt = (
        '你是校园图书馆运营分析助手。请仅基于下列统计，写 3 条简短、可执行的中文建议；'
        '不要编造数据。\n'
        f"近7天借阅 {report['last_7']} 次，前7天 {report['previous_7']} 次；"
        f"近30天借阅 {report['last_30']} 次，前30天 {report['previous_30']} 次；"
        f"当前在借 {report['active']} 本，逾期 {report['overdue']} 本，库存为0的图书 {report['out']} 本；"
        f"近30天最受欢迎图书：{report['lead_title']}。"
    )
    payload = json.dumps({
        'model': os.getenv('DEEPSEEK_MODEL', os.getenv('AI_MODEL', 'deepseek-chat')),
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.3,
    }).encode('utf-8')
    base = os.getenv('DEEPSEEK_API_BASE', 'https://api.deepseek.com').rstrip('/')
    req = urlrequest.Request(
        f'{base}/chat/completions', data=payload,
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}, method='POST',
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            content = json.loads(response.read().decode('utf-8'))['choices'][0]['message']['content']
        session['ai_generated_advice'] = content.strip()
    except (urlerror.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
        flash(f'AI 服务暂时不可用：{exc}', 'danger')
    return redirect(url_for('ai_insights'))


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
    app.run(debug=os.getenv('FLASK_DEBUG', '0') == '1')
