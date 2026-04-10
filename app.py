"""
Bookworm - Book Inventory Management System
Flask Backend Application
"""

import os
import secrets
from functools import wraps
from datetime import date, datetime

import bcrypt
import requests as http_requests
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, jsonify, session, redirect, url_for
)
from flask_cors import CORS
from supabase import create_client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
CORS(app)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def login_required(f):
    """Decorator: redirect to login if not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """Decorator: restrict access to specific auth levels."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if "auth_level" not in session:
                return jsonify({"error": "Authentication required"}), 401
            if session["auth_level"] not in roles:
                return jsonify({"error": "Insufficient permissions"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ---------------------------------------------------------------------------
# Page routes (HTML templates)
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/add-book")
@login_required
def add_book_page():
    return render_template("add_book.html")


@app.route("/remove-book")
@login_required
def remove_book_page():
    return render_template("remove_book.html")


@app.route("/sell-book")
@login_required
def sell_book_page():
    return render_template("sell_book.html")


@app.route("/inventory")
@login_required
def inventory_page():
    return render_template("inventory.html")


@app.route("/pricing")
@login_required
def pricing_page():
    return render_template("pricing.html")


# ---------------------------------------------------------------------------
# API: Authentication
# ---------------------------------------------------------------------------
@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    resp = supabase.table("users").select("*").eq("username", username).execute()
    if not resp.data:
        return jsonify({"error": "Invalid credentials"}), 401

    user = resp.data[0]
    if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        return jsonify({"error": "Invalid credentials"}), 401

    # Set session
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    session["display_name"] = user["display_name"]
    session["auth_level"] = user["auth_level"]
    session["store_id"] = user["store_id"]

    return jsonify({
        "message": "Login successful",
        "user": {
            "user_id": user["user_id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "auth_level": user["auth_level"],
            "store_id": user["store_id"],
        }
    })


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@app.route("/api/auth/me", methods=["GET"])
def api_me():
    if "user_id" not in session:
        return jsonify({"user": None})
    return jsonify({
        "user": {
            "user_id": session["user_id"],
            "username": session["username"],
            "display_name": session["display_name"],
            "auth_level": session["auth_level"],
            "store_id": session["store_id"],
        }
    })


@app.route("/api/auth/register", methods=["POST"])
@login_required
@role_required("admin")
def api_register():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    display_name = data.get("display_name", "").strip()
    auth_level = data.get("auth_level", "employee")
    store_id = data.get("store_id")

    if not username or not password or not display_name:
        return jsonify({"error": "username, password, and display_name are required"}), 400

    if auth_level not in ("admin", "manager", "employee"):
        return jsonify({"error": "auth_level must be admin, manager, or employee"}), 400

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        resp = supabase.table("users").insert({
            "username": username,
            "password_hash": hashed,
            "display_name": display_name,
            "auth_level": auth_level,
            "store_id": store_id,
        }).execute()
        return jsonify({"message": "User created", "user": resp.data[0]}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# API: Stores
# ---------------------------------------------------------------------------
@app.route("/api/stores", methods=["GET"])
@login_required
def api_get_stores():
    resp = supabase.table("stores").select("*").order("store_id").execute()
    return jsonify(resp.data or [])


@app.route("/api/stores", methods=["POST"])
@login_required
@role_required("admin", "manager")
def api_create_store():
    data = request.get_json()
    store_name = data.get("store_name", "").strip()
    location = data.get("location", "").strip()

    if not store_name:
        return jsonify({"error": "store_name is required"}), 400

    try:
        resp = supabase.table("stores").insert({
            "store_name": store_name,
            "location": location,
        }).execute()
        return jsonify(resp.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/stores/<int:store_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def api_delete_store(store_id):
    try:
        supabase.table("stores").delete().eq("store_id", store_id).execute()
        return jsonify({"message": "Store deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# API: Books
# ---------------------------------------------------------------------------
@app.route("/api/books", methods=["GET"])
@login_required
def api_get_books():
    """Search / list books with optional filters."""
    title = request.args.get("title", "")
    author = request.args.get("author", "")
    genre = request.args.get("genre", "")
    year = request.args.get("year", "")
    isbn = request.args.get("isbn", "")
    sort_by = request.args.get("sort_by", "title")
    order = request.args.get("order", "asc")
    limit = min(int(request.args.get("limit", 100)), 500)

    q = supabase.table("books").select("*")

    if title:
        q = q.ilike("title", f"%{title}%")
    if author:
        q = q.ilike("author", f"%{author}%")
    if genre:
        q = q.ilike("genre", f"%{genre}%")
    if year:
        q = q.eq("year", int(year))
    if isbn:
        q = q.or_(f"isbn_13.eq.{isbn},isbn_10.eq.{isbn}")

    valid_sorts = ["title", "author", "year", "rating", "genre"]
    if sort_by in valid_sorts:
        q = q.order(sort_by, desc=(order == "desc"))

    resp = q.limit(limit).execute()
    return jsonify(resp.data or [])


@app.route("/api/books/<isbn_13>", methods=["GET"])
@login_required
def api_get_book(isbn_13):
    resp = supabase.table("books").select("*").eq("isbn_13", isbn_13).execute()
    if not resp.data:
        return jsonify({"error": "Book not found"}), 404
    return jsonify(resp.data[0])


@app.route("/api/books", methods=["POST"])
@login_required
@role_required("admin", "manager")
def api_add_book():
    data = request.get_json()
    isbn_13 = data.get("isbn_13", "").strip()
    title = data.get("title", "").strip()
    author = data.get("author", "").strip()

    if not isbn_13 or not title or not author:
        return jsonify({"error": "isbn_13, title, and author are required"}), 400

    book_data = {
        "isbn_13": isbn_13,
        "isbn_10": data.get("isbn_10", "").strip() or None,
        "title": title,
        "author": author,
        "year": data.get("year"),
        "edition": data.get("edition", 1),
        "page_count": data.get("page_count"),
        "genre": data.get("genre", "").strip() or None,
        "rating": data.get("rating", 0),
        "publisher": data.get("publisher", "").strip() or None,
        "language": data.get("language", "English"),
        "cover_type": data.get("cover_type", "paperback"),
    }

    try:
        resp = supabase.table("books").insert(book_data).execute()
        return jsonify(resp.data[0]), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/books/<isbn_13>", methods=["PUT"])
@login_required
@role_required("admin", "manager")
def api_update_book(isbn_13):
    data = request.get_json()
    allowed = ["isbn_10", "title", "author", "year", "edition", "page_count",
               "genre", "rating", "publisher", "language", "cover_type"]
    updates = {k: v for k, v in data.items() if k in allowed}

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    try:
        resp = supabase.table("books").update(updates).eq("isbn_13", isbn_13).execute()
        if not resp.data:
            return jsonify({"error": "Book not found"}), 404
        return jsonify(resp.data[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/books/<isbn_13>", methods=["DELETE"])
@login_required
@role_required("admin", "manager")
def api_delete_book(isbn_13):
    try:
        resp = supabase.table("books").delete().eq("isbn_13", isbn_13).execute()
        return jsonify({"message": "Book deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# API: Open Library ISBN Lookup
# ---------------------------------------------------------------------------
@app.route("/api/books/lookup/<isbn>", methods=["GET"])
@login_required
def api_lookup_isbn(isbn):
    """Fetch book info from Open Library API by ISBN."""
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
        r = http_requests.get(url, timeout=10)
        data = r.json()
        key = f"ISBN:{isbn}"

        if key not in data:
            return jsonify({"error": "ISBN not found on Open Library"}), 404

        book = data[key]
        result = {
            "title": book.get("title", ""),
            "author": ", ".join(a.get("name", "") for a in book.get("authors", [])),
            "publisher": ", ".join(p.get("name", "") for p in book.get("publishers", [])),
            "year": None,
            "page_count": book.get("number_of_pages"),
            "cover_url": book.get("cover", {}).get("medium"),
            "subjects": [s.get("name", "") for s in book.get("subjects", [])[:5]],
        }

        # Extract year from publish_date
        pub_date = book.get("publish_date", "")
        if pub_date:
            for part in pub_date.replace(",", " ").split():
                if part.isdigit() and len(part) == 4:
                    result["year"] = int(part)
                    break

        # Try to get both ISBN formats
        for ident in book.get("identifiers", {}).get("isbn_13", []):
            result["isbn_13"] = ident
        for ident in book.get("identifiers", {}).get("isbn_10", []):
            result["isbn_10"] = ident

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Lookup failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# API: Inventory
# ---------------------------------------------------------------------------
@app.route("/api/inventory", methods=["GET"])
@login_required
def api_get_inventory():
    """Get inventory with optional store and book filters."""
    store_id = request.args.get("store_id")
    isbn_13 = request.args.get("isbn_13")
    title = request.args.get("title", "")
    author = request.args.get("author", "")
    genre = request.args.get("genre", "")
    year = request.args.get("year", "")
    sort_by = request.args.get("sort_by", "title")
    order = request.args.get("order", "asc")

    # Use a join query via the view
    q = supabase.table("book_inventory_view").select("*")

    if store_id and store_id != "all":
        q = q.eq("store_id", int(store_id))
    if isbn_13:
        q = q.eq("isbn_13", isbn_13)
    if title:
        q = q.ilike("title", f"%{title}%")
    if author:
        q = q.ilike("author", f"%{author}%")
    if genre:
        q = q.ilike("genre", f"%{genre}%")
    if year:
        q = q.eq("year", int(year))

    valid_sorts = {"title": "title", "author": "author", "year": "year",
                   "rating": "rating", "price": "base_price", "name": "title",
                   "quantity": "quantity"}
    sort_col = valid_sorts.get(sort_by, "title")
    q = q.order(sort_col, desc=(order == "desc"))

    resp = q.limit(500).execute()
    return jsonify(resp.data or [])


@app.route("/api/inventory", methods=["POST"])
@login_required
@role_required("admin", "manager")
def api_set_inventory():
    """Set inventory quantity for a book at a specific store."""
    data = request.get_json()
    isbn_13 = data.get("isbn_13", "").strip()
    store_id = data.get("store_id")
    quantity = data.get("quantity", 0)

    if not isbn_13 or not store_id:
        return jsonify({"error": "isbn_13 and store_id are required"}), 400

    try:
        # Upsert: insert or update
        resp = supabase.table("inventory").upsert({
            "isbn_13": isbn_13,
            "store_id": int(store_id),
            "quantity": int(quantity),
        }, on_conflict="isbn_13,store_id").execute()
        return jsonify(resp.data[0] if resp.data else {"message": "Updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/inventory/sell", methods=["POST"])
@login_required
def api_sell_book():
    """Decrease inventory by a given amount (sell copies)."""
    data = request.get_json()
    isbn_13 = data.get("isbn_13", "").strip()
    store_id = data.get("store_id")
    quantity_sold = data.get("quantity", 1)

    if not isbn_13 or not store_id:
        return jsonify({"error": "isbn_13 and store_id are required"}), 400

    # Get current inventory
    resp = (supabase.table("inventory")
            .select("*")
            .eq("isbn_13", isbn_13)
            .eq("store_id", int(store_id))
            .execute())

    if not resp.data:
        return jsonify({"error": "No inventory record found for this book/store"}), 404

    current_qty = resp.data[0]["quantity"]
    new_qty = current_qty - int(quantity_sold)

    if new_qty < 0:
        return jsonify({"error": f"Not enough stock. Current: {current_qty}"}), 400

    try:
        resp = (supabase.table("inventory")
                .update({"quantity": new_qty})
                .eq("isbn_13", isbn_13)
                .eq("store_id", int(store_id))
                .execute())
        return jsonify({
            "message": f"Sold {quantity_sold} copies",
            "new_quantity": new_qty,
            "data": resp.data[0] if resp.data else {}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# API: Pricing
# ---------------------------------------------------------------------------
@app.route("/api/pricing", methods=["GET"])
@login_required
def api_get_pricing():
    """Get pricing info, optionally filtered by store/book."""
    store_id = request.args.get("store_id")
    isbn_13 = request.args.get("isbn_13")

    q = supabase.table("pricing").select("*, books(title, author), stores(store_name)")

    if store_id:
        q = q.eq("store_id", int(store_id))
    if isbn_13:
        q = q.eq("isbn_13", isbn_13)

    resp = q.order("isbn_13").execute()
    return jsonify(resp.data or [])


@app.route("/api/pricing", methods=["POST"])
@login_required
@role_required("admin", "manager")
def api_set_pricing():
    """Set or update pricing for a book at a store."""
    data = request.get_json()
    isbn_13 = data.get("isbn_13", "").strip()
    store_id = data.get("store_id")

    if not isbn_13 or not store_id:
        return jsonify({"error": "isbn_13 and store_id are required"}), 400

    pricing_data = {
        "isbn_13": isbn_13,
        "store_id": int(store_id),
        "base_price": float(data.get("base_price", 0)),
        "discount_percent": float(data.get("discount_percent", 0)),
        "discount_start": data.get("discount_start"),
        "discount_end": data.get("discount_end"),
        "promo_type": data.get("promo_type", "none"),
        "promo_value": float(data.get("promo_value", 0)),
        "promo_start": data.get("promo_start"),
        "promo_end": data.get("promo_end"),
    }

    try:
        resp = supabase.table("pricing").upsert(
            pricing_data, on_conflict="isbn_13,store_id"
        ).execute()
        return jsonify(resp.data[0] if resp.data else {"message": "Updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/pricing/bulk-sale", methods=["POST"])
@login_required
@role_required("admin", "manager")
def api_bulk_sale():
    """Apply a discount/promo to multiple books at once."""
    data = request.get_json()
    isbn_list = data.get("isbn_list", [])
    store_id = data.get("store_id")
    discount_percent = data.get("discount_percent", 0)
    discount_start = data.get("discount_start")
    discount_end = data.get("discount_end")
    promo_type = data.get("promo_type", "percentage")
    promo_value = data.get("promo_value", 0)

    if not isbn_list or not store_id:
        return jsonify({"error": "isbn_list and store_id are required"}), 400

    results = []
    errors = []

    for isbn in isbn_list:
        try:
            pricing_data = {
                "isbn_13": isbn,
                "store_id": int(store_id),
                "discount_percent": float(discount_percent),
                "discount_start": discount_start,
                "discount_end": discount_end,
                "promo_type": promo_type,
                "promo_value": float(promo_value),
                "promo_start": discount_start,
                "promo_end": discount_end,
            }
            resp = supabase.table("pricing").upsert(
                pricing_data, on_conflict="isbn_13,store_id"
            ).execute()
            results.append(isbn)
        except Exception as e:
            errors.append({"isbn": isbn, "error": str(e)})

    return jsonify({
        "message": f"Updated {len(results)} books",
        "updated": results,
        "errors": errors
    })


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
