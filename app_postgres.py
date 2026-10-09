# app_postgres.py
import os
from datetime import datetime
from flask import Flask, jsonify, request, abort, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, '.env'))

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

# -------------------------
# DATABASE: use SQLite for local dev
# -------------------------
SQLITE_PATH = os.path.join(BASE_DIR, 'restaurant.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{SQLITE_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)  # optional for dev

# -------------------------
# MODELS
# -------------------------
class Branch(db.Model):
    __tablename__ = 'branch'
    branch_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255))

# mapping menu_item -> ingredient requirement
class Ingredient(db.Model):
    __tablename__ = 'ingredient'
    ingredient_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(50), default='unit')  # e.g., gram, piece

class MenuItemIngredient(db.Model):
    __tablename__ = 'menu_item_ingredient'
    id = db.Column(db.Integer, primary_key=True)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.menu_item_id'))
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.ingredient_id'))
    qty_needed = db.Column(db.Float, nullable=False)

class Inventory(db.Model):
    __tablename__ = 'inventory'
    inventory_id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.branch_id'))
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.ingredient_id'))
    qty = db.Column(db.Float, default=0.0)

class Staff(db.Model):
    __tablename__ = 'staff'
    staff_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50))
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)  # hash in production

class RestTable(db.Model):
    __tablename__ = 'rest_table'
    table_id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer)
    location = db.Column(db.String(255))

class Customer(db.Model):
    __tablename__ = 'customer'
    customer_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    note = db.Column(db.Text)

class MenuItem(db.Model):
    __tablename__ = 'menu_item'
    menu_item_id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.branch_id'), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Numeric(10,2), nullable=False)
    category = db.Column(db.String(100))
    available = db.Column(db.Boolean, default=True)
    image = db.Column(db.String(512))

class Order(db.Model):
    __tablename__ = 'orders'
    order_id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.branch_id'), nullable=True)
    table_id = db.Column(db.Integer, db.ForeignKey('rest_table.table_id'), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('staff.staff_id'), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.customer_id'), nullable=True)
    order_time = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50))
    total_amount = db.Column(db.Numeric(10,2), default=0)
    items = db.relationship('OrderItem', backref='order', cascade='all, delete-orphan')

class Payment(db.Model):
    __tablename__ = 'payment'
    payment_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'))
    amount = db.Column(db.Numeric(10,2))
    method = db.Column(db.String(50))
    paid_at = db.Column(db.DateTime)
    processed_by = db.Column(db.Integer, db.ForeignKey('staff.staff_id'))

class OrderItem(db.Model):
    __tablename__ = 'order_item'
    order_item_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.order_id'))
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.menu_item_id'))
    quantity = db.Column(db.Integer, default=1, nullable=False)
    note = db.Column(db.Text)
    status = db.Column(db.String(50))
    line_price = db.Column(db.Numeric(10,2))

class OrderItemHistory(db.Model):
    __tablename__ = 'order_item_history'
    history_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_item.order_item_id'))
    prev_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50))
    changed_at = db.Column(db.DateTime)
    changed_by = db.Column(db.Integer)

# -------------------------
# Helpers / serializers
# -------------------------
def menu_item_to_dict(m: MenuItem):
    return {
        "id": m.menu_item_id,
        "name": m.name,
        "desc": m.description or "",
        "price": float(m.price),
        "image": m.image or "/static/no-image.png",
        "available": bool(m.available),
        "category": m.category
    }

def order_to_dict(o: Order):
    return {
        "order_id": o.order_id,
        "table_id": o.table_id,
        "created_by": o.created_by,
        "customer_id": o.customer_id,
        "order_time": o.order_time.isoformat() if o.order_time else None,
        "status": o.status,
        "total_amount": float(o.total_amount or 0),
        "items": [
            {
                "order_item_id": it.order_item_id,
                "order_id": it.order_id,
                "menu_item_id": it.menu_item_id,
                "name": MenuItem.query.get(it.menu_item_id).name if MenuItem.query.get(it.menu_item_id) else None,
                "quantity": it.quantity,
                "price": float(it.line_price or 0),
                "status": it.status,
                "note": it.note
            } for it in o.items
        ]
    }

