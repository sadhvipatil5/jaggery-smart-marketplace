from flask import Flask, render_template, request, redirect, url_for, jsonify,session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager,login_user, login_required, logout_user, current_user
from models import db, User, Product, Order,  WishlistItem,seed_data
from config import Config
import pandas as pd
from flask import session
from sklearn.metrics.pairwise import cosine_similarity
import random
from sklearn.tree import DecisionTreeClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LinearRegression
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestClassifier 
import numpy as np
from werkzeug.security import check_password_hash,generate_password_hash
import random  # For simple recommendation
from flask_migrate import Migrate
from datetime import datetime
from models import Address, Product, Order
from ml_recommendation import recommend_products
from ml_price_prediction import train_price_model
app = Flask(__name__,template_folder='templates', static_folder='static')
app.config.from_object(Config)
db.init_app(app)



# Initialize Flask-Migrate
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'
app.config['SECRET_KEY'] = 'mysecretkey123'

@app.route('/')
def index():
    products = Product.query.order_by(Product.id.desc()).limit(12).all()
    quality_predictions = predict_quality(products)

    return render_template(
        'index.html',
        products=products,
        quality_predictions=quality_predictions
    )

def update_dynamic_prices():
    month = datetime.now().month
    products = Product.query.all()

    for p in products:
        base_price = p.price  # your column must exist

        # Seasonal price logic 🌾
        if month in [12, 1, 2]:
            p.current_price = round(base_price * 0.9, 2)
        elif month in [3, 4, 5]:
            p.current_price = round(base_price * 1.2, 2)
        elif month in [6, 7, 8, 9]:
            p.current_price = round(base_price * 1.1, 2)
        else:
            p.current_price = round(base_price, 2)

    db.session.commit()

# ----------------------------
# 4️⃣ Auto-update before every request
# ----------------------------
@app.before_request
def before_request_func():
    dynamic_price_ai()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Seasonal price adjustment logic
def adjust_prices():
    import datetime
    month = datetime.datetime.now().month
    multiplier = 1.0
    if month in [12, 1, 2]:  # Winter: higher demand
        multiplier = 1.1
    elif month in [6, 7, 8]:  # Summer: lower demand
        multiplier = 0.9
    products = Product.query.all()
    for product in products:
        product.current_price = product.base_price * multiplier
    db.session.commit()


def get_product_recommendations(product_id):

    products = Product.query.all()

    data = []

    for p in products:
        data.append({
            "id": p.id,
            "price": p.price,
            "category": hash(p.category) % 100
        })

    df = pd.DataFrame(data)

    if df.empty:
        return []

    features = df[['price','category']]

    similarity = cosine_similarity(features)

    index = df.index[df['id']==product_id][0]

    scores = list(enumerate(similarity[index]))

    scores = sorted(scores, key=lambda x:x[1], reverse=True)

    recommended_ids = []

    for s in scores[1:5]:
        recommended_ids.append(int(df.iloc[s[0]]['id']))

    return recommended_ids


# -------------------------------
# 2️⃣ JAGGERY QUALITY PREDICTION
# -------------------------------

X_quality = np.array([
    [80,10,85],
    [70,12,80],
    [50,20,60],
    [40,25,50],
    [30,30,40]
])

y_quality = ["A","A","B","B","C"]

quality_model = DecisionTreeClassifier()

quality_model.fit(X_quality,y_quality)

def predict_jaggery_quality(color,moisture,hardness):

    result = quality_model.predict([[color,moisture,hardness]])

    return result[0]


# -------------------------------
# 3️⃣ Address
# -------------------------------
@app.route('/address/<int:product_id>', methods=['GET', 'POST'])
@login_required
def address(product_id):

    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':

        save_address = request.form.get('save_address')

        if save_address:
            new_address = Address(
                user_id=current_user.id,
                full_name=request.form['name'],
                phone=request.form['phone'],
                address_line=request.form['address'],
                city=request.form['city'],
                pincode=request.form['pincode']
            )
            db.session.add(new_address)

        db.session.commit()

        # 👉 Instead of creating order here
        # redirect to payment page
        return redirect(url_for('payment', product_id=product.id))

    saved_addresses = Address.query.filter_by(user_id=current_user.id).all()

    return render_template(
        'address.html',
        product=product,
        saved_addresses=saved_addresses
    )

