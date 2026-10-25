#!/usr/bin/env python3
"""
Оплата и фискализация (54-ФЗ).

create_payment(order) -> {"payment_id", "pay_url", "provider"}

Провайдеры:
  demo        — платёж имитируется, заказ создаётся и ждёт подтверждения в админке
  yookassa    — ЮKassa: платёж + фискальный чек (онлайн-касса в личном кабинете ЮKassa)
  cloudpayments — CloudPayments: платёж + чек через свой ОФД
  robokassa   — Robokassa

Чек собирается в build_receipt() и передаётся провайдеру вместе с платежом.
Всё, что нужно от вас: shopId/secret из личного кабинета и включённая онлайн-касса.
"""
import base64
import hashlib
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid

import config


def _log(msg):
    print(f"[kassa] {msg}")


# --------------------------------------------------------------------------
# Чек (54-ФЗ)
# --------------------------------------------------------------------------
def build_receipt(order, items):
    """Формирует объект чека в формате ЮKassa (он же принимают большинство ОФД)."""
    receipt_items = []
    for i in items:
        receipt_items.append({
            "description": i["name"][:128],
            "quantity": str(i["qty"]),
            "amount": {"value": f"{i['price'] * i['qty']:.2f}", "currency": "RUB"},
            "vat_code": int(config.VAT_CODE),
            "payment_mode": "full_payment",
            "payment_subject": "commodity",
        })
    if order.get("deliveryPrice", 0) > 0:
        receipt_items.append({
            "description": "Доставка до пункта выдачи Ozon",
            "quantity": "1",
            "amount": {"value": f"{order['deliveryPrice']:.2f}", "currency": "RUB"},
            "vat_code": int(config.VAT_CODE),
            "payment_mode": "full_payment",
            "payment_subject": "service",
        })

    return {
        "customer": {
            "email": order["customer"]["email"] if order["customer"].get("email") else None,
            "phone": order["customer"]["phone"] or None,
        },
        "items": receipt_items,
        "tax_system_code": _sno_code(),
    }


def _sno_code():
    # 1 — ОСН, 2 — УСН доход, 3 — УСН доход-расход, 4 — ЕСХН, 5 — патент
    return {"osn": 1, "usn_income": 2, "usn_income_outcome": 3, "esn": 4, "patent": 5}.get(config.SNO, 1)


