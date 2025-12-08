from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
import time
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader
import os
from datetime import datetime

from flask_migrate import Migrate   # ✅ Added

# ================== LOAD ENVIRONMENT VARIABLES ==================
load_dotenv()

app = Flask(__name__)
CORS(app)

# ================== CONFIG ==================
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or "supersecretkey"

# ================== DATABASE CONFIG ==================
DATABASE_URL = os.getenv("DATABASE_URL")

# Fix for old Railway connection strings
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://")

# Validate PostgreSQL URL
if not DATABASE_URL or "://" not in DATABASE_URL or "postgresql" not in DATABASE_URL:
    print("⚠️ No valid PostgreSQL URL found → Using SQLite local.db")
    DATABASE_URL = "sqlite:///local.db"

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# ================== CLOUDINARY CONFIG ==================
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# ================== MODELS ==================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(50), unique=True)   # 🔥 MAKE PHONE UNIQUE
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    is_blocked = db.Column(db.Boolean, default=False)   # ⭐ NEW

from sqlalchemy.dialects.postgresql import JSON

class Listing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price_per_day = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100))

    images = db.Column(JSON, default=[])

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    is_rented = db.Column(db.Boolean, default=False)

    user = db.relationship("User", backref="listings")
    
    # ⭐ NEW LOCATION FIELDS
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    city = db.Column(db.String(100))
    area = db.Column(db.String(100))
    address = db.Column(db.String(255))

class AppBanner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)
    bg_color = db.Column(db.String(30), default="#EDE7F6")   # Light purple
    text_color = db.Column(db.String(30), default="#5A2DFF") # Deep purple
    active = db.Column(db.Boolean, default=True)

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # 🔥 Rename user1 → user1_id
    user1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # 🔥 Rename user2 → user2_id
    user2_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    listing_id = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class RentalRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # -------------------------
    # Basic Foreign Keys
    # -------------------------
    listing_id = db.Column(db.Integer, db.ForeignKey("listing.id"))
    renter_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    # Relationships
    listing = db.relationship("Listing", backref="rental_requests")
    renter = db.relationship("User", foreign_keys=[renter_id])
    owner = db.relationship("User", foreign_keys=[owner_id])

    chat_id = db.Column(db.Integer, db.ForeignKey("chat.id"), nullable=True)
    chat = db.relationship("Chat", backref="rental_request", lazy=True)

    # -------------------------
    # Rental Details
    # -------------------------
    start_date = db.Column(db.String(50))
    end_date = db.Column(db.String(50))
    total_days = db.Column(db.Integer)
    total_price = db.Column(db.Float)

    pickup_method = db.Column(db.String(50))  # self_pick / rider_delivery
    address = db.Column(db.String(300))       # old field (optional)
    note = db.Column(db.Text)

    # -------------------------
    # Renter → Rider Delivery Info
    # -------------------------
    renter_delivery_address = db.Column(db.String(500))
    renter_delivery_contact = db.Column(db.String(50))
    renter_delivery_note = db.Column(db.String(300))

    # -------------------------
    # Owner → Self Pickup Info
    # -------------------------
    owner_pickup_address = db.Column(db.String(500))
    owner_pickup_contact = db.Column(db.String(50))
    owner_pickup_note = db.Column(db.String(300))

    # -------------------------
    # Owner → Payment Info (For Rider Delivery)
    # -------------------------
    owner_payment_bank = db.Column(db.String(100))
    owner_payment_title = db.Column(db.String(150))
    owner_payment_account = db.Column(db.String(100))
    owner_payment_note = db.Column(db.String(300))

    # -------------------------
    # SAFE SYSTEM
    # -------------------------
    cnic_image = db.Column(db.String(300))
    selfie_image = db.Column(db.String(300))
    renter_verified = db.Column(db.Boolean, default=False)
    safety_rules_agreed = db.Column(db.Boolean, default=False)
    agreement_signed_at = db.Column(db.DateTime)

    # -------------------------
    # Status
    # -------------------------
    status = db.Column(db.String(20), default="pending")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey("chat.id"))
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    text = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Add this column in Message model:
    audio_url = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), default="sent")  

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    platform_name = db.Column(db.String(200), default="Rent Anything")
    logo_url = db.Column(db.String(500), default="")

