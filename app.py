#!/usr/bin/env python3
"""
ПОЛКА — интернет-магазин с доставкой в ПВЗ Ozon.
Бэкенд на стандартной библиотеке Python (без зависимостей) + SQLite.

Запуск:  python3 app.py  ->  http://localhost:8000
Админка: http://localhost:8000/admin  (пароль из ADMIN_PASSWORD, по умолчанию admin123)
"""
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import config
from integrations import kassa, ozon

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
CATALOG_PATH = os.path.join(BASE_DIR, "data", "catalog.json")

STATUSES = {
    "awaiting_payment": "Ждёт оплаты",
    "paid": "Оплачен",
    "packing": "Собирается",
    "shipped": "В пути",
    "delivered": "Получен",
    "cancelled": "Отменён",
}


# ==========================================================================
# База данных
# ==========================================================================
def db():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    catalog = json.load(open(CATALOG_PATH, encoding="utf-8"))
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY, slug TEXT UNIQUE, name TEXT, category TEXT,
                subcategory TEXT, price INTEGER, old_price INTEGER, emoji TEXT,
                weight REAL, description TEXT, features TEXT, stock INTEGER,
                rating REAL, reviews INTEGER, badge TEXT, image TEXT,
                variants TEXT, active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE,
                created_at TEXT, status TEXT, subtotal INTEGER, delivery_price INTEGER,
                total INTEGER, weight REAL, pvz_id TEXT, pvz_json TEXT,
                customer_json TEXT, comment TEXT, payment_provider TEXT,
                payment_id TEXT, paid_at TEXT
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER,
                product_id INTEGER, name TEXT, price INTEGER, qty INTEGER
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, level TEXT, message TEXT
            );
            """
        )
        cols = [c[1] for c in conn.execute("PRAGMA table_info(products)")]
        if "image" not in cols:
            conn.execute("ALTER TABLE products ADD COLUMN image TEXT")
        if "variants" not in cols:
            conn.execute("ALTER TABLE products ADD COLUMN variants TEXT")
        ocols = [c[1] for c in conn.execute("PRAGMA table_info(order_items)")]
        if "variant" not in ocols:
            conn.execute("ALTER TABLE order_items ADD COLUMN variant TEXT")
        # скидки убраны: перечёркнутых цен больше нет
        conn.execute("UPDATE products SET old_price = NULL WHERE old_price IS NOT NULL")
        # товары: вставляем отсутствующие, остатки и цены не перетираем
        for p in catalog["products"]:
            row = conn.execute("SELECT id, stock FROM products WHERE id = ?", (p["id"],)).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO products (id, slug, name, category, subcategory, price, old_price,
                       emoji, weight, description, features, stock, rating, reviews, badge, variants)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (p["id"], p["slug"], p["name"], p["category"], p["subcategory"], p["price"],
                     None, p["emoji"], p["weight"], p["description"],
                     json.dumps(p["features"], ensure_ascii=False), p["stock"], p["rating"],
                     p["reviews"], None,
                     json.dumps(p.get("variants"), ensure_ascii=False) if p.get("variants") else None),
                )


def log_event(level, message):
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO events (created_at, level, message) VALUES (?,?,?)",
                (now_iso(), level, message[:2000]),
            )
    except sqlite3.Error:
        pass


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ==========================================================================
# Каталог
# ==========================================================================
_catalog_meta = json.load(open(CATALOG_PATH, encoding="utf-8"))


def product_public(row):
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "category": row["category"],
        "subcategory": row["subcategory"],
        "price": row["price"],
        "oldPrice": row["old_price"] if row["old_price"] and row["old_price"] > row["price"] else None,
        "emoji": row["emoji"],
        "image": row["image"],
        "weight": row["weight"],
        "description": row["description"],
        "features": json.loads(row["features"] or "[]"),
        "stock": row["stock"],
        "inStock": row["stock"] > 0,
        "rating": row["rating"],
        "reviews": row["reviews"],
        "badge": row["badge"],
        "variants": json.loads(row["variants"]) if row["variants"] else None,
    }


def get_catalog():
    with db() as conn:
        rows = conn.execute("SELECT * FROM products WHERE active = 1 ORDER BY id").fetchall()
    products = [product_public(r) for r in rows]
    return {
        "shop": {"name": config.SHOP_NAME, "seller": config.SELLER_NAME, "inn": config.SELLER_INN,
                 "email": config.SELLER_EMAIL, "phone": config.SELLER_PHONE},
        "currency": config.STORE_CURRENCY,
        "categories": _catalog_meta["categories"],
        "subcategories": _catalog_meta["subcategories"],
        "delivery": {"freeFrom": config.DELIVERY_FREE_FROM, "base": config.DELIVERY_BASE,
                     "perKg": config.DELIVERY_PER_KG, "maxDays": config.DELIVERY_MAX_DAYS},
        "products": products,
    }


def get_product(slug):
    with db() as conn:
        row = conn.execute("SELECT * FROM products WHERE slug = ? AND active = 1", (slug,)).fetchone()
    return product_public(row) if row else None


# ==========================================================================
# Корзина и заказ
# ==========================================================================
def normalize_items(raw_items):
    """Проверяет корзину и подтягивает актуальные цены из БД. Поддерживает варианты (размер/цвет)."""
    if not isinstance(raw_items, list) or not raw_items:
        return None, "Корзина пуста"
    merged = {}
    for it in raw_items:
        try:
            pid = int(it.get("id"))
            qty = int(it.get("qty", 1))
        except (TypeError, ValueError):
            return None, "Некорректный товар в корзине"
        variant = (it.get("variant") or "").strip()[:40] or None
        if qty < 1 or qty > 99:
            return None, "Количество должно быть от 1 до 99"
        key = (pid, variant)
        merged[key] = merged.get(key, 0) + qty

    items, with_db = [], db()
    try:
        for (pid, variant), qty in merged.items():
            row = with_db.execute("SELECT * FROM products WHERE id = ? AND active = 1", (pid,)).fetchone()
            if not row:
                return None, "Товар не найден в каталоге"
            variants = json.loads(row["variants"]) if row["variants"] else None
            if variants:
                if not variant:
                    return None, f"«{row['name']}» — выберите вариант"
                v = next((x for x in variants if x["label"] == variant), None)
                if not v:
                    return None, f"«{row['name']}» — такого варианта нет"
                if v["stock"] < qty:
                    return None, f"«{row['name']}» ({variant}) — в наличии только {v['stock']} шт."
            elif row["stock"] < qty:
                return None, f"«{row['name']}» — в наличии только {row['stock']} шт."
            items.append({"id": row["id"], "name": row["name"], "price": row["price"],
                          "qty": qty, "weight": row["weight"], "emoji": row["emoji"],
                          "stock": row["stock"], "variant": variant})
    finally:
        with_db.close()
    return items, None


def quote(raw_items, pvz_id=None):
    items, err = normalize_items(raw_items)
    if err:
        return 400, {"error": err}
    subtotal = sum(i["price"] * i["qty"] for i in items)
    pvz = ozon.get_pvz_by_id(pvz_id) if pvz_id else None
    delivery = ozon.calc_delivery(items, pvz, subtotal) if pvz else {"ok": False, "error": "Выберите пункт выдачи"}
    total = subtotal + (int(delivery["price"]) if delivery.get("ok") else 0)
    return 200, {
        "items": items,
        "subtotal": subtotal,
        "count": sum(i["qty"] for i in items),
        "weight": round(sum(i["weight"] * i["qty"] for i in items), 2),
        "delivery": delivery,
        "pvz": pvz,
        "total": total,
    }


def next_order_number(conn):
    year = datetime.now().year % 100
    n = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"] + 1
    return f"PLK-{year}{n:04d}"


def create_order(payload):
    items, err = normalize_items(payload.get("items"))
    if err:
        return 400, {"error": err}

    customer = payload.get("customer") or {}
    name = (customer.get("name") or "").strip()
    phone_raw = (customer.get("phone") or "").strip()
    email = (customer.get("email") or "").strip()
    digits = re.sub(r"\D", "", phone_raw)

    if len(name) < 2:
        return 400, {"error": "Укажите имя получателя"}
    if len(digits) < 10:
        return 400, {"error": "Укажите корректный телефон"}
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Zа-яА-Я]{2,}", email):
        return 400, {"error": "Проверьте email для чека"}

    pvz = ozon.get_pvz_by_id(payload.get("pvzId"))
    if not pvz:
        return 400, {"error": "Выберите пункт выдачи Ozon"}

    subtotal = sum(i["price"] * i["qty"] for i in items)
    delivery = ozon.calc_delivery(items, pvz, subtotal)
    if not delivery.get("ok"):
        return 400, {"error": delivery.get("error", "Не удалось рассчитать доставку")}

    total = subtotal + int(delivery["price"])
    customer_clean = {
        "name": name,
        "phone": f"+{digits[0]}{digits[1:]}" if len(digits) == 11 else phone_raw,
        "email": email,
    }

    conn = db()
    try:
        # резервируем остатки
        for i in items:
            cur = conn.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (i["qty"], i["id"], i["qty"]),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return 409, {"error": f"«{i['name']}» только что закончился на складе"}
            if i.get("variant"):
                row = conn.execute("SELECT variants FROM products WHERE id = ?", (i["id"],)).fetchone()
                vs = json.loads(row["variants"]) if row and row["variants"] else []
                for v in vs:
                    if v["label"] == i["variant"]:
                        v["stock"] = max(0, v["stock"] - i["qty"])
                conn.execute("UPDATE products SET variants = ? WHERE id = ?",
                             (json.dumps(vs, ensure_ascii=False), i["id"]))
        number = next_order_number(conn)
        cur = conn.execute(
            """INSERT INTO orders (number, created_at, status, subtotal, delivery_price, total,
               weight, pvz_id, pvz_json, customer_json, comment, payment_provider)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (number, now_iso(), "awaiting_payment", subtotal, int(delivery["price"]), total,
             delivery["weight"], pvz["id"], json.dumps(pvz, ensure_ascii=False),
             json.dumps(customer_clean, ensure_ascii=False),
             (payload.get("comment") or "")[:500], config.PAYMENT_PROVIDER),
        )
        order_id = cur.lastrowid
        for i in items:
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, name, price, qty, variant) VALUES (?,?,?,?,?,?)",
                (order_id, i["id"], i["name"], i["price"], i["qty"], i.get("variant")),
            )
        conn.commit()
    finally:
        conn.close()

    order = {
        "number": number,
        "total": total,
        "deliveryPrice": int(delivery["price"]),
        "customer": customer_clean,
    }
    payment = kassa.create_payment(order, items)
    with db() as c2:
        c2.execute("UPDATE orders SET payment_id = ?, payment_provider = ? WHERE number = ?",
                   (payment.get("payment_id"), payment.get("provider"), number))
    if payment.get("status") == "error":
        cancel_order(number, restore_stock=True, reason="ошибка платёжного провайдера")
        return 502, {"error": payment.get("error") or "Не удалось создать платёж"}

    log_event("info", f"создан заказ {number} на {total} ₽, доставка {delivery['price']} ₽ ({delivery.get('source')})")
    return 201, {
        "order": {
            "number": number, "status": "awaiting_payment", "statusLabel": STATUSES["awaiting_payment"],
            "subtotal": subtotal, "deliveryPrice": int(delivery["price"]), "total": total,
            "deliveryDays": delivery["days"], "weight": delivery["weight"], "pvz": pvz,
            "customer": customer_clean, "items": items,
        },
        "payment": {"provider": payment.get("provider"), "payUrl": payment.get("pay_url")},
    }


