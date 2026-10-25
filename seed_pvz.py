#!/usr/bin/env python3
"""Генератор демо-списка ПВЗ Ozon: data/pvz.json.
В продакшене заменяется на выгрузку из API Ozon (см. integrations/ozon.py)."""
import json
import os
import random

BASE = os.path.dirname(os.path.abspath(__file__))

CITIES = [
    ("Москва", 55.7558, 37.6173, 260), ("Санкт-Петербург", 59.9343, 30.3351, 180),
    ("Краснодар", 45.0355, 38.9753, 95), ("Ростов-на-Дону", 47.2225, 39.7188, 70),
    ("Новосибирск", 55.0084, 82.9357, 80), ("Екатеринбург", 56.8389, 60.6057, 78),
    ("Казань", 55.7963, 49.1088, 65), ("Нижний Новгород", 56.3269, 44.0059, 62),
    ("Самара", 53.1959, 50.1002, 52), ("Челябинск", 55.1644, 61.4368, 48),
    ("Уфа", 54.7388, 55.9721, 44), ("Красноярск", 56.0153, 92.8932, 42),
    ("Воронеж", 51.6720, 39.1843, 40), ("Пермь", 58.0105, 56.2502, 38),
    ("Волгоград", 48.7080, 44.5133, 36), ("Краснодар", 45.0355, 38.9753, 0),
    ("Саратов", 51.5336, 46.0343, 32), ("Тюмень", 57.1522, 65.5272, 30),
    ("Сочи", 43.5855, 39.7231, 28), ("Ставрополь", 45.0428, 41.9734, 24),
    ("Иркутск", 52.2870, 104.3050, 24), ("Хабаровск", 48.4827, 135.0838, 22),
    ("Владивосток", 43.1155, 131.8855, 20), ("Калининград", 54.7104, 20.4522, 18),
]
STREETS = ["ул. Ленина", "пр-т Мира", "ул. Советская", "ул. Гагарина", "ул. Кирова",
           "пр-т Победы", "ул. Красная", "ул. Садовая", "ул. Московская", "ул. Северная",
           "ул. Центральная", "б-р Строителей"]
TYPES = [("Пункт выдачи", "📦"), ("Постамат", "🏪")]


def main():
    random.seed(7)
    points, pid = [], 0
    seen_city = set()
    for city, lat, lng, count in CITIES:
        if count == 0:
            continue
        if city in seen_city:
            continue
        seen_city.add(city)
        n = max(2, min(count // 12, 8))
        for k in range(n):
            pid += 1
            ptype = "Постамат" if k % 4 == 3 else "Пункт выдачи"
            points.append({
                "id": f"PVZ-{pid:05d}",
                "city": city,
                "address": f"{random.choice(STREETS)}, {random.randint(1, 180)}{random.choice(['', 'к1', 'к2', 'А'])}",
                "type": ptype,
                "icon": "🏪" if ptype == "Постамат" else "📦",
                "lat": round(lat + random.uniform(-0.09, 0.09), 5),
                "lng": round(lng + random.uniform(-0.12, 0.12), 5),
                "workHours": "Пн–Вс 09:00–21:00" if ptype == "Пункт выдачи" else "Круглосуточно",
                "maxWeight": 25 if ptype == "Пункт выдачи" else 15,
                "maxDimension": "до 60×40×40 см" if ptype == "Пункт выдачи" else "до 36×30×20 см",
            })
    path = os.path.join(BASE, "data", "pvz.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updatedAt": "2026-10-01", "source": "demo", "points": points}, f, ensure_ascii=False, indent=1)
    print(f"готово: {len(points)} ПВЗ в {len({p['city'] for p in points})} городах -> {path}")


if __name__ == "__main__":
    main()