# -------------------------
# Serve frontend (static)
# -------------------------
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    static_dir = os.path.join(BASE_DIR, 'static')
    if path != "" and os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)
    index_path = os.path.join(static_dir, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(static_dir, 'index.html')
    return "Backend is running. Put frontend files in ./static/"

# -------------------------
# API endpoints
# -------------------------
@app.route('/api/menu-items', methods=['GET'])
def get_menu_items():
    category = request.args.get('category')
    branch_id = request.args.get('branch_id', type=int)
    q = MenuItem.query
    if branch_id:
        q = q.filter_by(branch_id=branch_id)
    if category:
        q = q.filter_by(category=category)
    items = q.all()
    return jsonify([menu_item_to_dict(m) for m in items])


@app.route('/api/menu-items/<int:item_id>', methods=['GET','PATCH'])
def menu_item_detail(item_id):
    m = MenuItem.query.get_or_404(item_id)
    if request.method == 'GET':
        return jsonify(menu_item_to_dict(m))
    data = request.get_json() or {}
    if 'available' in data:
        m.available = bool(data['available'])
    if 'price' in data:
        m.price = data['price']
    db.session.commit()
    return jsonify(menu_item_to_dict(m))

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.get_json() or {}
    branch_id = data.get('branch_id')
    if branch_id is None or not Branch.query.get(branch_id):
        return jsonify({"error":"branch not found"}), 400
    table_id = data.get('table_id')
    # optional: check table belongs to branch (if you model that)
    o = Order(branch_id=branch_id, table_id=table_id, created_by=data.get('created_by'),
              order_time=datetime.utcnow(), status='OPEN', total_amount=0)
    db.session.add(o)
    db.session.commit()
    return jsonify(order_to_dict(o)), 201


@app.route('/api/orders/active', methods=['GET'])
def get_active_order():
    table_id = request.args.get('table_id', type=int)
    if table_id is None:
        return jsonify(None)
    o = Order.query.filter(Order.table_id==table_id, Order.status.in_(['OPEN','SENT','PREPARING'])).first()
    if not o:
        return jsonify(None)
    return jsonify(order_to_dict(o))

@app.route('/api/orders/<int:order_id>', methods=['GET', 'PUT'])
def order_detail(order_id):
    o = Order.query.get_or_404(order_id)

    if request.method == 'GET':
        return jsonify(order_to_dict(o))

    # PUT
    data = request.get_json() or {}

    if 'status' in data:
        o.status = data['status']

        # Khi gửi xuống bếp
        if data['status'] == 'SENT':
            for it in o.items:
                # chỉ đổi những món CHƯA gửi
                if it.status in ('NOT_SENT', 'PENDING'):
                    it.status = 'WAITING'

    db.session.commit()
    return jsonify(order_to_dict(o))


@app.route('/api/orders/<int:order_id>/items', methods=['POST','GET'])
def order_items_route(order_id):
    o = Order.query.get_or_404(order_id)
    if request.method == 'GET':
        return jsonify([{
            "order_item_id": it.order_item_id,
            "order_id": it.order_id,
            "menu_item_id": it.menu_item_id,
            "quantity": it.quantity,
            "note": it.note,
            "status": it.status,
            "line_price": float(it.line_price or 0)
        } for it in o.items])

    # POST: thêm item vào order
    data = request.get_json() or {}
    menu_item_id = data.get('menu_item_id')
    qty = int(data.get('quantity', 1))
    note = data.get('note', '')

    m = MenuItem.query.get(menu_item_id)
    if not m:
        return jsonify({"error":"menu item not found"}), 400

    # đảm bảo menu item thuộc cùng chi nhánh với order (nếu order có branch)
    if o.branch_id and m.branch_id and o.branch_id != m.branch_id:
        return jsonify({"error":"menu item not available in this branch"}), 400

    # tạo order_item: mặc định NOT_SENT (chưa gửi xuống bếp)
    oi = OrderItem(
        order_id=o.order_id,
        menu_item_id=menu_item_id,
        quantity=qty,
        note=note,
        status='NOT_SENT',
        line_price=m.price
    )
    db.session.add(oi)

    # cập nhật tổng tiền order
    o.total_amount = float(o.total_amount or 0) + float(m.price) * qty

    db.session.commit()

    return jsonify({
        "order_item_id": oi.order_item_id,
        "order_id": oi.order_id,
        "menu_item_id": oi.menu_item_id,
        "quantity": oi.quantity,
        "note": oi.note,
        "status": oi.status,
        "line_price": float(oi.line_price)
    }), 201



@app.route('/api/kitchen/items', methods=['GET'])
def kitchen_items():
    status = request.args.get('status')
    q = OrderItem.query
    if status:
        q = q.filter_by(status=status)
    else:
        # default: trả các món đã gửi xuống bếp (WAITING, PREPARING), không trả NOT_SENT
        q = q.filter(OrderItem.status.in_(["WAITING","PREPARING"]))
    items = q.all()
    result = []
    for it in items:
        mi = MenuItem.query.get(it.menu_item_id)
        result.append({
            "order_item_id": it.order_item_id,
            "order_id": it.order_id,
            "name": mi.name if mi else None,
            "quantity": it.quantity,
            "note": it.note,
            "status": it.status
        })
    return jsonify(result)


@app.route('/api/kitchen/items/<int:order_item_id>/status', methods=['PUT'])
def kitchen_update_item(order_item_id):
    it = OrderItem.query.get_or_404(order_item_id)
    data = request.get_json() or {}
    new_status = data.get('status')
    if new_status not in ('PREPARING','FINISHED'):
        return jsonify({"error":"invalid status"}), 400
    prev = it.status
    it.status = new_status
    hist = OrderItemHistory(order_item_id=it.order_item_id, prev_status=prev, new_status=new_status,
                            changed_at=datetime.utcnow(), changed_by=data.get('changed_by'))
    db.session.add(hist)
    parent = Order.query.get(it.order_id)
    if parent:
        if all(x.status == 'FINISHED' for x in parent.items):
            parent.status = 'COMPLETED'
    db.session.commit()
    return jsonify({
        "order_item_id": it.order_item_id,
        "status": it.status
    })

@app.route('/api/payments', methods=['POST'])
def payments_route():
    data = request.get_json() or {}
    order_id = data.get('order_id')
    amount = data.get('amount')
    method = data.get('method')
    if not Order.query.get(order_id):
        return jsonify({"error":"order not found"}), 400
    p = Payment(order_id=order_id, amount=amount, method=method, paid_at=datetime.utcnow(), processed_by=data.get('processed_by'))
    db.session.add(p)
    o = Order.query.get(order_id)
    o.status = 'PAID'
    db.session.commit()
    return jsonify({
        "payment_id": p.payment_id,
        "order_id": p.order_id,
        "amount": float(p.amount),
        "method": p.method,
        "paid_at": p.paid_at.isoformat() + 'Z'
    }), 201

@app.route('/api/reports/history', methods=['GET'])
def reports_history():
    payments = Payment.query.all()
    total_revenue = sum(float(p.amount) for p in payments)
    total_orders = Order.query.count()
    return jsonify({
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "payments": [{
            "payment_id": p.payment_id, "order_id": p.order_id, "amount": float(p.amount), "paid_at": p.paid_at.isoformat() + 'Z'
        } for p in payments]
    })

@app.route('/api/tables/<int:table_id>/current-order', methods=['GET'])
def table_current_order(table_id):
    o = Order.query.filter(Order.table_id==table_id, Order.status.in_(['OPEN','SENT','PREPARING'])).first()
    if not o:
        return jsonify(None)
    return jsonify(order_to_dict(o))

# -------------------------
# DB init + seed
# -------------------------
def init_db(seed=True):
    with app.app_context():
        db.create_all()

        # -----------------------
        # Seed Branch
        # -----------------------
        if seed and Branch.query.count() == 0:
            branches = [
                Branch(branch_id=1, name="Chi nhánh Trung tâm", location="Quận 1"),
                Branch(branch_id=2, name="Chi nhánh Quận 7", location="Quận 7"),
            ]
            db.session.add_all(branches)
            db.session.commit()
            print("Seeded branches.")

        # -----------------------
        # Seed Menu Items (theo branch)
        # -----------------------
        if seed and MenuItem.query.count() == 0:
            m1 = MenuItem(
                name="Phở bò tái",
                description="Nước dùng thanh, thịt mềm.",
                price=45000,
                category="mains",
                available=True,
                image="/static/pho.png",
                branch_id=1
            )
            m2 = MenuItem(
                name="Cà phê sữa đá",
                description="Pha phin đậm vị.",
                price=25000,
                category="drinks",
                available=True,
                image="/static/cafe.png",
                branch_id=1
            )
            m3 = MenuItem(
                name="Gỏi cuốn tôm thịt",
                description="Tươi, cuốn có tôm, thịt.",
                price=30000,
                category="appetizer",
                available=True,
                image="/static/goicuon.png",
                branch_id=1
            )

            db.session.add_all([m1, m2, m3])
            db.session.commit()
            print("Seeded menu items.")

        # -----------------------
        # Seed RestTable
        # -----------------------
        if seed and RestTable.query.count() == 0:
            default_tables = [
                RestTable(table_id=1, table_number=1, location='Main'),
                RestTable(table_id=2, table_number=2, location='Main'),
                RestTable(table_id=3, table_number=3, location='Patio'),
                RestTable(table_id=4, table_number=4, location='Patio'),
                RestTable(table_id=5, table_number=5, location='VIP'),
            ]

            db.session.add_all(default_tables)
            db.session.commit()
            print("Seeded default rest tables.")




# -------------------------
# Run
# -------------------------
if __name__ == '__main__':
    init_db(seed=True)
    app.run(host='0.0.0.0', port=3000, debug=True)