@app.route('/payment/<int:product_id>', methods=['GET', 'POST'])
@login_required
def payment(product_id):

    product = Product.query.get_or_404(product_id)

    if request.method == 'POST':

        payment_mode = request.form.get('payment_mode')

        # ✅ Create order AFTER payment
        order = Order(
            user_id=current_user.id,
            product_id=product.id,
            quantity=1,
            total_price=product.current_price,
            status="Paid" if payment_mode != "COD" else "Pending"
        )

        db.session.add(order)
        db.session.commit()

        return redirect(url_for('order_success'))

    return render_template('payment.html', product=product)

@app.route('/edit-address/<int:address_id>', methods=['GET', 'POST'])
@login_required
def edit_address(address_id):

    address = Address.query.get_or_404(address_id)

    # सुरक्षा: user can edit only their address
    if address.user_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for('address', product_id=1))

    if request.method == 'POST':
        address.full_name = request.form['name']
        address.phone = request.form['phone']
        address.address_line = request.form['address']
        address.city = request.form['city']
        address.pincode = request.form['pincode']

        db.session.commit()

        flash("✅ Address updated successfully!", "success")
        return redirect(url_for('address', product_id=1))

    return render_template('edit_address.html', address=address)

@app.route('/delete-address/<int:address_id>', methods=['POST'])
@login_required
def delete_address(address_id):

    address = Address.query.get_or_404(address_id)

    # सुरक्षा: user can delete only their own address
    if address.user_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for('address'))

    db.session.delete(address)
    db.session.commit()

    flash("🗑️ Address deleted successfully!", "success")
    return redirect(url_for('my_orders'))

@app.route('/account')
@login_required
def account():
    return render_template('account.html')


@app.route('/my-orders')
@login_required
def my_orders():
    orders = Order.query.filter(
        Order.user_id == current_user.id,
        Order.status != "Cancelled"   # ✅ hide cancelled orders
    ).all()

    return render_template('orders.html', orders=orders)
@app.route('/track-order/<int:order_id>')
@login_required
def track_order(order_id):
    order = Order.query.get_or_404(order_id)

    # सुरक्षा: user should only see their own order
    if order.user_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for('my_orders'))

    return render_template('track_order.html', order=order)

