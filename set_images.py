#!/usr/bin/env python3
"""
Оптимизация фото товаров и привязка их к каталогу.

    python3 set_images.py            # сжать все jpg в static/uploads и обновить каталог
    python3 set_images.py --check    # только показать, что привязано

Правила:
  * фото кладём в static/uploads/ с именем p<ID>.jpg  (p1.jpg — товар с id=1)
  * скрипт делает из них webp-версии 640px и 320px (для карточек и превью)
  * catalog.json и база получают поле image
"""
import json
import os
import sys

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "static", "uploads")
CATALOG = os.path.join(BASE, "data", "catalog.json")
DB_PATH = os.path.join(BASE, "data", "shop.db")

SIZES = {"": 640, "@2x": 640}  # основной файл 640px, хватит и для retina-карточек


def optimize():
    made = []
    for name in sorted(os.listdir(UPLOADS)):
        if not name.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        stem = os.path.splitext(name)[0]
        src = os.path.join(UPLOADS, name)
        img = Image.open(src).convert("RGB")
        # квадрат по центру
        side = min(img.size)
        left = (img.width - side) // 2
        top = (img.height - side) // 2
        img = img.crop((left, top, left + side, top + side))

        out = os.path.join(UPLOADS, f"{stem}.webp")
        img.resize((640, 640), Image.LANCZOS).save(out, "WEBP", quality=82, method=6)
        small = os.path.join(UPLOADS, f"{stem}-sm.webp")
        img.resize((320, 320), Image.LANCZOS).save(small, "WEBP", quality=80, method=6)
        made.append((stem, os.path.getsize(out) // 1024, os.path.getsize(small) // 1024))
    return made


def attach():
    """Прописывает image в catalog.json и в базу для всех товаров, у которых есть фото."""
    catalog = json.load(open(CATALOG, encoding="utf-8"))
    linked = []
    for p in catalog["products"]:
        stem = f"p{p['id']}"
        if os.path.exists(os.path.join(UPLOADS, f"{stem}.webp")):
            p["image"] = f"/uploads/{stem}.webp"
            linked.append(p["id"])
    json.dump(catalog, open(CATALOG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if os.path.exists(DB_PATH):
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE products SET image = NULL")
        for pid in linked:
            conn.execute("UPDATE products SET image = ? WHERE id = ?", (f"/uploads/p{pid}.webp", pid))
        conn.commit()
        conn.close()
    return linked


if __name__ == "__main__":
    if "--check" in sys.argv:
        catalog = json.load(open(CATALOG, encoding="utf-8"))
        have = [p for p in catalog["products"] if p.get("image")]
        print(f"с фото: {len(have)} из {len(catalog['products'])}")
        for p in have:
            print(f"  {p['id']:>3}. {p['name'][:44]:<46} {p['image']}")
        sys.exit(0)

    made = optimize()
    linked = attach()
    total = sum(m[1] + m[2] for m in made)
    print(f"оптимизировано {len(made)} фото (webp, суммарно {total} КБ)")
    print(f"привязано к каталогу: {len(linked)} товаров")