def get_order(number):
    with db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE number = ?", (number,)).fetchone()
        if not row:
            return None
        items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (row["id"],)).fetchall()
    return {
        "number": row["number"],
        "createdAt": row["created_at"],
        "status": row["status"],
        "statusLabel": STATUSES.get(row["status"], row["status"]),
        "subtotal": row["subtotal"],
        "deliveryPrice": row["delivery_price"],
        "total": row["total"],
        "weight": row["weight"],
        "pvz": json.loads(row["pvz_json"] or "{}"),
        "customer": json.loads(row["customer_json"] or "{}"),
        "comment": row["comment"],
        "paidAt": row["paid_at"],
        "items": [{"id": i["product_id"], "name": i["name"], "price": i["price"], "qty": i["qty"],
                   "variant": i["variant"]} for i in items],
    }


def cancel_order(number, restore_stock=False, reason=""):
    with db() as conn:
        row = conn.execute("SELECT id, status FROM orders WHERE number = ?", (number,)).fetchone()
        if not row or row["status"] == "cancelled":
            return False
        if restore_stock:
            for it in conn.execute("SELECT product_id, qty, variant FROM order_items WHERE order_id = ?", (row["id"],)):
                conn.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (it["qty"], it["product_id"]))
                if it["variant"]:
                    r = conn.execute("SELECT variants FROM products WHERE id = ?", (it["product_id"],)).fetchone()
                    vs = json.loads(r["variants"]) if r and r["variants"] else []
                    for v in vs:
                        if v["label"] == it["variant"]:
                            v["stock"] = v["stock"] + it["qty"]
                    conn.execute("UPDATE products SET variants = ? WHERE id = ?",
                                 (json.dumps(vs, ensure_ascii=False), it["product_id"]))
        conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (row["id"],))
    log_event("warn", f"заказ {number} отменён: {reason or 'без причины'}")
    return True