# ================== API ROUTES ==================

@app.route("/api/signup", methods=["POST"])
def api_signup():
    data = request.get_json() or {}

    name = data.get("name")
    email = (data.get("email") or "").strip().lower()   # 🔥 normalize email
    phone = (data.get("phone") or "").strip()
    password = data.get("password")

    # 🔥 Validate all fields
    if not all([name, email, phone, password]):
        return jsonify({"success": False, "error": "Missing fields"}), 400

    # 🔥 Check if email already exists (case-insensitive)
    existing_email = User.query.filter(
        db.func.lower(User.email) == email
    ).first()
    if existing_email:
        return jsonify({"success": False, "error": "Email already registered"}), 400

    # 🔥 Check if phone already exists
    existing_phone = User.query.filter_by(phone=phone).first()
    if existing_phone:
        return jsonify({"success": False, "error": "Phone number already registered"}), 400

    # 🔥 Hash password
    hashed = generate_password_hash(password)

    # 🔥 Create user
    user = User(name=name, email=email, phone=phone, password=hashed)
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Signup successful",
        "user_id": user.id
    })

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password")

    if not email or not password:
        return jsonify({"success": False, "error": "Missing credentials"}), 400

    # Case-insensitive search
    user = User.query.filter(db.func.lower(User.email) == email).first()

    if not user:
        return jsonify({"success": False, "error": "Invalid login"}), 401

    # 🚫 BLOCK CHECK
    if user.is_blocked:
        return jsonify({
            "success": False,
            "error": "Your account has been blocked by admin."
        }), 403

    # Password check
    if not check_password_hash(user.password, password):
        return jsonify({"success": False, "error": "Invalid login"}), 401

    # SUCCESS
    return jsonify({
        "success": True,
        "message": "Login successful",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "is_blocked": user.is_blocked     # optional but helpful for Flutter
        }
    }), 200

# ================== SETTINGS API ==================

@app.route("/api/settings", methods=["GET"])
def get_settings():
    s = Setting.query.first()
    if not s:
        s = Setting()
        db.session.add(s)
        db.session.commit()

    return jsonify({
        "platform_name": s.platform_name or "Rent Anything",
        "logo_url": s.logo_url or ""
    })

@app.route("/api/profile/<int:user_id>")
def get_profile(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found"})

    return jsonify({
        "success": True,
        "name": user.name,
        "email": user.email,
        "phone": user.phone
    })

# ================== ADMIN SECTION ==================

@app.route("/admin")
def admin_dashboard():
    users = User.query.order_by(User.created_at.desc()).all()
    settings = Setting.query.first()
    return render_template(
        "admin_dashboard.html",
        users=users,
        settings=settings
    )


@app.route("/admin/update-settings", methods=["POST"])
def update_settings():
    platform_name = request.form.get("platform_name")
    logo = request.files.get("logo")

    s = Setting.query.first()
    if not s:
        s = Setting()
        db.session.add(s)

    if logo:
        upload_result = cloudinary.uploader.upload(
            logo,
            folder="rent_anything_logo"
        )
        s.logo_url = upload_result["secure_url"]

    if platform_name:
        s.platform_name = platform_name

    db.session.commit()

    return redirect(url_for("admin_dashboard"))

@app.route("/api/listings/add", methods=["POST"])
def add_listing():
    data = request.get_json() or {}

    user_id = data.get("user_id")
    title = data.get("title")
    description = data.get("description")
    price = data.get("price_per_day")
    category = data.get("category")
    images = data.get("images", [])  # ⬅ MULTIPLE IMAGES

    if not all([user_id, title, description, price]):
        return jsonify({"success": False, "error": "Missing fields"}), 400

    listing = Listing(
        user_id=user_id,
        title=title,
        description=description,
        price_per_day=price,
        category=category,
        images=images
    )

    db.session.add(listing)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Listing added successfully",
        "listing_id": listing.id
    })

@app.route("/api/listings", methods=["GET"])
def get_listings():
    listings = Listing.query.filter_by(is_rented=False).order_by(Listing.created_at.desc()).all()

    return jsonify([
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "price_per_day": item.price_per_day,
            "category": item.category,
            "images": item.images or [],
            "city": item.city,
            "area": item.area,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "owner_id": item.user_id,
            "owner_name": item.user.name if item.user else None
        }
        for item in listings
    ])

