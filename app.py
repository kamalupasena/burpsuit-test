"""Intentionally vulnerable, local-only API for Burp Suite teaching."""
from __future__ import annotations

import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, make_response, request

app = Flask(__name__)
DB_PATH = Path(os.environ.get("LAB_DB", "/tmp/burp-lab.sqlite3"))
SESSIONS: dict[str, dict[str, Any]] = {}


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def initialize() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT,
                role TEXT, email TEXT, bio TEXT
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY, name TEXT, description TEXT, price REAL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER,
                quantity INTEGER, status TEXT
            );
        """)
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            db.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", [
                (1, "alice", "alice123", "user", "alice@example.test", "Wallet customer"),
                (2, "bob", "bob123", "user", "bob@example.test", "Merchant customer"),
                (3, "admin", "admin123", "admin", "admin@example.test", "Lab administrator"),
            ])
            db.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", [
                (1, "Serendib Tea", "Ceylon black tea, 100 g", 4.50),
                (2, "Canvas Tote", "Reusable market bag", 8.00),
                (3, "Travel Mug", "Insulated stainless steel mug", 12.25),
            ])
            db.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", [
                (1001, 1, 1, 2, "shipped"), (1002, 2, 2, 1, "processing"),
                (1003, 1, 3, 1, "delivered"),
            ])


def current_user() -> dict[str, Any] | None:
    token = request.cookies.get("lab_session") or request.headers.get("X-Lab-Token")
    return SESSIONS.get(token or "")


def require_user():
    user = current_user()
    if not user:
        return None, (jsonify(error="authentication required"), 401)
    return user, None


@app.get("/health")
def health():
    return jsonify(status="ok", lab="burp-suite-api")


@app.get("/api/docs")
def docs():
    return jsonify({"service": "Serendib Pay training API", "version": "1.0",
                    "auth": "POST /api/auth/login; cookie lab_session or X-Lab-Token",
                    "routes": ["/api/auth/login", "/api/auth/logout", "/api/me",
                               "/api/users/{id}", "/api/products", "/api/search?q=",
                               "/api/orders", "/api/admin/reports", "/api/lab/reset"]})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    with connect() as db:
        # Intentional SQL injection exercise: use only this seeded local database.
        sql = "SELECT id, username, role FROM users WHERE username='" + str(body.get("username", "")) + "' AND password='" + str(body.get("password", "")) + "'"
        try:
            row = db.execute(sql).fetchone()
        except sqlite3.Error as exc:
            return jsonify(error="database query failed", detail=str(exc)), 400
    if not row:
        return jsonify(error="invalid credentials"), 401
    token = secrets.token_urlsafe(18)
    SESSIONS[token] = dict(row)
    response = make_response(jsonify(message="signed in", user=dict(row), token=token))
    response.set_cookie("lab_session", token, httponly=False, samesite="Lax")
    return response


@app.post("/api/auth/logout")
def logout():
    token = request.cookies.get("lab_session") or request.headers.get("X-Lab-Token")
    SESSIONS.pop(token or "", None)
    response = make_response(jsonify(message="signed out"))
    response.delete_cookie("lab_session")
    return response


@app.get("/api/me")
def me():
    user, error = require_user()
    return error or jsonify(user=user)


@app.route("/api/users/<int:user_id>", methods=["GET", "PATCH"])
def user_profile(user_id: int):
    user, error = require_user()
    if error:
        return error
    with connect() as db:
        if request.method == "PATCH":
            body = request.get_json(silent=True) or {}
            # Intentional BOLA: authenticated users can update any seeded profile.
            allowed = {k: body[k] for k in ("email", "bio") if k in body}
            if allowed:
                fields = ", ".join(f"{k}=?" for k in allowed)
                db.execute(f"UPDATE users SET {fields} WHERE id=?", (*allowed.values(), user_id))
        row = db.execute("SELECT id, username, role, email, bio FROM users WHERE id=?", (user_id,)).fetchone()
    return (jsonify(error="user not found"), 404) if not row else jsonify(user=dict(row), viewer=user["username"])


@app.get("/api/products")
def products():
    with connect() as db:
        rows = db.execute("SELECT * FROM products ORDER BY id").fetchall()
    return jsonify(products=[dict(row) for row in rows])


@app.get("/api/products/<int:product_id>")
def product(product_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    return (jsonify(error="product not found"), 404) if not row else jsonify(product=dict(row))


@app.get("/api/search")
def search():
    query = request.args.get("q", "")
    with connect() as db:
        rows = db.execute("SELECT id, name, description, price FROM products WHERE name LIKE ? OR description LIKE ?",
                          (f"%{query}%", f"%{query}%")).fetchall()
    return jsonify(query=query, results=[dict(row) for row in rows])


@app.route("/api/orders", methods=["GET", "POST"])
def orders():
    user, error = require_user()
    if error:
        return error
    with connect() as db:
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            # Intentional mass assignment: client-supplied user_id is trusted.
            owner = body.get("user_id", user["id"])
            product_id = int(body.get("product_id", 1))
            quantity = int(body.get("quantity", 1))
            cursor = db.execute("INSERT INTO orders(user_id, product_id, quantity, status) VALUES (?, ?, ?, 'processing')",
                                (owner, product_id, quantity))
            return jsonify(order_id=cursor.lastrowid, user_id=owner, status="processing"), 201
        # Intentional BOLA: optional user_id overrides the logged-in identity.
        owner = request.args.get("user_id", user["id"])
        rows = db.execute("SELECT * FROM orders WHERE user_id=?", (owner,)).fetchall()
    return jsonify(orders=[dict(row) for row in rows])


@app.get("/api/admin/reports")
def admin_reports():
    user, error = require_user()
    if error:
        return error
    # Intentional role-check flaw: any authenticated user can access the report.
    with connect() as db:
        rows = db.execute("SELECT id, username, role, email FROM users").fetchall()
    return jsonify(viewer=user["username"], users=[dict(row) for row in rows])


@app.post("/api/lab/reset")
def reset():
    # Local-only lab control, deliberately unauthenticated for easy classroom resets.
    SESSIONS.clear()
    if DB_PATH.exists():
        DB_PATH.unlink()
    initialize()
    return jsonify(message="lab data reset", seeded_accounts=["alice", "bob", "admin"])


initialize()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
