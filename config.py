#!/usr/bin/env python3
"""Конфигурация магазина. Все значения читаются из переменных окружения,
поэтому секреты не попадают в код и в git."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv():
    """Читает .env рядом с config.py. Уже заданные переменные окружения не перезаписываются."""
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()


def _env(name, default=""):
    return os.environ.get(name, default).strip()


# --- общее ---
SHOP_NAME = _env("SHOP_NAME", "ПОЛКА")
SHOP_URL = _env("SHOP_URL", "http://localhost:8000")
PORT = int(_env("PORT", "8000"))
DB_PATH = _env("DB_PATH", os.path.join(BASE_DIR, "data", "shop.db"))

# --- админка ---
ADMIN_PASSWORD = _env("ADMIN_PASSWORD", "admin123")  # ОБЯЗАТЕЛЬНО сменить в продакшене
ADMIN_TOKEN_TTL = 12 * 3600

# --- доставка Ozon ---
# Режим: "demo" — считает по тарифной сетке ниже; "api" — запросы в Ozon Seller API.
OZON_MODE = _env("OZON_MODE", "demo")
OZON_CLIENT_ID = _env("OZON_CLIENT_ID", "")
OZON_API_KEY = _env("OZON_API_KEY", "")
OZON_API_BASE = _env("OZON_API_BASE", "https://api-seller.ozon.ru")

DELIVERY_BASE = float(_env("DELIVERY_BASE", "199"))       # базовая стоимость до ПВЗ, ₽
DELIVERY_PER_KG = float(_env("DELIVERY_PER_KG", "39"))    # за каждый кг свыше 1 кг
DELIVERY_FREE_FROM = float(_env("DELIVERY_FREE_FROM", "3433"))  # бесплатно от суммы, 0 = выключить
DELIVERY_MAX_DAYS = int(_env("DELIVERY_MAX_DAYS", "7"))

# --- оплата и облачная касса (54-ФЗ) ---
# Провайдер: "demo" — заказ создаётся без реального платежа (для отладки),
#           "yookassa" — ЮKassa: платёж + чек в облачную кассу,
#           "cloudpayments", "robokassa" — адаптеры в integrations/kassa.py
PAYMENT_PROVIDER = _env("PAYMENT_PROVIDER", "demo")
YOOKASSA_SHOP_ID = _env("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = _env("YOOKASSA_SECRET_KEY", "")
CLOUDPAYMENTS_PUBLIC_ID = _env("CLOUDPAYMENTS_PUBLIC_ID", "")
CLOUDPAYMENTS_API_SECRET = _env("CLOUDPAYMENTS_API_SECRET", "")
ROBOKASSA_LOGIN = _env("ROBOKASSA_LOGIN", "")
ROBOKASSA_PASSWORD1 = _env("ROBOKASSA_PASSWORD1", "")
ROBOKASSA_PASSWORD2 = _env("ROBOKASSA_PASSWORD2", "")

# Облачная касса (фискализация). ЮKassa умеет слать чеки сама —
# достаточно передать receipt в платёж и включить онлайн-кассу в личном кабинете.
# Для отдельной кассы (АТОЛ Онлайн, OrangeData, МодульКасса) заполните блок ниже.
FISCAL_PROVIDER = _env("FISCAL_PROVIDER", "")  # "" | "atol" | "orangedata" | "modulkassa"
FISCAL_TOKEN = _env("FISCAL_TOKEN", "")
FISCAL_GROUP_ID = _env("FISCAL_GROUP_ID", "")
VAT_CODE = _env("VAT_CODE", "1")  # 1 — без НДС (УСН), 3 — НДС 20%, 2 — 10%
SNO = _env("SNO", "osn")  # система налогообложения: osn | usn_income | usn_income_outcome | esn | patent

# --- реквизиты для чека и подвала сайта ---
SELLER_NAME = _env("SELLER_NAME", "ИП Иванов Иван Иванович")
SELLER_INN = _env("SELLER_INN", "000000000000")
SELLER_EMAIL = _env("SELLER_EMAIL", "orders@example.ru")
SELLER_PHONE = _env("SELLER_PHONE", "+7 900 000-00-00")

# --- прочее ---
RESERVE_MINUTES = int(_env("RESERVE_MINUTES", "30"))  # сколько держим остаток до оплаты
STORE_CURRENCY = "₽"