@app.route("/api/listings/<int:listing_id>", methods=["GET"])
def get_listing(listing_id):
    listing = Listing.query.get(listing_id)
    if not listing:
        return jsonify({"success": False, "error": "Listing not found"}), 404

    return jsonify({
        "success": True,
        "listing": {
            "id": listing.id,
            "title": listing.title,
            "description": listing.description,
            "price_per_day": listing.price_per_day,
            "category": listing.category,
            "images": listing.images or [],
            "created_at": listing.created_at.isoformat() if listing.created_at else None,
            "is_rented": listing.is_rented,
            "user": {
                "id": listing.user.id,
                "name": listing.user.name,
            }
        }
    })

@app.route("/api/my_listings/<int:user_id>", methods=["GET"])
def get_my_listings(user_id):
    listings = Listing.query.filter_by(user_id=user_id).all()

    return jsonify({
        "success": True,
        "listings": [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "price_per_day": item.price_per_day,
                "category": item.category,
                "images": item.images or [],
                "created_at": item.created_at
            }
            for item in listings
        ]
    })

@app.route("/api/listings/delete/<int:listing_id>", methods=["DELETE"])
def delete_listing(listing_id):
    listing = Listing.query.get(listing_id)
    if not listing:
        return jsonify({"success": False, "error": "Listing not found"})

    db.session.delete(listing)
    db.session.commit()

    return jsonify({"success": True})

# ============================================================
#  SEND MESSAGE (TEXT + AUDIO)
# ============================================================
@app.route("/api/chat/send", methods=["POST"])
def send_message():
    # -----------------------------
    # TEXT MESSAGE (JSON)
    # -----------------------------
    if request.is_json:
        data = request.get_json()
        chat_id = data.get("chat_id")
        sender_id = data.get("sender_id")
        text = data.get("text", "")

        if not all([chat_id, sender_id]):
            return jsonify({"success": False, "error": "Missing fields"})

        msg = Message(
            chat_id=chat_id,
            sender_id=sender_id,
            text=text,
            status="sent",
            is_read=False
        )
        db.session.add(msg)
        db.session.commit()

        return jsonify({"success": True})

    # -----------------------------
    # AUDIO MESSAGE (Multipart)
    # -----------------------------
    data = request.form
    chat_id = data.get("chat_id")
    sender_id = data.get("sender_id")
    text = data.get("text", "")

    audio_file = request.files.get("audio")

    if not all([chat_id, sender_id]):
        return jsonify({"success": False, "error": "Missing fields"})

    audio_url = None

    # Upload audio to Cloudinary
    if audio_file:
        try:
            upload_result = cloudinary.uploader.upload(
                audio_file,
                resource_type="video",       # Cloudinary treats audio as video
                folder="rentnow_audio",
                public_id=f"voice_{sender_id}_{int(time.time())}"
            )
            audio_url = upload_result.get("secure_url")
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    msg = Message(
        chat_id=chat_id,
        sender_id=sender_id,
        text=text,
        audio_url=audio_url,
        status="sent",
        is_read=False
    )

    db.session.add(msg)
    db.session.commit()

    return jsonify({"success": True, "audio_url": audio_url})

@app.route("/api/chat/messages/<int:chat_id>")
def get_messages(chat_id):
    messages = Message.query.filter_by(chat_id=chat_id)\
                .order_by(Message.created_at.asc()).all()

    user_id = request.args.get("user_id", type=int)

    # -----------------------------
    # UPDATE "sent" → "delivered"
    # -----------------------------
    if user_id:
        changed = False
        for m in messages:
            if m.sender_id != user_id and m.status == "sent":
                m.status = "delivered"
                changed = True
        if changed:
            db.session.commit()

    return jsonify({
        "success": True,
        "messages": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "text": m.text,
                "audio_url": m.audio_url,
                "status": m.status,
                "is_read": m.is_read,
                "time": m.created_at.isoformat()
            }
            for m in messages
        ]
    })