def mark_paid(number):
    with db() as conn:
        conn.execute("UPDATE orders SET status = 'paid', paid_at = ? WHERE number = ? AND status = 'awaiting_payment'",
                     (now_iso(), number))
    log_event("info", f"заказ {number} оплачен")


# ==========================================================================
# Админка
# ==========================================================================
ADMIN_SESSIONS = {}  # token -> expires_at
LOGIN_FAILS = {}     # ip -> [count, first_ts]


def make_token():
    token = hashlib.sha256(f"{time.time()}{os.urandom(16).hex()}".encode()).hexdigest()[:40]
    ADMIN_SESSIONS[token] = time.time() + config.ADMIN_TOKEN_TTL
    return token


def check_admin(headers):
    auth = headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    exp = ADMIN_SESSIONS.get(token)
    if exp and exp > time.time():
        return True
    return False


def admin_stats():
    with db() as conn:
        orders = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(total),0) s FROM orders").fetchone()
        paid = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(total),0) s FROM orders WHERE status IN ('paid','packing','shipped','delivered')").fetchone()
        waiting = conn.execute("SELECT COUNT(*) c FROM orders WHERE status = 'awaiting_payment'").fetchone()
        out = conn.execute("SELECT COUNT(*) c FROM products WHERE stock = 0").fetchone()
        low = conn.execute("SELECT COUNT(*) c FROM products WHERE stock > 0 AND stock <= 5").fetchone()
        revenue_by_day = conn.execute(
            """SELECT substr(created_at,1,10) d, COUNT(*) c, SUM(total) s FROM orders
               WHERE status IN ('paid','packing','shipped','delivered')
               GROUP BY d ORDER BY d DESC LIMIT 7"""
        ).fetchall()
    return {
        "orders": orders["c"], "ordersSum": orders["s"],
        "paidOrders": paid["c"], "revenue": paid["s"],
        "awaitingPayment": waiting["c"],
        "outOfStock": out["c"], "lowStock": low["c"],
        "revenueByDay": [dict(r) for r in revenue_by_day],
    }