@app.route('/cancel-order/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    order = Order.query.get_or_404(order_id)

    # 🔒 security
    if order.user_id != current_user.id:
        flash("Unauthorized!", "danger")
        return redirect(url_for('my_orders'))

    # ❌ only allow if pending
    if order.status != "Pending":
        flash("Cannot cancel now!", "warning")
        return redirect(url_for('track_order', order_id=order.id))

    # 🔴 HERE YOU ADD DELETE
    db.session.delete(order)
    db.session.commit()

    flash("Order deleted!", "success")
    return redirect(url_for('my_orders'))  
# -------------------------------
# 4️⃣ DEMAND PREDICTION
# -------------------------------
# =========================
# 🤖 AI DEMAND PREDICTION FUNCTION
# =========================
def predict_seasonal_demand():

    orders = Order.query.all()

    if not orders:
        return {}

    data = []

    for o in orders:

        if not o.created_at or o.quantity is None:
            continue

        product = Product.query.get(o.product_id)

        data.append({
            "product_id": o.product_id,
            "month": o.created_at.month,
            "quantity": o.quantity,
            "price": product.current_price,
            "stock": product.stock
        })

    df = pd.DataFrame(data)

    if df.empty:
        return {}

    # Aggregate monthly demand per product
    grouped = df.groupby(["product_id", "month"]).agg({
        "quantity": "sum",
        "price": "mean",
        "stock": "mean"
    }).reset_index()

    X = grouped[["month", "price", "stock"]]
    y = grouped["quantity"]

    # 🔥 Stronger model than Linear Regression
    from sklearn.ensemble import RandomForestRegressor

    model = RandomForestRegressor(n_estimators=100)
    model.fit(X, y)

    predictions = {}

    current_month = datetime.now().month

    for p in Product.query.all():

        pred = model.predict([[current_month, p.current_price, p.stock]])
        predictions[p.id] = max(0, int(pred[0]))

    return predictions

def dynamic_price_ai():

    demand_predictions = predict_seasonal_demand()
    products = Product.query.all()

    for p in products:

        demand = demand_predictions.get(p.id, 0)

        # 🔥 Smart pricing logic
        if demand > 15:
            # High demand → increase price
            p.current_price = round(p.price * 1.25, 2)

        elif demand > 8:
            # Medium demand
            p.current_price = round(p.price * 1.1, 2)

        elif demand < 3:
            # Low demand → discount
            p.current_price = round(p.price * 0.85, 2)

        else:
            p.current_price = round(p.price, 2)

    db.session.commit()

from sklearn.ensemble import RandomForestClassifier
import pandas as pd
def predict_quality(products):

    if not products:
        return {}

    predictions = {}

    for p in products:

        total_orders = Order.query.filter_by(product_id=p.id, status="Paid").count()
        price = p.current_price
        stock = p.stock

        # ✅ FINAL LOGIC (consistent everywhere)
        if price >= 120 and total_orders >= 5 and stock >= 20:
            quality = "High"

        elif price >= 80 and total_orders >= 2:
            quality = "Moderate"

        else:
            quality = "Low"

        predictions[p.id] = quality

    return predictions

# ---------- Login Route ----------
#from flask import session

from flask_login import login_user

@app.route('/login', methods=['GET','POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):

            login_user(user)

            # ✅ ADD THIS
            next_page = request.args.get('next')

            return redirect(next_page) if next_page else redirect(url_for('index'))

        else:
            return "Invalid email or password"

    return render_template('login.html')


# ---------- Register Route ----------
from flask import request, redirect, url_for, render_template
from models import User, db

from flask import flash

@app.route('/register', methods=['GET','POST'])
def register():

    if request.method == 'POST':

        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            flash("⚠️ User already exists. Please login.", "danger")
            return redirect(url_for('login'))

        # Create new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash("✅ Registration successful! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

from flask_login import login_user

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        admin = User.query.filter_by(email=email, is_admin=True).first()

        if admin and admin.check_password(password):
            login_user(admin)   # ✅ IMPORTANT
            flash('✅ Admin logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))

        else:
            flash('❌ Invalid admin credentials', 'danger')

    return render_template('admin_login.html')
#@app.route('/admin_dashboard')
#def admin_dashboard():
 #   if 'admin_logged_in' not in session:
  #      flash('Please login as admin first.', 'warning')
   #     return redirect(url_for('admin_login'))
    
    # ✅ Fetch only actual products from database
    #products = Product.query.all()
    
    #return render_template('admin_dashboard.html', products=products)

from flask_login import login_required, current_user


@app.route('/admin_dashboard')
@login_required
def admin_dashboard():

    if not current_user.is_admin:
        flash("Access denied!", "danger")
        return redirect(url_for('index'))

    products = Product.query.order_by(Product.id.asc()).all()
    orders = Order.query.all()
    total_products = len(products)
    total_orders = len(orders)
    total_revenue = sum(o.total_price or 0 for o in orders)

    seasonal_demand = predict_seasonal_demand()
    quality_predictions = predict_quality(products)
    predicted_prices = {}

    if orders:
        df = pd.DataFrame([
            {"stock": o.product.stock, "price": o.total_price}
            for o in orders if o.total_price
        ])

        if not df.empty:
            X = df[["stock"]]
            y = df["price"]

            model = LinearRegression()
            model.fit(X, y)

            for p in products:
                predicted = model.predict(pd.DataFrame([[p.stock]], columns=["stock"]))
                predicted_prices[p.id] = round(predicted[0], 2)
    else:
        for p in products:
            predicted_prices[p.id] = p.current_price

    return render_template(
        "admin_dashboard.html",
        products=products,
        seasonal_demand=seasonal_demand,
        quality_predictions=quality_predictions,
        predicted_prices=predicted_prices,
        total_products=total_products,
        total_orders=total_orders,
        total_revenue=total_revenue
    )


from sqlalchemy.exc import IntegrityError

# ✅ Add Product
from sqlalchemy.exc import IntegrityError

@app.route("/admin/add_product", methods=["POST"])
@login_required
def add_product():

    if not current_user.is_admin:
        flash("Access denied!", "danger")
        return redirect(url_for("index"))

    try:
        print(request.form)  # DEBUG

        name = request.form.get("name")
        description = request.form.get("description")
        price = float(request.form.get("price", 0))
        current_price = float(request.form.get("current_price", 0))
        category = request.form.get("category")
        stock = int(request.form.get("stock", 0))
        image_url = request.form.get("image_url") or "https://via.placeholder.com/300x200"

        new_product = Product(
            name=name,
            description=description,
            price=price,
            current_price=current_price,
            category=category,
            stock=stock,
            image_url=image_url
        )

        db.session.add(new_product)
        db.session.commit()

        print("✅ Product saved:", new_product.id)

        flash("✅ Product added successfully!", "success")

    except Exception as e:
        db.session.rollback()
        print("❌ ERROR:", e)
        flash("❌ Error adding product!", "danger")

    return redirect(url_for("admin_dashboard"))

# ✅ Update Product
@app.route("/admin/edit_product/<int:product_id>", methods=["POST"])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        flash("Access denied!", "danger")
        return redirect(url_for("index"))

    product = Product.query.get_or_404(product_id)
    product.name = request.form["name"]
    product.description = request.form["description"]
    product.price = float(request.form["price"])
    product.current_price = float(request.form["current_price"])
    product.category = request.form["category"]
    product.stock = int(request.form["stock"])
    product.image_url = request.form.get("image_url") or product.image_url

    db.session.commit()
    flash("✏️ Product updated successfully!", "success")
    return redirect(url_for("admin_dashboard"))

# ✅ Delete Product
@app.route('/admin/delete_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get(product_id)
    if product:
        db.session.delete(product)
        db.session.commit()
        flash("Product deleted successfully!", "success")
    else:
        flash("Product not found!", "danger")
    return redirect(url_for('admin_dashboard'))
# ===============================
# 🧩 ADMIN ORDER MANAGEMENT
# ===============================

# ✅ Admin view all orders
@app.route('/admin/orders')
def admin_orders():
    if 'admin_logged_in' not in session:
        flash('Please login as admin first.', 'warning')
        return redirect(url_for('admin_login'))

    # Fetch all orders with user and product info
    orders = Order.query.all()
    return render_template('admin_orders.html', orders=orders)


# ✅ Update Order Status
@app.route('/admin/update_order_status/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    if 'admin_logged_in' not in session:
        flash('Please login as admin first.', 'warning')
        return redirect(url_for('admin_login'))
    
    order = Order.query.get_or_404(order_id)
    new_status = request.form['status']
    order.status = new_status
    db.session.commit()
    flash(f"✅ Order #{order.id} status updated to {new_status}", 'success')
    return redirect(url_for('admin_orders'))


# ✅ Delete Order
@app.route('/admin/delete_order/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    if 'admin_logged_in' not in session:
        flash('Please login as admin first.', 'warning')
        return redirect(url_for('admin_login'))
    
    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()
    flash(f"🗑️ Order #{order.id} deleted successfully!", 'success')
    return redirect(url_for('admin_orders'))

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    order = Order.query.filter_by(user_id=current_user.id, product_id=product.id, status='Pending').first()

    if order:
        order.quantity += 1
        order.total_price = order.quantity * product.current_price
    else:
        order = Order(
            user_id=current_user.id,
            product_id=product.id,
            quantity=1,
            total_price=product.current_price,
            status='Pending'
        )
        db.session.add(order)

    db.session.commit()
    flash(f"{product.name} added to your cart!", "success")
    return redirect(url_for('index'))


@app.route('/cart')
@login_required
def cart():
    orders = Order.query.filter_by(user_id=current_user.id, status='Pending').all()
    total = 0
    for order in orders:
        total += order.product.price * order.quantity

    return render_template('cart.html', orders=orders, total=total)

@app.route('/cart/increase/<int:order_id>', methods=['POST'])
@login_required
def increase_quantity(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id == current_user.id and order.status == 'Pending':
        order.quantity += 1
        order.total_price = order.quantity * order.product.current_price
        db.session.commit()
    return redirect(url_for('checkout'))


@app.route('/cart/decrease/<int:order_id>', methods=['POST'])
@login_required
def decrease_quantity(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id == current_user.id and order.status == 'Pending':
        if order.quantity > 1:
            order.quantity -= 1
            order.total_price = order.quantity * order.product.current_price
        else:
            db.session.delete(order)
        db.session.commit()
    return redirect(url_for('checkout'))

# Wishlist page
# ✅ View wishlist
@app.route('/wishlist')
@login_required
def wishlist():
    wishlist_items = WishlistItem.query.filter_by(user_id=current_user.id).all()
    return render_template('wishlist.html', wishlist_items=wishlist_items)


# ✅ Add product to wishlist
@app.route('/add_to_wishlist/<int:product_id>', methods=['POST'])
@login_required
def add_to_wishlist(product_id):
    existing_item = WishlistItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if existing_item:
        flash('Already in wishlist!', 'info')
    else:
        new_item = WishlistItem(user_id=current_user.id, product_id=product_id)
        db.session.add(new_item)
        db.session.commit()
        flash('Added to wishlist ❤️', 'success')

    return redirect(url_for('index'))


# ✅ Remove from wishlist (optional but useful)
@app.route('/remove_from_wishlist/<int:item_id>', methods=['POST'])
@login_required
def remove_from_wishlist(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    if item.user_id == current_user.id:
        db.session.delete(item)
        db.session.commit()
        flash('Removed from wishlist 🗑️', 'success')
    return redirect(url_for('wishlist'))



@app.route("/product/<int:product_id>")
def product_detail(product_id):

    product = Product.query.get_or_404(product_id)

    recommendations = recommend_products(product_id)

    return render_template(
        "product_detail.html",
        product=product,
        recommendations=recommendations
    )
#def product_detail(product_id):
 
 #   product = Product.query.get_or_404(product_id)
    # Fetch similar products from the same category (excluding current one)
    #similar_products = Product.query.filter(
     #   Product.category == product.category,
      #  Product.id != product.id
    #).limit(4).all()
    #return render_template('product_detail.html', product=product, similar_products=similar_products)*/
@app.route('/buy-now/<int:product_id>', methods=['POST'])
@login_required
def buy_now(product_id):
    product = Product.query.get_or_404(product_id)

    quantity = 1  # ✅ default quantity
    total_price = product.price * quantity  # ✅ calculate price

    order = Order(
        user_id=current_user.id,
        product_id=product.id,
        quantity=quantity,
        total_price=total_price,
        status="Pending"
    )

    db.session.add(order)
    db.session.commit()

    
    return redirect(url_for('address',product_id=product_id))
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    # Fetch all pending orders of the user
    orders = Order.query.filter_by(user_id=current_user.id, status='Pending').all()

    if not orders:
        flash("Your cart is empty.", "info")
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Simulate payment success
        for order in orders:
            order.status = 'Paid'
        db.session.commit()

        flash("✅ Payment successful! Your order has been placed.", "success")
        return redirect(url_for('order_success'))

    total_price = sum(order.total_price for order in orders)

    return render_template('checkout.html', orders=orders, total_price=total_price)

@app.route('/order-success')
@login_required
def order_success():
    orders = Order.query.filter_by(
        user_id=current_user.id
    ).order_by(Order.id.desc()).all()

    return render_template('order_success.html', orders=orders)


# =====================================================
# 🤖 AI API ROUTES
# =====================================================

# Jaggery Quality Prediction
@app.route('/jaggery_quality')
def jaggery_quality():
    products = Product.query.all()

    quality_predictions = predict_quality(products)

    return render_template(
        'jaggery_quality.html',
        products=products,
        quality_predictions=quality_predictions
    )

@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.json['message']
    reply = get_response(user_input)
    return {"reply": reply}


# Demand Prediction
@app.route('/ai/demand')
def ai_demand():

    result=predict_demand()

    return jsonify(result)


# ---------- Logout Route ----------
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    if request.method == 'POST':
        adjust_prices()
        flash('Prices updated seasonally!')
    products = Product.query.all()
    return render_template('admin.html', products=products)



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        #seed_data()  # Run once to add sample data
    app.run(debug=True)