@app.route("/api/chat/list/<int:user_id>")
def chat_list(user_id):
    chats = Chat.query.filter(
        (Chat.user1_id == user_id) | (Chat.user2_id == user_id)
    ).order_by(Chat.created_at.desc()).all()

    data = []

    for c in chats:
        other_id = c.user2_id if c.user1_id == user_id else c.user1_id
        other = User.query.get(other_id)

        last_msg = Message.query.filter_by(chat_id=c.id)\
                    .order_by(Message.created_at.desc()).first()

        last_message = last_msg.text if last_msg else ""
        last_status = last_msg.status if last_msg else None

        unread_count = Message.query.filter(
            Message.chat_id == c.id,
            Message.sender_id != user_id,
            Message.is_read == False
        ).count()

        data.append({
            "chat_id": c.id,
            "other_user": {
                "id": other.id,
                "name": other.name
            },
            "last_message": last_message,
            "last_status": last_status,
            "unread_count": unread_count
        })

    return jsonify({"success": True, "chats": data})

# ALIAS ROUTE SO FLUTTER WORKS
@app.route("/api/chats/<int:user_id>")
def chats_alias(user_id):
    return chat_list(user_id)

@app.route("/api/chat/count/<int:user_id>")
def chat_count(user_id):
    count = Chat.query.filter(
        (Chat.user1_id == user_id) | (Chat.user2_id == user_id)
    ).count()

    return jsonify({"success": True, "count": count})

@app.route("/api/unread_chats/<int:user_id>")
def unread_chats(user_id):
    unread = Message.query.join(Chat, Message.chat_id == Chat.id).filter(
        Message.sender_id != user_id,
        Message.is_read == False,
        ((Chat.user1_id == user_id) | (Chat.user2_id == user_id))
    ).count()

    return jsonify({"success": True, "count": unread})

@app.route("/api/chat/mark_read", methods=["POST"])
def mark_read():
    data = request.get_json()
    chat_id = data.get("chat_id")
    user_id = data.get("user_id")

    messages = Message.query.filter_by(chat_id=chat_id).all()

    changed = False
    for m in messages:
        if m.sender_id != user_id and m.status in ["sent", "delivered"]:
            m.status = "seen"
            m.is_read = True
            changed = True

    if changed:
        db.session.commit()

    return jsonify({"success": True})

@app.route("/api/chat/start", methods=["POST"])
def start_chat():
    data = request.get_json()
    user1_id = data.get("user1_id")
    user2_id = data.get("user2_id")
    listing_id = data.get("listing_id")

    if not all([user1_id, user2_id]):
        return jsonify({"success": False, "error": "Missing IDs"})

    chat = Chat.query.filter(
        ((Chat.user1_id == user1_id) & (Chat.user2_id == user2_id)) |
        ((Chat.user1_id == user2_id) & (Chat.user2_id == user1_id))
    ).first()

    if not chat:
        chat = Chat(
            user1_id=user1_id,
            user2_id=user2_id,
            listing_id=listing_id
        )
        db.session.add(chat)
        db.session.commit()

    return jsonify({
        "success": True,
        "chat_id": chat.id
    })

@app.route("/api/profile/update", methods=["POST"])
def update_profile():
    data = request.get_json()
    user_id = data.get("user_id")
    name = data.get("name")
    phone = data.get("phone")

    user = User.query.get(user_id)
    if not user:
        return jsonify({"success": False})

    user.name = name
    user.phone = phone
    db.session.commit()

    return jsonify({"success": True})

from werkzeug.security import check_password_hash, generate_password_hash

@app.route("/api/profile/change_password", methods=["POST"])
def change_password():
    data = request.get_json()
    user_id = data.get("user_id")
    old_password = data.get("old_password")
    new_password = data.get("new_password")

    user = User.query.get(user_id)

    if not user:
        return jsonify({"success": False, "error": "User not found"})

    # ❗ Correct hash verification
    if not check_password_hash(user.password, old_password):
        return jsonify({"success": False, "error": "Old password incorrect"})

    # ❗ Save new hashed password
    user.password = generate_password_hash(new_password)
    db.session.commit()

    return jsonify({"success": True})

@app.route("/api/listings/create", methods=["POST"])
def create_listing():
    data = request.get_json()

    listing = Listing(
        user_id=data["user_id"],
        title=data["title"],
        description=data["description"],
        price_per_day=data["price_per_day"],
        category=data.get("category", ""),
        images=data.get("images", []),

        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        city=data.get("city"),
        area=data.get("area"),
        address=data.get("address")
    )

    db.session.add(listing)
    db.session.commit()

    return jsonify({"success": True, "listing_id": listing.id})