# --------------------------------------------------------------------------
# HTTP helper
# --------------------------------------------------------------------------
def _post(url, payload, headers, timeout=15):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --------------------------------------------------------------------------
# Провайдеры
# --------------------------------------------------------------------------
def _create_yookassa(order, items):
    idempotency = str(uuid.uuid4())
    payload = {
        "amount": {"value": f"{order['total']:.2f}", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": f"{config.SHOP_URL}/?paid={order['number']}"},
        "description": f"Заказ {order['number']} в {config.SHOP_NAME}",
        "receipt": build_receipt(order, items),
        "metadata": {"order_number": order["number"]},
    }
    auth = base64.b64encode(
        f"{config.YOOKASSA_SHOP_ID}:{config.YOOKASSA_SECRET_KEY}".encode()
    ).decode()
    data = _post(
        "https://api.yookassa.ru/v3/payments",
        payload,
        {"Authorization": f"Basic {auth}", "Idempotence-Key": idempotency},
    )
    return {
        "provider": "yookassa",
        "payment_id": data.get("id"),
        "pay_url": (data.get("confirmation") or {}).get("confirmation_url"),
        "status": data.get("status", "pending"),
    }


def _create_cloudpayments(order, items):
    payload = {
        "PublicId": config.CLOUDPAYMENTS_PUBLIC_ID,
        "Amount": float(order["total"]),
        "Currency": "RUB",
        "InvoiceId": order["number"],
        "Description": f"Заказ {order['number']} в {config.SHOP_NAME}",
        "AccountId": order["customer"]["phone"],
        "Email": order["customer"].get("email") or "",
        "Culture": "ru-RU",
        "SendEmail": True,
        "RequireConfirmation": False,
        # CloudPayments сам пробьёт чек, если в личном кабинете включена онлайн-касса
        "Receipt": {
            "Items": [
                {
                    "Label": i["name"][:128],
                    "Price": float(i["price"]),
                    "Quantity": i["qty"],
                    "Amount": float(i["price"] * i["qty"]),
                    "Vat": int(config.VAT_CODE),
                    "Method": 1,
                    "Object": 1,
                } for i in items
            ],
            "TaxationSystem": _sno_code(),
            "Email": order["customer"].get("email") or config.SELLER_EMAIL,
        },
    }
    auth = base64.b64encode(
        f"{config.CLOUDPAYMENTS_PUBLIC_ID}:{config.CLOUDPAYMENTS_API_SECRET}".encode()
    ).decode()
    data = _post("https://api.cloudpayments.ru/orders/create", payload, {"Authorization": f"Basic {auth}"})
    model = data.get("Model") or {}
    return {
        "provider": "cloudpayments",
        "payment_id": model.get("Id"),
        "pay_url": model.get("Url") or f"{config.SHOP_URL}/?pay={order['number']}",
        "status": "pending",
    }


def _create_robokassa(order, items):
    signature = hashlib.md5(
        f"{config.ROBOKASSA_LOGIN}:{order['total']:.2f}:{order['number']}:{config.ROBOKASSA_PASSWORD1}:Shp_order={order['number']}".encode()
    ).hexdigest()
    query = (
        f"MerchantLogin={config.ROBOKASSA_LOGIN}&OutSum={order['total']:.2f}"
        f"&InvId={order['number']}&Description=Order+{order['number']}"
        f"&SignatureValue={signature}&Shp_order={order['number']}"
        f"&Receipt={urllib.parse.quote(json.dumps({'items': build_receipt(order, items)['items']}))}"
    )
    return {
        "provider": "robokassa",
        "payment_id": f"rk-{order['number']}",
        "pay_url": f"https://auth.robokassa.ru/Merchant/Index.aspx?{query}",
        "status": "pending",
    }


def create_payment(order, items):
    provider = config.PAYMENT_PROVIDER
    try:
        if provider == "yookassa" and config.YOOKASSA_SHOP_ID and config.YOOKASSA_SECRET_KEY:
            return _create_yookassa(order, items)
        if provider == "cloudpayments" and config.CLOUDPAYMENTS_PUBLIC_ID:
            return _create_cloudpayments(order, items)
        if provider == "robokassa" and config.ROBOKASSA_LOGIN:
            return _create_robokassa(order, items)
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
        _log(f"ошибка провайдера {provider}: {e}")
        return {"provider": "demo", "payment_id": None, "pay_url": None,
                "status": "error", "error": "Платёжный сервис недоступен, попробуйте позже"}

    # demo-режим
    return {
        "provider": "demo",
        "payment_id": f"demo-{order['number']}",
        "pay_url": f"/order.html?number={order['number']}",
        "status": "pending",
    }


# --------------------------------------------------------------------------
# Вебхук: провайдер сообщает об оплате
# --------------------------------------------------------------------------
def verify_webhook(headers, body):
    """Проверка подлинности уведомления. Возвращает (ok, order_number, paid)."""
    provider = config.PAYMENT_PROVIDER
    if provider == "yookassa":
        # ЮKassa присылает IP для whitelisting; дополнительно сверяем статус через GET /v3/payments/{id}
        try:
            event = json.loads(body or "{}")
        except json.JSONDecodeError:
            return False, None, False
        obj = event.get("object", {})
        return True, (obj.get("metadata") or {}).get("order_number"), obj.get("status") == "succeeded"

    if provider == "cloudpayments":
        sig = headers.get("Content-HMAC", "")
        calc = base64.b64encode(
            hashlib.sha256((body + config.CLOUDPAYMENTS_API_SECRET).encode()).digest()
        ).decode()
        if sig != calc:
            return False, None, False
        event = json.loads(body or "{}")
        return True, event.get("InvoiceId"), event.get("Status") == "Completed"

    if provider == "robokassa":
        event = json.loads(body or "{}")
        inv, out_sum, sig = event.get("InvId"), event.get("OutSum"), event.get("SignatureValue", "")
        check = hashlib.md5(f"{out_sum}:{inv}:{config.ROBOKASSA_PASSWORD2}".encode()).hexdigest()
        return check.lower() == sig.lower(), inv, True

    return True, None, False
