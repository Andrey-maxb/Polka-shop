#!/usr/bin/env python3
"""
Сборка автономной демо-версии магазина в одном HTML-файле.
Нужна, чтобы показать сайт без запуска Python-сервера: каталог, корзина,
оформление, ПВЗ и админка работают на встроенном mock-бэкенде.

    python3 build_demo.py

Результат: static/demo.html и static/admin-demo.html
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")
DATA = os.path.join(BASE, "data")

catalog = json.load(open(os.path.join(DATA, "catalog.json"), encoding="utf-8"))
pvz = json.load(open(os.path.join(DATA, "pvz.json"), encoding="utf-8"))
store_css = open(os.path.join(STATIC, "store.css"), encoding="utf-8").read()
admin_css = open(os.path.join(STATIC, "admin.css"), encoding="utf-8").read()
store_js = open(os.path.join(STATIC, "app.js"), encoding="utf-8").read()
admin_js = open(os.path.join(STATIC, "admin.js"), encoding="utf-8").read()
index_html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
admin_html = open(os.path.join(STATIC, "admin.html"), encoding="utf-8").read()

# --------------------------------------------------------------------------
# Mock-бэкенд: перехватывает fetch и отвечает теми же данными, что и сервер
# --------------------------------------------------------------------------
MOCK = r"""
// ===== Демо-режим: подмена серверной части прямо в браузере =====
(function () {
  // localStorage может быть недоступен в песочнице предпросмотра — даём замену в памяти
  try { window.localStorage.setItem('__t', '1'); window.localStorage.removeItem('__t'); }
  catch (e) {
    const mem = {};
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: (k) => (k in mem ? mem[k] : null),
        setItem: (k, v) => { mem[k] = String(v); },
        removeItem: (k) => { delete mem[k]; },
        clear: () => { Object.keys(mem).forEach((k) => delete mem[k]); },
      },
    });
  }

  const TARIFF = { base: 199, perKg: 39, freeFrom: 3433, maxDays: 7 };
  const SHOP = {
    name: 'ПОЛКА', seller: 'ИП Иванов Иван Иванович', inn: '000000000000',
    email: 'orders@example.ru', phone: '+7 900 000-00-00',
  };
  const CATALOG = Object.assign(
    { shop: SHOP, currency: '₽', delivery: TARIFF },
    __CATALOG__
  );
  const PVZ = __PVZ__.points;
  const STATUSES = {
    awaiting_payment: 'Ждёт оплаты', paid: 'Оплачен', packing: 'Собирается',
    shipped: 'В пути', delivered: 'Получен', cancelled: 'Отменён',
  };
  const state = {
    products: CATALOG.products.map((p) => ({
      ...p, image: p.image || null, inStock: (p.stock || 0) > 0,
    })),
    orders: [],
    seq: 0,
    admin: false,
  };

  const money = (n) => Math.round(n);

  // демонстрационные заказы, чтобы админка не была пустой при открытии
  (function seedOrders() {
    const pick = (i, qty) => {
      const p = state.products[i];
      return { id: p.id, name: p.name, price: p.price, qty };
    };
    const mk = (n, daysAgo, status, items) => {
      const subtotal = items.reduce((s, i) => s + i.price * i.qty, 0);
      const deliveryPrice = subtotal >= TARIFF.freeFrom ? 0 : 199;
      return {
        number: 'PLK-26' + String(n).padStart(4, '0'),
        createdAt: new Date(Date.now() - daysAgo * 86400000).toISOString(),
        status, subtotal, deliveryPrice, total: subtotal + deliveryPrice, weight: 1.2,
        pvz: PVZ[n % PVZ.length],
        customer: { name: ['Анна Иванова', 'Дмитрий Петров', 'Мария Ким'][n % 3], phone: '+7 900 000-00-0' + n, email: 'client' + n + '@mail.ru' },
        comment: '', items, paidAt: status === 'awaiting_payment' ? null : new Date().toISOString(),
      };
    };
    state.orders = [
      mk(3, 0, 'awaiting_payment', [pick(6, 1)]),
      mk(2, 1, 'shipped', [pick(16, 1), pick(29, 2)]),
      mk(1, 3, 'delivered', [pick(2, 2), pick(34, 1)]),
    ];
    state.seq = 3;
  })();

  function calcDelivery(items, p) {
    const weight = items.reduce((s, i) => s + (i.weight || 0.3) * i.qty, 0);
    const maxUnit = Math.max(...items.map((i) => i.weight || 0.3), 0.3);
    if (!p) return { ok: false, error: 'Не выбран пункт выдачи' };
    if (maxUnit > (p.maxWeight || 25)) {
      return { ok: false, error: 'Товар тяжелее ' + p.maxWeight + ' кг не помещается в этот ПВЗ' };
    }
    let price = TARIFF.base + Math.max(0, weight - 1) * TARIFF.perKg;
    let free = false;
    const subtotal = items.reduce((s, i) => s + i.price * i.qty, 0);
    if (subtotal >= TARIFF.freeFrom) { price = 0; free = true; }
    return {
      ok: true, price: money(price), days: '2–' + TARIFF.maxDays,
      weight: Math.round(weight * 100) / 100, free, source: 'demo',
    };
  }

  function it_variant(raw, id) {
    const found = (raw || []).find((x) => Number(x.id) === Number(id) && x.variant);
    return found ? found.variant : null;
  }

  function normalize(raw) {
    if (!Array.isArray(raw) || !raw.length) return { error: 'Корзина пуста' };
    const merged = {};
    for (const it of raw) {
      const id = Number(it.id), qty = Number(it.qty || 1);
      if (!id || !qty || qty < 1) return { error: 'Некорректный товар' };
      merged[id] = (merged[id] || 0) + qty;
    }
    const items = [];
    for (const [id, qty] of Object.entries(merged)) {
      const p = state.products.find((x) => x.id === Number(id));
      if (!p) return { error: 'Товар не найден' };
      if (p.stock < qty) return { error: '«' + p.name + '» — в наличии только ' + p.stock + ' шт.' };
      items.push({ id: p.id, name: p.name, price: p.price, qty, weight: p.weight, emoji: p.emoji,
                   image: p.image, stock: p.stock, variant: it_variant(raw, p.id) });
    }
    return { items };
  }

  function quote(body) {
    const { items, error } = normalize((body || {}).items);
    if (error) return [400, { error }];
    const subtotal = items.reduce((s, i) => s + i.price * i.qty, 0);
    const p = PVZ.find((x) => x.id === (body || {}).pvzId) || null;
    const delivery = p ? calcDelivery(items, p) : { ok: false, error: 'Выберите пункт выдачи' };
    return [200, {
      items, subtotal, count: items.reduce((s, i) => s + i.qty, 0),
      weight: Math.round(items.reduce((s, i) => s + i.weight * i.qty, 0) * 100) / 100,
      delivery, pvz: p, total: subtotal + (delivery.ok ? delivery.price : 0),
    }];
  }

  function createOrder(body) {
    const { items, error } = normalize((body || {}).items);
    if (error) return [400, { error }];
    const c = (body || {}).customer || {};
    const digits = String(c.phone || '').replace(/\D/g, '');
    if (String(c.name || '').trim().length < 2) return [400, { error: 'Укажите имя получателя' }];
    if (digits.length < 10) return [400, { error: 'Укажите корректный телефон' }];
    const p = PVZ.find((x) => x.id === (body || {}).pvzId);
    if (!p) return [400, { error: 'Выберите пункт выдачи Ozon' }];
    const subtotal = items.reduce((s, i) => s + i.price * i.qty, 0);
    const delivery = calcDelivery(items, p);
    if (!delivery.ok) return [400, { error: delivery.error }];

    items.forEach((i) => {
      const p2 = state.products.find((x) => x.id === i.id);
      if (p2) p2.stock -= i.qty;
    });
    state.seq += 1;
    const number = 'PLK-26' + String(state.seq).padStart(4, '0');
    const order = {
      number, createdAt: new Date().toISOString(), status: 'awaiting_payment',
      subtotal, deliveryPrice: delivery.price, total: subtotal + delivery.price,
      weight: delivery.weight, pvz: p,
      customer: { name: c.name.trim(), phone: c.phone, email: c.email || '' },
      comment: body.comment || '', items: items.map(({ id, name, price, qty }) => ({ id, name, price, qty })),
      paidAt: null,
    };
    state.orders.unshift(order);
    return [201, {
      order: { ...order, statusLabel: STATUSES.awaiting_payment, deliveryDays: delivery.days },
      payment: { provider: 'demo', payUrl: null },
    }];
  }

  function stats() {
    const paid = state.orders.filter((o) => ['paid', 'packing', 'shipped', 'delivered'].includes(o.status));
    return {
      orders: state.orders.length,
      ordersSum: state.orders.reduce((s, o) => s + o.total, 0),
      paidOrders: paid.length,
      revenue: paid.reduce((s, o) => s + o.total, 0),
      awaitingPayment: state.orders.filter((o) => o.status === 'awaiting_payment').length,
      outOfStock: state.products.filter((p) => p.stock === 0).length,
      lowStock: state.products.filter((p) => p.stock > 0 && p.stock <= 5).length,
      revenueByDay: paid.length ? [{ d: new Date().toISOString().slice(0, 10), c: paid.length, s: paid.reduce((x, o) => x + o.total, 0) }] : [],
    };
  }

  const routes = [
    [/^\/api\/catalog$/, () => [200, {
      ...CATALOG,
      products: state.products.map((p) => ({ ...p, inStock: p.stock > 0 })),
    }]],
    [/^\/api\/config$/, () => [200, { shop: CATALOG.shop, paymentProvider: 'demo', ozonMode: 'demo', delivery: TARIFF }]],
    [/^\/api\/health$/, () => [200, { status: 'ok' }]],
    [/^\/api\/products\/(.+)$/, (m) => {
      const p = state.products.find((x) => x.slug === decodeURIComponent(m[1]));
      return p ? [200, { product: p }] : [404, { error: 'Товар не найден' }];
    }],
    [/^\/api\/pvz$/, (m, url, q) => {
      let list = PVZ;
      const city = q.get('city'), text = (q.get('q') || '').toLowerCase();
      if (city) list = list.filter((p) => p.city.toLowerCase().includes(city.toLowerCase()));
      if (text) list = list.filter((p) => (p.address + ' ' + p.city).toLowerCase().includes(text));
      return [200, {
        source: 'demo',
        cities: [...new Set(PVZ.map((p) => p.city))].sort(),
        points: list.slice(0, 60), total: list.length,
      }];
    }],
    [/^\/api\/orders\/([^/]+)$/, (m) => {
      const o = state.orders.find((x) => x.number === decodeURIComponent(m[1]));
      return o ? [200, { order: { ...o, statusLabel: STATUSES[o.status] } }] : [404, { error: 'Заказ не найден' }];
    }],
    [/^\/api\/admin\/session$/, () => [200, { authorized: state.admin }]],
    [/^\/api\/admin\/products$/, () => [200, {
      products: state.products.map((p) => ({
        id: p.id, slug: p.slug, name: p.name, category: p.category, subcategory: p.subcategory,
        price: p.price, old_price: p.oldPrice, stock: p.stock, emoji: p.emoji, active: 1,
      })),
    }]],
    [/^\/api\/admin\/orders$/, () => [200, {
      orders: state.orders.map((o) => ({
        id: o.number, number: o.number, created_at: o.createdAt, status: o.status,
        subtotal: o.subtotal, delivery_price: o.deliveryPrice, total: o.total, weight: o.weight,
        payment_provider: 'demo', paid_at: o.paidAt, statusLabel: STATUSES[o.status],
        customer: o.customer, pvz: o.pvz, items: o.items,
      })),
      statuses: STATUSES,
    }]],
    [/^\/api\/admin\/stats$/, () => [200, stats()]],
  ];

  const posts = [
    [/^\/api\/admin\/login$/, () => { state.admin = true; return [200, { token: 'demo-token', ttl: 3600 }]; }],
    [/^\/api\/orders\/([^/]+)\/demo-pay$/, (body, path) => {
      const number = decodeURIComponent(path.split('/')[3]);
      const o = state.orders.find((x) => x.number === number);
      if (!o) return [404, { error: 'Заказ не найден' }];
      if (o.status === 'awaiting_payment') { o.status = 'paid'; o.paidAt = new Date().toISOString(); }
      return [200, { ok: true, order: { ...o, statusLabel: STATUSES[o.status] } }];
    }],
    [/^\/api\/quote$/, (body) => quote(body)],
    [/^\/api\/orders$/, (body) => createOrder(body)],
    [/^\/api\/admin\/product$/, (body) => {
      const p = state.products.find((x) => x.id === Number(body.id));
      if (!p) return [404, { error: 'Товар не найден' }];
      if (body.price != null) p.price = Number(body.price);
      if (body.stock != null) p.stock = Number(body.stock);
      return [200, { ok: true }];
    }],
    [/^\/api\/admin\/bulk-stock$/, (body) => {
      state.products.forEach((p) => { p.stock = Number(body.stock) || 0; });
      return [200, { ok: true }];
    }],
    [/^\/api\/admin\/order-status$/, (body) => {
      const o = state.orders.find((x) => x.number === body.number);
      if (!o) return [404, { error: 'Заказ не найден' }];
      if (body.status === 'cancelled' && o.status !== 'cancelled') {
        o.items.forEach((i) => {
          const p = state.products.find((x) => x.id === i.id);
          if (p) p.stock += i.qty;
        });
      }
      o.status = body.status;
      return [200, { ok: true }];
    }],
  ];

  const realFetch = window.fetch.bind(window);
  window.fetch = async function (input, opts = {}) {
    const rawUrl = typeof input === 'string' ? input : input.url;
    if (!rawUrl.startsWith('/api/')) return realFetch(input, opts);

    const url = new URL(rawUrl, location.href);
    const path = url.pathname;
    const method = (opts.method || 'GET').toUpperCase();
    let body = null;
    if (opts.body) { try { body = JSON.parse(opts.body); } catch (e) { body = {}; } }

    let result = null;
    if (method === 'GET') {
      for (const [re, fn] of routes) {
        const m = path.match(re);
        if (m) { result = fn(m, url, url.searchParams); break; }
      }
    } else {
      for (const [re, fn] of posts) {
        if (path.match(re)) { result = fn(body, path); break; }
      }
    }
    if (!result) result = [404, { error: 'Не найдено' }];
    const [status, data] = result;
    await new Promise((r) => setTimeout(r, 80)); // имитация сети, чтобы были видны состояния загрузки
    return { ok: status < 400, status, json: async () => data };
  };

  window.__DEMO__ = true;
})();
"""

MOCK = MOCK.replace("__CATALOG__", json.dumps(catalog, ensure_ascii=False)) \
           .replace("__PVZ__", json.dumps(pvz, ensure_ascii=False))


def _embed_images(html, products):
    """Встраивает фото как data URI — версия, которая работает без сервера и без сети."""
    import base64
    import re
    for p in products:
        img = p.get("image")
        if not img:
            continue
        stem = os.path.basename(img).rsplit(".", 1)[0]
        small = os.path.join(STATIC, "uploads", f"{stem}-sm.webp")
        full = os.path.join(STATIC, "uploads", f"{stem}.webp")
        path = small if os.path.exists(small) else full
        if not os.path.exists(path):
            continue
        mime = "image/webp"
        data = base64.b64encode(open(path, "rb").read()).decode()
        html = html.replace(f'"/uploads/{stem}.webp"', f'"data:{mime};base64,{data}"')
    return html


def _relative_images(html):
    """Для GitHub Pages: пути к фото относительно папки docs/."""
    return html.replace('"/uploads/', '"uploads/')


def build_store(embed_images=True):
    html = index_html
    html = html.replace('<link rel="stylesheet" href="/store.css">', f"<style>\n{store_css}\n</style>")
    html = html.replace('<a href="/admin" class="tiny">Вход для сотрудников</a>',
                        '<a href="admin-demo.html" class="tiny">Вход для сотрудников (демо)</a>')
    html = html.replace('<script src="/app.js"></script>',
                        f"<script>\n{MOCK}\n</script>\n<script>\n{store_js}\n</script>")
    html = _embed_images(html, catalog["products"]) if embed_images else _relative_images(html)
    # в автономной версии верхняя плашка предупреждает, что это демо
    html = html.replace('<span>🧾 Электронный чек на почту</span>',
                        '<span>🧾 Электронный чек на почту</span>\n      <span>🧪 Демо-режим: платежи имитируются</span>')
    out = os.path.join(STATIC, "demo.html")
    open(out, "w", encoding="utf-8").write(html)
    return out


def build_pages():
    """Версия для GitHub Pages: один файл + папка uploads рядом."""
    html = index_html
    html = html.replace('<link rel="stylesheet" href="/store.css">', f"<style>\n{store_css}\n</style>")
    html = html.replace('<a href="/admin" class="tiny">Вход для сотрудников</a>',
                        '<a href="admin-demo.html" class="tiny">Вход для сотрудников (демо)</a>')
    html = html.replace('<script src="/app.js"></script>',
                        f"<script>\n{MOCK}\n</script>\n<script>\n{store_js}\n</script>")
    html = _relative_images(html)
    os.makedirs(os.path.join(BASE, "docs"), exist_ok=True)
    out = os.path.join(BASE, "docs", "index.html")
    open(out, "w", encoding="utf-8").write(html)
    return out


def build_admin():
    html = admin_html
    html = html.replace('<link rel="stylesheet" href="/store.css">', f"<style>\n{store_css}\n</style>")
    html = html.replace('<link rel="stylesheet" href="/admin.css">', f"<style>\n{admin_css}\n</style>")
    html = html.replace('<a class="btn btn-ghost" href="/" target="_blank" style="padding:9px 16px;font-size:13.5px">Открыть магазин ↗</a>',
                        '<a class="btn btn-ghost" href="demo.html" style="padding:9px 16px;font-size:13.5px">Открыть магазин ↗</a>')
    html = html.replace('placeholder="••••••••"', 'placeholder="любой пароль — демо"')
    html = html.replace('<p class="tiny muted" style="margin-top:16px">Пароль задаётся переменной окружения <code>ADMIN_PASSWORD</code> на сервере.</p>',
                        '<p class="tiny muted" style="margin-top:16px">Это демо-версия: введите любой пароль. Заказы появляются после оформления в магазине.</p>')
    html = html.replace('<script src="/admin.js"></script>',
                        f"<script>\n{MOCK}\n</script>\n<script>\n{admin_js}\n</script>")
    out = os.path.join(STATIC, "admin-demo.html")
    open(out, "w", encoding="utf-8").write(html)
    return out


if __name__ == "__main__":
    a = build_store(embed_images=True)
    b = build_admin()
    c = build_pages()
    for f in (a, b, c):
        print(f"готово: {f}  ({os.path.getsize(f) // 1024} КБ)")