import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius (km)

    lat1, lon1, lat2, lon2 = map(math.radians,
                                 [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat/2)**2 + \
        math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2

    c = 2 * math.asin(math.sqrt(a))
    return R * c

@app.route("/api/listings/nearby", methods=["POST"])
def nearby_listings():
    data = request.get_json()

    user_lat = data.get("latitude")
    user_lon = data.get("longitude")
    radius_km = 15   # 🚀 Adjust radius (10–15 km)

    listings = Listing.query.all()
    nearby = []

    for l in listings:
        if l.latitude and l.longitude:
            dist = haversine(user_lat, user_lon, l.latitude, l.longitude)

            if dist <= radius_km:
                nearby.append({
                    "id": l.id,
                    "title": l.title,
                    "price_per_day": l.price_per_day,
                    "category": l.category,          # ⭐ FIXED
                    "images": l.images,
                    "distance": round(dist, 1),

                    # ⭐ FULL LOCATION INFO
                    "city": l.city,
                    "area": l.area,
                    "latitude": l.latitude,
                    "longitude": l.longitude,
                })

    nearby.sort(key=lambda x: x["distance"])

    return jsonify({"success": True, "nearby": nearby})

@app.route("/api/listings/by_location", methods=["POST"])
def listings_by_location():
    data = request.get_json()
    city = data.get("city")
    area = data.get("area")

    query = Listing.query

    # Filter by city
    if city:
        query = query.filter(Listing.city.ilike(f"%{city}%"))

    # Filter by area (optional)
    if area and area.strip() != "":
        query = query.filter(Listing.area.ilike(f"%{area}%"))

    result = []
    for l in query.all():
        result.append({
            "id": l.id,
            "title": l.title,
            "category": l.category,       # ⭐ CATEGORY FIXED
            "price_per_day": l.price_per_day,
            "images": l.images,

            # ⭐ FULL LOCATION DETAILS ADDED
            "city": l.city,
            "area": l.area,
            "latitude": l.latitude,
            "longitude": l.longitude,
        })

    return jsonify({"success": True, "results": result})

@app.route("/api/rent/create", methods=["POST"])
def create_rental_request():
    data = request.json

    # Create chat
    chat_id = get_or_create_chat(data["renter_id"], data["owner_id"])

    req = RentalRequest(
        listing_id=data["listing_id"],
        renter_id=data["renter_id"],
        owner_id=data["owner_id"],
        start_date=data["start_date"],
        end_date=data["end_date"],
        total_days=data["total_days"],
        total_price=data["total_price"],
        pickup_method=data["pickup_method"],
        address=data.get("address", ""),
        note=data.get("note", ""),
        chat_id=chat_id
    )

    db.session.add(req)

    # ❌ Do NOT hide listing here
    # listing.is_rented = True  <-- REMOVED

    db.session.commit()

    return jsonify({"success": True, "message": "Request created"})


@app.route("/api/rent/status/<int:listing_id>/<int:user_id>")
def rent_status(listing_id, user_id):
    req = RentalRequest.query.filter_by(
        listing_id=listing_id,
        renter_id=user_id
    ).order_by(RentalRequest.id.desc()).first()

    if not req:
        return jsonify({"exists": False})

    return jsonify({
        "exists": True,
        "status": req.status,
        "request_id": req.id,
        "chat_id": req.chat_id,

        # Pickup details (if owner accepted)
        "owner_pickup_address": req.owner_pickup_address,
        "owner_pickup_contact": req.owner_pickup_contact,
        "owner_pickup_note": req.owner_pickup_note
    })


@app.route("/api/rent/owner/<int:owner_id>")
def owner_rental_requests(owner_id):
    reqs = RentalRequest.query.filter_by(owner_id=owner_id).all()

    return jsonify({
        "success": True,
        "requests": [
            {
                "id": r.id,
                "listing_id": r.listing_id,
                "listing_title": r.listing.title,

                "renter_id": r.renter_id,
                "renter_name": r.renter.name,

                "start_date": r.start_date,
                "end_date": r.end_date,
                "total_days": r.total_days,
                "total_price": r.total_price,

                "pickup_method": r.pickup_method,
                "address": r.address,
                "note": r.note,

                "cnic_image": r.cnic_image,
                "selfie_image": r.selfie_image,

                "status": r.status,
                "chat_id": get_or_create_chat(r.owner_id, r.renter_id)
            }
            for r in reqs
        ]
    })


def get_or_create_chat(user1_id, user2_id):
    existing = Chat.query.filter(
        ((Chat.user1_id == user1_id) & (Chat.user2_id == user2_id)) |
        ((Chat.user1_id == user2_id) & (Chat.user2_id == user1_id))
    ).first()

    if existing:
        return existing.id

    chat = Chat(user1_id=user1_id, user2_id=user2_id)
    db.session.add(chat)
    db.session.commit()
    return chat.id


@app.route("/api/rent/my/<int:user_id>")
def my_rentals(user_id):
    reqs = RentalRequest.query.filter_by(renter_id=user_id).all()

    return jsonify({
        "success": True,
        "rentals": [
            {
                "id": r.id,
                "listing_id": r.listing_id,
                "listing_title": r.listing.title,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "total_days": r.total_days,
                "total_price": r.total_price,
                "pickup_method": r.pickup_method,
                "address": r.address,
                "note": r.note,

                # Show pickup details to renter ALSO
                "owner_pickup_address": r.owner_pickup_address,
                "owner_pickup_contact": r.owner_pickup_contact,
                "owner_pickup_note": r.owner_pickup_note,

                "status": r.status,
                "owner_id": r.owner_id,
                "owner_name": r.owner.name,

                "chat_id": get_or_create_chat(r.owner_id, r.renter_id)
            }
            for r in reqs
        ]
    })


@app.route("/api/rent/decision", methods=["POST"])
def rent_decision():
    data = request.json
    req = RentalRequest.query.get(data["request_id"])

    status = data["status"]
    req.status = status

    listing = Listing.query.get(req.listing_id)

    # Owner ACCEPTED the rental → Hide listing
    if status == "accepted":
        listing.is_rented = True

    # Owner DECLINED → Show listing again
    elif status == "declined":
        listing.is_rented = False

    # Pickup details (if self-pickup)
    if "owner_pickup_address" in data:
        req.owner_pickup_address = data["owner_pickup_address"]
        req.owner_pickup_contact = data["owner_pickup_contact"]
        req.owner_pickup_note = data.get("owner_pickup_note", "")

    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/rent/return", methods=["POST"])
def rent_return():
    data = request.json
    req = RentalRequest.query.get(data["request_id"])

    if not req:
        return jsonify({"success": False, "error": "Request not found"}), 404

    req.status = "returned"

    # Make listing visible again
    listing = Listing.query.get(req.listing_id)
    listing.is_rented = False

    db.session.commit()
    return jsonify({"success": True})

@app.route("/api/rent/create_safe", methods=["POST"])
def create_safe_rent():
    data = request.json

    renter_id = data["renter_id"]

    # -------------------------------------------------------------
    # ❗ BLOCK USER IF THEY ALREADY HAVE AN ACTIVE RENTAL
    # -------------------------------------------------------------
    active_rental = RentalRequest.query.filter(
        RentalRequest.renter_id == renter_id,
        RentalRequest.status.in_(["accepted", "ongoing"])  # actively rented
    ).first()

    if active_rental:
        return jsonify({
            "success": False,
            "error": "You already have an active rental. Return your current item first."
        }), 400

    # -------------------------------------------------------------
    # 🔥 CREATE OR GET CHAT
    # -------------------------------------------------------------
    chat_id = get_or_create_chat(data["renter_id"], data["owner_id"])

    # -------------------------------------------------------------
    # ⭐ CREATE RENTAL REQUEST (SAFE MODE)
    # -------------------------------------------------------------
    req = RentalRequest(
        listing_id=data["listing_id"],
        renter_id=data["renter_id"],
        owner_id=data["owner_id"],

        start_date=data["start_date"],
        end_date=data["end_date"],
        total_days=data["total_days"],
        total_price=data["total_price"],

        pickup_method=data["pickup_method"],
        address=data.get("address", ""),
        note=data.get("note", ""),

        cnic_image=data["cnic_image"],
        selfie_image=data["selfie_image"],
        renter_verified=True,
        safety_rules_agreed=data["rules_agreed"],
        agreement_signed_at=datetime.utcnow(),

        chat_id=chat_id
    )

    db.session.add(req)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Safe rental request created",
        "chat_id": chat_id
    })

