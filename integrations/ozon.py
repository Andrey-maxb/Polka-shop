#!/usr/bin/env python3
"""
Интеграция с Ozon: пункты выдачи и расчёт стоимости доставки.

Два режима (переменная окружения OZON_MODE):
  demo — считает по тарифной сетке из config.py, ПВЗ берёт из data/pvz.json.
         Так сайт полностью работает без договора с Ozon.
  api  — обращается к Ozon Seller API с вашими OZON_CLIENT_ID / OZON_API_KEY.
         Если Ozon недоступен или ключей нет — автоматически откатывается
         на demo, чтобы витрина не падала в день запуска.

Важно про «настоящий» расчёт доставки:
  Ozon отдаёт стоимость доставки и список ПВЗ только партнёрам с подключённой
  схемой FBS/realFBS (Ozon Доставка). Точные пути методов и набор полей зависят
  от вашего тарифа, поэтому в _api_request() оставлена одна точка правки.
  Что запросить у менеджера Ozon: доступ к Seller API (Client-Id, Api-Key)
  и метод расчёта стоимости доставки до ПВЗ.
"""
import json
import os
import ssl
import urllib.error
import urllib.request

import config

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PVZ_PATH = os.path.join(BASE, "data", "pvz.json")
LOG_PREFIX = "[ozon]"


def _log(msg):
    print(f"{LOG_PREFIX} {msg}")


# --------------------------------------------------------------------------
# Пункты выдачи
# --------------------------------------------------------------------------
def load_pvz():
    try:
        with open(PVZ_PATH, encoding="utf-8") as f:
            return json.load(f).get("points", [])
    except (OSError, json.JSONDecodeError) as e:
        _log(f"не удалось прочитать {PVZ_PATH}: {e}")
        return []


def _api_request(path, payload):
    """Один POST в Ozon Seller API. Возвращает dict или бросает исключение."""
    req = urllib.request.Request(
        config.OZON_API_BASE.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Client-Id": config.OZON_CLIENT_ID,
            "Api-Key": config.OZON_API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_pvz(city=None, query=None):
    """Список ПВЗ с фильтрацией по городу и поиском по адресу."""
    points = load_pvz()
    source = "demo"

    if config.OZON_MODE == "api" and config.OZON_CLIENT_ID and config.OZON_API_KEY:
        try:
            data = _api_request("/v1/delivery/point/list", {"filter": {"city": city} if city else {}})
            remote = data.get("points") or data.get("result") or []
            if remote:
                points, source = remote, "ozon"
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            _log(f"API недоступен ({e}), использую локальный список ПВЗ")

    if city:
        city_l = city.lower()
        points = [p for p in points if city_l in p.get("city", "").lower()]
    if query:
        q = query.lower()
        points = [p for p in points if q in p.get("address", "").lower() or q in p.get("city", "").lower()]

    cities = sorted({p.get("city", "") for p in load_pvz() if p.get("city")})
    return {"source": source, "cities": cities, "points": points[:60], "total": len(points)}


def get_pvz_by_id(pvz_id):
    for p in load_pvz():
        if p.get("id") == pvz_id:
            return p
    return None


# --------------------------------------------------------------------------
# Расчёт доставки
# --------------------------------------------------------------------------
def _round_price(x):
    return int(round(x / 10.0) * 10)


def calc_delivery(items, pvz, subtotal):
    """items: [{'price': int, 'qty': int, 'weight': float}]. Возвращает dict с ценой и сроком."""
    weight = sum(float(i.get("weight", 0.3)) * int(i.get("qty", 1)) for i in items)
    max_unit = max([float(i.get("weight", 0.3)) for i in items], default=0.3)

    if not pvz:
        return {"ok": False, "error": "Не выбран пункт выдачи"}

    limit = float(pvz.get("maxWeight", 25))
    if max_unit > limit:
        return {
            "ok": False,
            "error": f"Товар тяжелее {limit:g} кг не помещается в этот ПВЗ — выберите пункт выдачи",
        }

    # вариант через Ozon Seller API
    if config.OZON_MODE == "api" and config.OZON_CLIENT_ID and config.OZON_API_KEY:
        try:
            data = _api_request("/v1/delivery/check", {
                "delivery_point_id": pvz.get("id"),
                "items": [{"sku": str(i.get("id")), "quantity": int(i.get("qty", 1))} for i in items],
                "total_price": subtotal,
            })
            price = data.get("price") or data.get("delivery_price")
            if price is not None:
                days = data.get("days") or data.get("delivery_days") or config.DELIVERY_MAX_DAYS
                return {
                    "ok": True,
                    "price": float(price),
                    "days": f"{int(days) - 1 if int(days) > 1 else 1}–{int(days)}",
                    "weight": round(weight, 2),
                    "free": float(price) == 0,
                    "source": "ozon",
                }
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            _log(f"расчёт через API не удался ({e}), считаю по тарифу")

    # тарифная сетка (demo / fallback)
    price = config.DELIVERY_BASE + max(0.0, weight - 1.0) * config.DELIVERY_PER_KG
    free = False
    if config.DELIVERY_FREE_FROM and subtotal >= config.DELIVERY_FREE_FROM:
        price, free = 0.0, True
    price = _round_price(price)

    return {
        "ok": True,
        "price": float(price),
        "days": f"2–{config.DELIVERY_MAX_DAYS}",
        "weight": round(weight, 2),
        "free": free,
        "source": "tariff",
    }


def track_order(order_number):
    """Трек-номер и статус отправления. В demo-режиме — заглушка."""
    if config.OZON_MODE == "api" and config.OZON_CLIENT_ID and config.OZON_API_KEY:
        try:
            data = _api_request("/v2/posting/fbs/get", {"posting_number": order_number})
            return {"status": data.get("status"), "tracking": data.get("tracking_number")}
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            _log(f"трекинг недоступен: {e}")
    return {"status": "awaiting_packaging", "tracking": None}