# ==========================================================================
# HTTP
# ==========================================================================
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
        ".ico": "image/x-icon", ".json": "application/json; charset=utf-8",
        ".png": "image/png", ".webmanifest": "application/manifest+json"}


class Handler(BaseHTTPRequestHandler):
    server_version = "Polka/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------- служебное ----------------
    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")

    def _send(self, status, body, ctype, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    @staticmethod
    def _decode_qs(raw):
        """Устойчиво декодирует query-строку: браузеры шлют UTF-8, curl может слать сырые байты."""
        out = {}
        for k, v in parse_qs(raw, keep_blank_values=True).items():
            val = v[0]
            try:
                val = val.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            out[k] = val
        return out

    def _json(self, status, data):
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _static(self, path):
        clean = path.split("?")[0].lstrip("/") or "index.html"
        if clean in ("admin", "admin/"):
            clean = "admin.html"
        if not os.path.splitext(clean)[1]:
            clean += ".html"
        full = os.path.normpath(os.path.join(STATIC_DIR, clean))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._send(404, "404 — страница не найдена".encode("utf-8"), "text/html; charset=utf-8")
        with open(full, "rb") as fh:
            body = fh.read()
        ext = os.path.splitext(full)[1].lower()
        cache = "no-cache" if ext == ".html" else "public, max-age=3600"
        self._send(200, body, MIME.get(ext, "application/octet-stream"), {"Cache-Control": cache})

    # ---------------- GET ----------------
    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, self._decode_qs(u.query)

        if path == "/api/catalog":
            return self._json(200, get_catalog())
        if path.startswith("/api/products/"):
            slug = path.rsplit("/", 1)[-1]
            p = get_product(slug)
            return self._json(200, {"product": p}) if p else self._json(404, {"error": "Товар не найден"})
        if path == "/api/pvz":
            return self._json(200, ozon.get_pvz(city=q.get("city"), query=q.get("q")))
        if path == "/api/config":
            return self._json(200, {
                "shop": {"name": config.SHOP_NAME, "seller": config.SELLER_NAME,
                         "inn": config.SELLER_INN, "phone": config.SELLER_PHONE, "email": config.SELLER_EMAIL},
                "paymentProvider": config.PAYMENT_PROVIDER,
                "ozonMode": config.OZON_MODE,
                "delivery": {"freeFrom": config.DELIVERY_FREE_FROM, "base": config.DELIVERY_BASE,
                             "perKg": config.DELIVERY_PER_KG, "maxDays": config.DELIVERY_MAX_DAYS},
            })
        if path.startswith("/api/orders/"):
            number = path.rsplit("/", 1)[-1]
            order = get_order(number)
            return self._json(200, {"order": order}) if order else self._json(404, {"error": "Заказ не найден"})
        if path == "/api/health":
            return self._json(200, {"status": "ok", "time": now_iso()})

        # --- админ ---
        if path == "/api/admin/session":
            return self._json(200, {"authorized": check_admin(self.headers)})
        if path == "/api/admin/products":
            if not check_admin(self.headers):
                return self._json(401, {"error": "Нужен вход"})
            with db() as conn:
                rows = conn.execute(
                    "SELECT id, slug, name, category, subcategory, price, old_price, stock, emoji, active, variants "
                    "FROM products ORDER BY id").fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["variants"] = json.loads(d["variants"]) if d["variants"] else None
                out.append(d)
            return self._json(200, {"products": out})
        if path == "/api/admin/orders":
            if not check_admin(self.headers):
                return self._json(401, {"error": "Нужен вход"})
            with db() as conn:
                rows = conn.execute(
                    "SELECT * FROM orders ORDER BY id DESC LIMIT 200").fetchall()
                items = conn.execute("SELECT * FROM order_items").fetchall()
            by_order = {}
            for i in items:
                by_order.setdefault(i["order_id"], []).append(
                    {"name": i["name"], "qty": i["qty"], "price": i["price"]})
            orders = []
            for r in rows:
                o = {k: r[k] for k in ("id", "number", "created_at", "status", "subtotal",
                                       "delivery_price", "total", "weight", "payment_provider", "paid_at")}
                o["statusLabel"] = STATUSES.get(r["status"], r["status"])
                o["customer"] = json.loads(r["customer_json"] or "{}")
                o["pvz"] = json.loads(r["pvz_json"] or "{}")
                o["items"] = by_order.get(r["id"], [])
                orders.append(o)
            return self._json(200, {"orders": orders, "statuses": STATUSES})
        if path == "/api/admin/stats":
            if not check_admin(self.headers):
                return self._json(401, {"error": "Нужен вход"})
            return self._json(200, admin_stats())

        return self._static(path)

    # ---------------- POST ----------------
    def do_POST(self):
        path = urlparse(self.path).path
        payload = self._body()
        if payload is None:
            return self._json(400, {"error": "Некорректный JSON"})

        if path == "/api/quote":
            return self._json(*quote(payload.get("items"), payload.get("pvzId")))
        if path == "/api/orders":
            return self._json(*create_order(payload))
        if re.fullmatch(r"/api/orders/[^/]+/demo-pay", path):
            if config.PAYMENT_PROVIDER != "demo":
                return self._json(403, {"error": "Демо-оплата отключена: подключён реальный провайдер"})
            number = path.split("/")[3]
            if not get_order(number):
                return self._json(404, {"error": "Заказ не найден"})
            mark_paid(number)
            return self._json(200, {"ok": True, "order": get_order(number)})
        if path == "/api/payments/webhook":
            raw = json.dumps(payload, ensure_ascii=False)
            ok, number, paid = kassa.verify_webhook(dict(self.headers), raw)
            if not ok:
                log_event("warn", "отклонён вебхук платёжной системы")
                return self._json(403, {"error": "invalid signature"})
            if paid and number:
                mark_paid(number)
            return self._json(200, {"ok": True})
        if path == "/api/admin/login":
            ip = self.client_address[0]
            fails, first = LOGIN_FAILS.get(ip, [0, time.time()])
            if fails >= 10 and time.time() - first < 600:
                return self._json(429, {"error": "Слишком много попыток. Попробуйте через 10 минут"})
            password = payload.get("password") or ""
            if hmac.compare_digest(password, config.ADMIN_PASSWORD):
                LOGIN_FAILS.pop(ip, None)
                return self._json(200, {"token": make_token(), "ttl": config.ADMIN_TOKEN_TTL})
            LOGIN_FAILS[ip] = [fails + 1, first if fails else time.time()]
            log_event("warn", f"неудачный вход в админку с {ip}")
            return self._json(401, {"error": "Неверный пароль"})
        if path == "/api/admin/order-status":
            if not check_admin(self.headers):
                return self._json(401, {"error": "Нужен вход"})
            number, status = payload.get("number"), payload.get("status")
            if status not in STATUSES:
                return self._json(400, {"error": "Неизвестный статус"})
            if status == "cancelled":
                cancel_order(number, restore_stock=True, reason="отменил администратор")
            else:
                with db() as conn:
                    conn.execute("UPDATE orders SET status = ? WHERE number = ?", (status, number))
                log_event("info", f"заказ {number}: статус {status}")
            return self._json(200, {"ok": True, "order": get_order(number)})
        if path == "/api/admin/product":
            if not check_admin(self.headers):
                return self._json(401, {"error": "Нужен вход"})
            try:
                pid = int(payload.get("id"))
            except (TypeError, ValueError):
                return self._json(400, {"error": "Не указан товар"})
            fields, args = [], []
            if "price" in payload:
                try:
                    price = int(payload["price"])
                except (TypeError, ValueError):
                    return self._json(400, {"error": "Цена должна быть числом"})
                if price < 0:
                    return self._json(400, {"error": "Цена не может быть отрицательной"})
                fields.append("price = ?")
                args.append(price)
            if "stock" in payload:
                try:
                    stock = int(payload["stock"])
                except (TypeError, ValueError):
                    return self._json(400, {"error": "Остаток должен быть числом"})
                if stock < 0:
                    return self._json(400, {"error": "Остаток не может быть отрицательным"})
                fields.append("stock = ?")
                args.append(stock)
            if "active" in payload:
                fields.append("active = ?")
                args.append(1 if payload["active"] else 0)
            if not fields:
                return self._json(400, {"error": "Нет полей для изменения"})
            args.append(pid)
            with db() as conn:
                cur = conn.execute(f"UPDATE products SET {', '.join(fields)} WHERE id = ?", args)
                if cur.rowcount == 0:
                    return self._json(404, {"error": "Товар не найден"})
            return self._json(200, {"ok": True})
        if path == "/api/admin/bulk-stock":
            if not check_admin(self.headers):
                return self._json(401, {"error": "Нужен вход"})
            stock = payload.get("stock")
            if not isinstance(stock, int) or stock < 0:
                return self._json(400, {"error": "Укажите остаток числом"})
            with db() as conn:
                conn.execute("UPDATE products SET stock = ?", (stock,))
            log_event("info", f"массово установлен остаток {stock} шт. на все товары")
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "Не найдено"})

    # ---------------- HEAD ----------------
    def do_HEAD(self):
        self.do_GET()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    init_db()
    srv = Server(("0.0.0.0", config.PORT), Handler)
    print(f"{config.SHOP_NAME}: http://0.0.0.0:{config.PORT}  |  админка /admin  |  оплата: {config.PAYMENT_PROVIDER}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