@app.route("/api/rent/check_request", methods=["POST"])
def check_rent_request():
    data = request.json
    listing_id = data["listing_id"]
    renter_id = data["renter_id"]

    req = RentalRequest.query.filter_by(
        listing_id=listing_id,
        renter_id=renter_id
    ).order_by(RentalRequest.id.desc()).first()

    if not req:
        return jsonify({"exists": False})

    return jsonify({
        "exists": True,
        "status": req.status
    })

@app.route("/api/banner")
def get_banner():
    banner = AppBanner.query.filter_by(active=True).first()
    if banner:
        return {
            "success": True,
            "text": banner.text,
            "bg_color": banner.bg_color,
            "text_color": banner.text_color
        }
    return {"success": False, "message": "No banner active"}

@app.route("/admin/banner/update", methods=["POST"])
def admin_update_banner():
    data = request.form

    banner = AppBanner.query.first()
    if not banner:
        banner = AppBanner()

    banner.text = data.get("text")
    banner.bg_color = data.get("bg_color", "#EDE7F6")
    banner.text_color = data.get("text_color", "#5A2DFF")
    banner.active = True if data.get("active") == "on" else False

    db.session.add(banner)
    db.session.commit()

    flash("Banner updated successfully!", "success")
    return redirect("/admin")

@app.route("/admin/user/<int:user_id>")
def admin_user_details(user_id):
    user = User.query.get_or_404(user_id)
    listings = Listing.query.filter_by(user_id=user_id).all()

    return render_template(
        "admin_user_details.html",
        user=user,
        listings=listings
    )

@app.route("/admin/listing/<int:id>")
def admin_listing_details(id):
    listing = Listing.query.get_or_404(id)
    user = User.query.get(listing.user_id)

    return render_template(
        "admin_listing_details.html",
        listing=listing,
        user=user
    )

@app.route("/admin/user/block/<int:user_id>", methods=["POST"])
def admin_block_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_blocked = True
    db.session.commit()
    flash("User blocked successfully!", "warning")
    return redirect("/admin")


@app.route("/admin/user/unblock/<int:user_id>", methods=["POST"])
def admin_unblock_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_blocked = False
    db.session.commit()
    flash("User unblocked successfully!", "success")
    return redirect("/admin")


@app.route("/admin/user/delete/<int:user_id>", methods=["POST"])
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)

    # ======================================
    # 1. DELETE LISTINGS BY USER
    # ======================================
    Listing.query.filter_by(user_id=user.id).delete(synchronize_session=False)

    # ======================================
    # 2. DELETE MESSAGES SENT BY USER
    # ======================================
    Message.query.filter_by(sender_id=user.id).delete(synchronize_session=False)

    # ======================================
    # 3. DELETE ALL MESSAGES IN CHATS WHERE USER WAS INVOLVED
    # ======================================
    # Find all chat IDs where user is user1 or user2
    chat_ids = db.session.query(Chat.id).filter(
        (Chat.user1_id == user.id) |
        (Chat.user2_id == user.id)
    ).all()

    chat_ids = [c.id for c in chat_ids]

    if chat_ids:
        Message.query.filter(Message.chat_id.in_(chat_ids)).delete(synchronize_session=False)

    # ======================================
    # 4. DELETE THE CHATS
    # ======================================
    Chat.query.filter(
        (Chat.user1_id == user.id) |
        (Chat.user2_id == user.id)
    ).delete(synchronize_session=False)

    # ======================================
    # 5. DELETE RENTAL REQUESTS (user can be renter or owner)
    # ======================================
    RentalRequest.query.filter(
        (RentalRequest.renter_id == user.id) |
        (RentalRequest.owner_id == user.id)
    ).delete(synchronize_session=False)

    # ======================================
    # 6. DELETE USER
    # ======================================
    db.session.delete(user)
    db.session.commit()

    flash("User deleted permanently!", "danger")
    return redirect("/admin")

# ================== MAIN ==================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)