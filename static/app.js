/* ==========================================================================
   ПОЛКА — витрина. Ванильный JS, без зависимостей.
   ========================================================================== */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const app = $('#app');
const money = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n)) + ' ₽';
const plural = (n, a, b, c) => { const m = n % 100, k = n % 10;
  if (m > 10 && m < 20) return c; if (k > 1 && k < 5) return b; if (k === 1) return a; return c; };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ---------------- состояние ---------------- */
const state = {
  catalog: null,
  cart: JSON.parse(localStorage.getItem('polka_cart') || '{}'),
  quote: null,
  pvz: JSON.parse(localStorage.getItem('polka_pvz') || 'null'),
  pvzCity: localStorage.getItem('polka_city') || '',
  checkout: { pay: 'card', pvz: null, sending: false },
  filters: { cat: '', sub: '', q: '', min: '', max: '', instock: true, sort: 'popular' },
};

/* ---------------- API ---------------- */
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || 'Что-то пошло не так');
  return data;
}

/* ---------------- корзина ---------------- */
function cartItems() {
  if (!state.catalog) return [];
  return Object.entries(state.cart)
    .map(([key, qty]) => {
      const [id, variant] = key.split('|');
      const p = state.catalog.products.find((x) => x.id === Number(id));
      return p ? { ...p, qty, variant: variant || null, key } : null;
    })
    .filter((i) => i && i.id && i.price);
}
const itemKey = (id, variant) => `${id}|${variant || ''}`;
const cartCount = () => cartItems().reduce((s, i) => s + i.qty, 0);
const cartSum = () => cartItems().reduce((s, i) => s + i.price * i.qty, 0);

function saveCart() {
  localStorage.setItem('polka_cart', JSON.stringify(state.cart));
  paintCartCount();
}
function addToCart(id, qty = 1, variant = null, silent = false) {
  const p = state.catalog.products.find((x) => x.id === id);
  if (!p) return;
  if (p.variants && !variant) { toast('Выберите размер', 'err'); return; }
  const key = itemKey(id, variant);
  const cur = state.cart[key] || 0;
  const limit = p.variants ? (p.variants.find((v) => v.label === variant)?.stock ?? 0) : p.stock;
  if (cur + qty > limit) {
    toast(`В наличии только ${limit} ${plural(limit, 'штука', 'штуки', 'штук')}`, 'err');
    return;
  }
  state.cart[key] = cur + qty;
  saveCart();
  if (!silent) toast(`Добавлено: ${p.name}${variant ? ', ' + variant : ''}`, 'ok');
  if ($('#cartDrawer')) paintDrawer();
}
function setQty(key, qty) {
  const [id, variant] = String(key).split('|');
  const p = state.catalog.products.find((x) => x.id === Number(id));
  if (!p) return;
  const limit = p.variants ? (p.variants.find((v) => v.label === variant)?.stock ?? 0) : p.stock;
  if (qty < 1) delete state.cart[key];
  else state.cart[key] = Math.min(qty, limit);
  saveCart();
  if ($('#cartDrawer')) paintDrawer();
  if (location.hash.startsWith('#/cart') || location.hash.startsWith('#/checkout')) route();
}
function paintCartCount() {
  const el = $('#cartCount');
  const n = cartCount();
  el.textContent = n;
  el.classList.toggle('hidden', n === 0);
}

/* ---------------- уведомления ---------------- */
function toast(msg, kind = '') {
  const host = $('#toasts');
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  host.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .2s'; }, 2400);
  setTimeout(() => el.remove(), 2700);
}

/* ---------------- шапка: категории ---------------- */
function paintCatnav() {
  const active = state.filters.cat || (location.hash.match(/cat=([a-z-]+)/) || [])[1] || '';
  $('#catnav').innerHTML = `
    <a href="#/catalog" class="${!active ? 'active' : ''}">✨ Все товары</a>
    ${state.catalog.categories.map((c) => `
      <a href="#/catalog?cat=${c.id}" class="${active === c.id ? 'active' : ''}">${c.emoji} ${esc(c.title)}</a>`).join('')}`;
}

/* ==========================================================================
   VIEWS
   ========================================================================== */
function viewHome() {
  const products = state.catalog.products;
  const fresh = products.slice(-8).reverse();
  const popularCats = [...state.catalog.categories];

  app.innerHTML = `
  <section class="hero"><div class="wrap"><div class="hero-grid">
    <div class="hero-main">
      <div>
        <h1>Полезные вещи<br>по честным ценам</h1>
        <p>${products.length} проверенных товаров для дома, кухни, авто и спорта. Доставка в удобный пункт выдачи Ozon — стоимость сразу видно в корзине.</p>
      </div>
      <div class="hero-cta">
        <a class="btn btn-light" href="#/catalog">Открыть каталог →</a>
        <a class="btn" style="border-color:rgba(255,255,255,.32);color:#fff" href="#/delivery">Как работает доставка</a>
      </div>
    </div>
    <div class="hero-side">
      <div class="hero-card"><div class="ic">📦</div><div><b>ПВЗ Ozon по всей РФ</b><p>Выбираете пункт при оформлении — видим точную стоимость и срок доставки</p></div></div>
      <div class="hero-card"><div class="ic">🧾</div><div><b>Чек на почту</b><p>Оплата картой, фискальный чек по 54-ФЗ приходит сразу после оплаты</p></div></div>
      <div class="hero-card"><div class="ic">🚚</div><div><b>Бесплатно от ${money(state.catalog.delivery.freeFrom)}</b><p>Доставка от ${money(state.catalog.delivery.base)} + ${money(state.catalog.delivery.perKg)} за каждый кг свыше 1 кг</p></div></div>
    </div>
  </div>
  <div class="trust">
    <div><span class="e">⚡</span> Отправка в день заказа</div>
    <div><span class="e">💳</span> Карта, СБП, чек по 54-ФЗ</div>
    <div><span class="e">↩️</span> Возврат 14 дней</div>
    <div><span class="e">🛡️</span> Гарантия 12 месяцев</div>
  </div>
  </div></section>

  <section class="section"><div class="wrap">
    <div class="section-head">
      <div><h2>Категории</h2><p>Восемь разделов — от электроники до туризма</p></div>
    </div>
    <div class="grid">
      ${state.catalog.categories.map((c) => {
        const count = products.filter((p) => p.category === c.id).length;
        return `<a class="card" href="#/catalog?cat=${c.id}">
          <div class="card-media" style="font-size:52px">${c.emoji}</div>
          <div class="card-body"><div class="card-name" style="min-height:auto">${esc(c.title)}</div>
          <div class="card-cat">${count} ${plural(count, 'товар', 'товара', 'товаров')}</div></div>
        </a>`;
      }).join('')}
    </div>
  </div></section>

  <section class="section"><div class="wrap">
    <div class="section-head"><div><h2>Все товары</h2><p>${products.length} позиций в наличии и под заказ</p></div>
    <a class="btn btn-ghost" href="#/catalog">Открыть каталог</a></div>
    <div class="grid">${products.slice(0, 8).map(cardHtml).join('')}</div>
  </div></section>

  <section class="section"><div class="wrap">
    <div class="section-head"><div><h2>Новинки</h2><p>Последние добавленные позиции</p></div>
    <a class="btn btn-ghost" href="#/catalog?sort=new">Все новинки</a></div>
    <div class="grid">${fresh.map(cardHtml).join('')}</div>
  </div></section>`;
}

function cardHtml(p) {
  const cat = state.catalog.categories.find((c) => c.id === p.category);
  const discount = p.oldPrice ? Math.round((1 - p.price / p.oldPrice) * 100) : 0;
  return `<article class="card">
    <a class="card-media" href="#/product/${p.slug}" aria-label="${esc(p.name)}">
      <div class="badges">
        ${p.badge ? `<span class="badge-tag ${p.badge === 'Хит' ? 'sale' : ''}">${p.badge}</span>` : ''}
        ${discount ? `<span class="badge-tag soft">−${discount}%</span>` : ''}
      </div>
      ${p.image ? `<img src="${esc(p.image)}" alt="${esc(p.name)}" loading="lazy">` : `<span class="emoji">${p.emoji}</span>`}
      ${!p.inStock ? '<div class="stock-out">Нет в наличии</div>' : ''}
    </a>
    <div class="card-body">
      <div class="card-cat">${esc(state.catalog.subcategories[p.subcategory] || '')}</div>
      <a class="card-name" href="#/product/${p.slug}">${esc(p.name)}</a>
      <div class="card-foot">
        <div><span class="price">${money(p.price)}</span>${p.oldPrice ? `<span class="price-old">${money(p.oldPrice)}</span>` : ''}</div>
        <button class="add-mini" data-add="${p.id}" ${!p.inStock ? 'disabled' : ''} title="В корзину" aria-label="Добавить в корзину">+</button>
      </div>
    </div>
  </article>`;
}

/* ---------------- каталог ---------------- */
function filteredProducts() {
  const f = state.filters;
  let list = [...state.catalog.products];
  if (f.cat) list = list.filter((p) => p.category === f.cat);
  if (f.sub) list = list.filter((p) => p.subcategory === f.sub);
  if (f.q) {
    const q = f.q.toLowerCase();
    list = list.filter((p) => (p.name + ' ' + p.description + ' ' + p.features.join(' ')).toLowerCase().includes(q));
  }
  if (f.min !== '') list = list.filter((p) => p.price >= Number(f.min));
  if (f.max !== '') list = list.filter((p) => p.price <= Number(f.max));
  if (f.instock) list = list.filter((p) => p.inStock);
  const sorters = {
    popular: (a, b) => (b.reviews * b.rating) - (a.reviews * a.rating),
    price_asc: (a, b) => a.price - b.price,
    price_desc: (a, b) => b.price - a.price,
    new: (a, b) => b.id - a.id,
    discount: (a, b) => (b.oldPrice ? 1 - b.price / b.oldPrice : 0) - (a.oldPrice ? 1 - a.price / a.oldPrice : 0),
  };
  return list.sort(sorters[f.sort] || sorters.popular);
}

function viewCatalog() {
  const f = state.filters;
  const list = filteredProducts();
  const cats = state.catalog.categories;
  const activeCat = cats.find((c) => c.id === f.cat);
  const subs = activeCat ? activeCat.subcategories : [];

  app.innerHTML = `<div class="page"><div class="wrap">
    <div class="crumbs"><a href="#/">Главная</a> / <span>${activeCat ? esc(activeCat.title) : 'Каталог'}</span></div>
    <div class="section-head" style="margin-bottom:22px">
      <div>
        <h1 style="font-size:clamp(24px,3vw,32px)">${activeCat ? activeCat.emoji + ' ' + esc(activeCat.title) : 'Все товары'}</h1>
        <p>${list.length} ${plural(list.length, 'товар', 'товара', 'товаров')}${f.q ? ` по запросу «${esc(f.q)}»` : ''}</p>
      </div>
    </div>

    <div class="catalog-layout">
      <aside class="filters">
        <div class="filter-card">
          <h4>Разделы</h4>
          <div class="filter-list">
            <button data-cat="" class="${!f.cat ? 'active' : ''}">Все категории <span class="count">${state.catalog.products.length}</span></button>
            ${cats.map((c) => {
              const n = state.catalog.products.filter((p) => p.category === c.id).length;
              const isOpen = f.cat === c.id;
              return `<button data-cat="${c.id}" class="${isOpen ? 'active' : ''}">${c.emoji} ${esc(c.title)} <span class="count">${n}</span></button>
                ${isOpen ? c.subcategories.map((s) => {
                  const sn = state.catalog.products.filter((p) => p.subcategory === s).length;
                  if (!sn) return '';
                  return `<button class="sub ${f.sub === s ? 'active' : ''}" data-sub="${s}">${esc(state.catalog.subcategories[s])} <span class="count">${sn}</span></button>`;
                }).join('') : ''}`;
            }).join('')}
          </div>
        </div>
        <div class="filter-card">
          <h4>Цена, ₽</h4>
          <div class="price-row">
            <input type="number" id="fMin" placeholder="от" value="${f.min}" min="0" inputmode="numeric">
            <span class="muted">—</span>
            <input type="number" id="fMax" placeholder="до" value="${f.max}" min="0" inputmode="numeric">
          </div>
        </div>
        <div class="filter-card">
          <h4>Наличие</h4>
          <label class="switch"><input type="checkbox" id="fStock" ${f.instock ? 'checked' : ''}> Только в наличии</label>
        </div>
      </aside>

      <div>
        <div class="toolbar">
          <div class="found">${list.length} ${plural(list.length, 'товар', 'товара', 'товаров')}</div>
          <select class="select" id="fSort">
            <option value="popular" ${f.sort === 'popular' ? 'selected' : ''}>Сначала популярные</option>
            <option value="price_asc" ${f.sort === 'price_asc' ? 'selected' : ''}>Сначала дешёвые</option>
            <option value="price_desc" ${f.sort === 'price_desc' ? 'selected' : ''}>Сначала дорогие</option>
            <option value="discount" ${f.sort === 'discount' ? 'selected' : ''}>Больше скидка</option>
            <option value="new" ${f.sort === 'new' ? 'selected' : ''}>Новинки</option>
          </select>
        </div>
        ${list.length ? `<div class="grid">${list.map(cardHtml).join('')}</div>` : `
          <div class="empty-state"><div class="e">🔍</div><h3>Ничего не найдено</h3>
          <p class="muted" style="margin-top:8px">Попробуйте изменить фильтры или поискать другое слово.</p>
          <button class="btn btn-ghost" style="margin-top:18px" data-reset>Сбросить фильтры</button></div>`}
      </div>
    </div>
  </div></div>`;

  // события фильтров
  $$('[data-cat]').forEach((b) => b.onclick = () => {
    const cat = b.dataset.cat;
    state.filters.cat = cat;
    state.filters.sub = '';
    navigate(`#/catalog${cat ? '?cat=' + cat : ''}`);
    route();
  });
  $$('[data-sub]').forEach((b) => b.onclick = () => {
    state.filters.sub = state.filters.sub === b.dataset.sub ? '' : b.dataset.sub;
    route();
  });
  const applyPrice = () => {
    state.filters.min = $('#fMin').value;
    state.filters.max = $('#fMax').value;
    route();
  };
  $('#fMin').onchange = applyPrice; $('#fMax').onchange = applyPrice;
  $('#fStock').onchange = (e) => { state.filters.instock = e.target.checked; route(); };
  $('#fSort').onchange = (e) => { state.filters.sort = e.target.value; route(); };
  const reset = $('[data-reset]');
  if (reset) reset.onclick = () => { state.filters = { ...state.filters, cat: '', sub: '', q: '', min: '', max: '', instock: false }; navigate('#/catalog'); route(); };
}

/* ---------------- карточка товара ---------------- */
function viewProduct(slug) {
  const p = state.catalog.products.find((x) => x.slug === slug);
  if (!p) { app.innerHTML = `<div class="page"><div class="wrap"><div class="empty-state"><div class="e">🫥</div><h3>Товар не найден</h3><a class="btn btn-primary" style="margin-top:16px" href="#/catalog">В каталог</a></div></div></div>`; return; }
  const cat = state.catalog.categories.find((c) => c.id === p.category);
  const sub = state.catalog.subcategories[p.subcategory] || '';
  const discount = p.oldPrice ? Math.round((1 - p.price / p.oldPrice) * 100) : 0;
  const related = state.catalog.products.filter((x) => x.category === p.category && x.id !== p.id).slice(0, 4);

  app.innerHTML = `<div class="product"><div class="wrap">
    <div class="crumbs"><a href="#/">Главная</a> / <a href="#/catalog?cat=${cat.id}">${esc(cat.title)}</a> / <a href="#/catalog?cat=${cat.id}">${esc(sub)}</a> / <span>${esc(p.name)}</span></div>
    <div class="product-grid">
      <div class="product-media">${p.image ? `<img src="${esc(p.image)}" alt="${esc(p.name)}">` : `<span class="emoji">${p.emoji}</span>`}<span class="watermark">ПОЛКА · ${esc(sub)}</span></div>
      <div class="product-info">
        <div style="margin-bottom:8px;font-size:13px;color:${p.inStock ? 'var(--ok)' : 'var(--sale)'}">${p.inStock ? 'В наличии: ' + p.stock + ' шт.' : 'Нет в наличии'}</div>
        <h1>${esc(p.name)}</h1>
        <div class="product-price">
          <span class="price">${money(p.price)}</span>
          ${p.oldPrice ? `<span class="price-old" style="font-size:18px">${money(p.oldPrice)}</span>` : ''}
          ${discount ? `<span class="discount">−${discount}%</span>` : ''}
        </div>
        <p class="muted small">или ${money(p.price / 4)} × 4 платежа без процентов</p>

        <ul class="features">${p.features.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>

        <div class="buy-box">
          ${p.variants ? `<div class="variant-block">
            <div class="variant-label">Размер: <b id="variantPicked">выберите</b></div>
            <div class="variant-list" id="variantList">
              ${p.variants.map((v) => `<button type="button" class="variant-btn ${v.stock === 0 ? 'disabled' : ''}" data-variant="${esc(v.label)}" ${v.stock === 0 ? 'disabled' : ''} title="${v.stock > 0 ? 'в наличии ' + v.stock + ' шт.' : 'нет в наличии'}">${esc(v.label)}</button>`).join('')}
            </div>
          </div>` : ''}
          <div class="buy-row">
            <div class="qty">
              <button data-q="-1" aria-label="Меньше">−</button>
              <span id="qtyVal">1</span>
              <button data-q="1" aria-label="Больше">+</button>
            </div>
            <button class="btn btn-primary btn-lg" id="addBtn" ${!p.inStock ? 'disabled' : ''}>${p.inStock ? 'Добавить в корзину' : 'Нет в наличии'}</button>
          </div>
          <div class="deliv-note"><span class="e">📦</span>
            <div>Доставка в ПВЗ Ozon: <b>от ${money(state.catalog.delivery.base)}</b>, срок 2–${state.catalog.delivery.maxDays} дня. Точная стоимость рассчитывается после выбора пункта выдачи.<br>
            Бесплатно при заказе от ${money(state.catalog.delivery.freeFrom)}.</div>
          </div>
        </div>
      </div>
    </div>

    <div class="desc-block">
      <div>
        <h3>Описание</h3>
        <p style="margin-top:12px">${esc(p.description)}</p>
        <p style="margin-top:14px" class="muted small">Отправляем со склада в течение 24 часов. Упаковываем в защитную плёнку и коробку. Если товар не подошёл — вернуть можно в течение 14 дней с момента получения в ПВЗ.</p>
      </div>
      <div class="spec">
        <h3 style="font-size:15px">Характеристики</h3>
        <dl>
          <dt>Артикул</dt><dd>PLK-${String(p.id).padStart(4, '0')}</dd>
          <dt>Раздел</dt><dd>${esc(cat.title)}</dd>
          <dt>Подраздел</dt><dd>${esc(sub)}</dd>
          <dt>Вес</dt><dd>${p.weight} кг</dd>
          <dt>Остаток</dt><dd>${p.stock} шт.</dd>
          <dt>Гарантия</dt><dd>12 месяцев</dd>
          <dt>Доставка</dt><dd>ПВЗ Ozon</dd>
        </dl>
      </div>
    </div>

    ${related.length ? `<section class="section"><div class="section-head"><h2>Похожие товары</h2></div>
      <div class="grid">${related.map(cardHtml).join('')}</div></section>` : ''}
  </div></div>`;

  let qty = 1;
  let chosen = null;
  const variantStock = () => (p.variants ? (p.variants.find((v) => v.label === chosen)?.stock ?? 0) : p.stock);
  $$('[data-q]').forEach((b) => b.onclick = () => {
    qty = Math.max(1, Math.min(variantStock() || 1, qty + Number(b.dataset.q)));
    $('#qtyVal').textContent = qty;
  });
  if (p.variants) {
    $$('[data-variant]').forEach((b) => b.onclick = () => {
      chosen = b.dataset.variant;
      $$('[data-variant]').forEach((x) => x.classList.toggle('active', x === b));
      $('#variantPicked').textContent = chosen;
      qty = 1;
      $('#qtyVal').textContent = qty;
    });
  }
  $('#addBtn').onclick = () => {
    if (p.variants && !chosen) { toast('Выберите размер', 'err'); return; }
    addToCart(p.id, qty, chosen);
    openDrawer();
  };
}

/* ---------------- корзина (страница) ---------------- */
function viewCart() {
  const items = cartItems();
  if (!items.length) {
    app.innerHTML = `<div class="page"><div class="wrap"><div class="empty-state">
      <div class="e">🛍️</div><h2>Корзина пуста</h2>
      <p class="muted" style="margin-top:10px">Загляните в каталог — там 100 полезных вещей.</p>
      <a class="btn btn-primary btn-lg" style="margin-top:22px" href="#/catalog">Перейти в каталог</a>
    </div></div></div>`;
    return;
  }
  const sum = cartSum();
  app.innerHTML = `<div class="page"><div class="wrap">
    <div class="crumbs"><a href="#/">Главная</a> / <span>Корзина</span></div>
    <h1 style="font-size:clamp(24px,3vw,32px);margin-bottom:20px">Корзина</h1>
    <div class="two-col">
      <div>
        <div class="panel">
          ${items.map((i) => `<div class="cart-line">
            <a class="cart-thumb" href="#/product/${i.slug}">${i.image ? `<img src="${esc(i.image)}" alt="">` : i.emoji}</a>
            <div>
              <a class="name" href="#/product/${i.slug}">${esc(i.name)}</a>
              <div class="meta">${i.variant ? `<b>${esc(i.variant)}</b> · ` : ''}${money(i.price)} · ${i.weight} кг</div>
              <div style="margin-top:8px;display:flex;gap:14px;align-items:center">
                <div class="qty"><button data-dec="${i.key}">−</button><span>${i.qty}</span><button data-inc="${i.key}">+</button></div>
                <button class="remove" data-del="${i.key}">Удалить</button>
              </div>
            </div>
            <div style="text-align:right"><div class="price" style="font-size:17px">${money(i.price * i.qty)}</div></div>
          </div>`).join('')}
        </div>
        <div class="hint">💡 Товар резервируется на 30 минут после оформления. Не успели оплатить — остаток вернётся на склад, заказ можно оформить заново.</div>
      </div>
      <div class="summary">
        <div class="panel">
          <h3>Итого</h3>
          <div style="margin-top:14px">
            <div class="sum-row"><span>Товары (${cartCount()})</span><span class="v">${money(sum)}</span></div>
            <div class="sum-row"><span>Доставка в ПВЗ</span><span class="v muted">рассчитаем при оформлении</span></div>
            <div class="sum-row total"><span>К оплате</span><span class="v">${money(sum)}</span></div>
          </div>
          <a class="btn btn-primary btn-block btn-lg" style="margin-top:16px" href="#/checkout">Оформить заказ</a>
          <a class="btn btn-ghost btn-block" style="margin-top:10px" href="#/catalog">Продолжить покупки</a>
          <p class="legal">Оплата картой или СБП. Чек по 54-ФЗ приходит на email сразу после оплаты.</p>
        </div>
      </div>
    </div>
  </div></div>`;

  $$('[data-inc]').forEach((b) => b.onclick = () => { const k = b.dataset.inc; setQty(k, (state.cart[k] || 0) + 1); });
  $$('[data-dec]').forEach((b) => b.onclick = () => { const k = b.dataset.dec; setQty(k, (state.cart[k] || 0) - 1); });
  $$('[data-del]').forEach((b) => b.onclick = () => { setQty(b.dataset.del, 0); toast('Товар удалён'); });
}

/* ---------------- оформление ---------------- */
async function viewCheckout() {
  const items = cartItems();
  if (!items.length) { navigate('#/cart'); return; }

  app.innerHTML = `<div class="page"><div class="wrap">
    <div class="crumbs"><a href="#/cart">Корзина</a> / <span>Оформление</span></div>
    <h1 style="font-size:clamp(24px,3vw,32px);margin-bottom:16px">Оформление заказа</h1>
    <div class="steps">
      <div class="step-pill current" id="pill1"><b>1</b> Контакты</div>
      <div class="step-pill" id="pill2"><b>2</b> Пункт выдачи</div>
      <div class="step-pill" id="pill3"><b>3</b> Оплата</div>
    </div>
    <div class="two-col">
      <div>
        <div class="panel">
          <h3>1. Контакты получателя</h3>
          <p class="muted small" style="margin:6px 0 16px">На телефон придёт SMS с кодом получения, на email — чек.</p>
          <div class="field-row">
            <div class="field"><label for="cName">Имя и фамилия *</label><input id="cName" autocomplete="name" placeholder="Анна Иванова"></div>
            <div class="field"><label for="cPhone">Телефон *</label><input id="cPhone" inputmode="tel" autocomplete="tel" placeholder="+7 900 000-00-00"></div>
          </div>
          <div class="field"><label for="cEmail">Email для чека</label><input id="cEmail" type="email" autocomplete="email" placeholder="you@mail.ru"></div>
          <div class="field" style="margin-bottom:0"><label for="cComment">Комментарий к заказу</label><textarea id="cComment" rows="2" placeholder="Необязательно"></textarea></div>
        </div>

        <div class="panel">
          <h3>2. Пункт выдачи Ozon</h3>
          <p class="muted small" style="margin:6px 0 14px">Выберите город и удобный ПВЗ — стоимость доставки пересчитается автоматически.</p>
          <div class="pvz-tools">
            <select id="pvzCity"></select>
            <input id="pvzSearch" placeholder="Улица или район" autocomplete="off">
          </div>
          <div class="pvz-list" id="pvzList"><div class="skeleton" style="height:64px"></div><div class="skeleton" style="height:64px"></div></div>
          <div id="pvzChosen" class="hint hidden" style="background:var(--ok-soft);border-color:#bfe6d5;color:#0f6b4b"></div>
        </div>

        <div class="panel">
          <h3>3. Оплата</h3>
          <p class="muted small" style="margin:6px 0 14px">Платёж проходит на защищённой странице банка. Данные карты не попадают на наш сервер.</p>
          <div style="display:grid;gap:8px">
            <label class="pay-option selected" data-pay="card">
              <span class="radio">✓</span>
              <div><b>Банковская карта</b><span>Visa, Mastercard, МИР · чек на email</span></div>
            </label>
            <label class="pay-option" data-pay="sbp">
              <span class="radio"></span>
              <div><b>СБП</b><span>Оплата по QR-коду в приложении банка · без комиссии</span></div>
            </label>
          </div>
          <p class="legal">Нажимая «Оплатить заказ», вы соглашаетесь с <a href="#/legal#offer" style="text-decoration:underline">публичной офертой</a> и <a href="#/legal#privacy" style="text-decoration:underline">политикой конфиденциальности</a>.</p>
        </div>
      </div>

      <div class="summary">
        <div class="panel">
          <h3>Ваш заказ</h3>
          <div style="margin-top:12px;max-height:290px;overflow-y:auto">
            ${items.map((i) => `<div style="display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--line)">
              <div class="cart-thumb" style="width:46px;height:46px;font-size:20px;border-radius:10px">${i.emoji}</div>
              <div style="flex:1;min-width:0"><div class="small" style="font-weight:550">${esc(i.name)}</div><div class="tiny muted">${i.variant ? 'Размер ' + esc(i.variant) + ' · ' : ''}${i.qty} × ${money(i.price)}</div></div>
              <div class="small nowrap" style="font-variant-numeric:tabular-nums">${money(i.price * i.qty)}</div>
            </div>`).join('')}
          </div>
          <div id="summaryBox" style="margin-top:14px">
            <div class="sum-row"><span>Товары (${cartCount()})</span><span class="v">${money(cartSum())}</span></div>
            <div class="sum-row"><span>Доставка</span><span class="v muted" id="delivVal">выберите ПВЗ</span></div>
            <div class="sum-row total"><span>Итого</span><span class="v" id="totalVal">${money(cartSum())}</span></div>
          </div>
          <div id="delivDetails"></div>
          <button class="btn btn-primary btn-block btn-lg" id="payBtn" style="margin-top:16px">Оплатить заказ</button>
          <p class="legal" id="payHint">Сначала выберите пункт выдачи — добавим стоимость доставки.</p>
        </div>
      </div>
    </div>
  </div></div>`;

  // --- ПВЗ ---
  const citySel = $('#pvzCity');
  const pvzList = $('#pvzList');
  const searchInput = $('#pvzSearch');
  let pvzCache = [];

  const pvzHtml = (p) => `<button type="button" class="pvz-item ${state.checkout.pvz?.id === p.id ? 'selected' : ''}" data-pvz="${p.id}">
      <span class="e">${p.icon || '📦'}</span>
      <span><b>${esc(p.address)}</b><span>${esc(p.city)} · ${esc(p.type)} · ${esc(p.workHours)}</span></span>
      <span class="radio">✓</span>
    </button>`;

  async function loadPvz() {
    pvzList.innerHTML = '<div class="skeleton" style="height:64px"></div><div class="skeleton" style="height:64px"></div>';
    try {
      const q = new URLSearchParams();
      if (citySel.value) q.set('city', citySel.value);
      if (searchInput.value.trim()) q.set('q', searchInput.value.trim());
      const data = await api('/api/pvz?' + q);
      pvzCache = data.points;
      pvzList.innerHTML = data.points.length ? data.points.map(pvzHtml).join('') :
        '<p class="muted small" style="padding:14px">Ничего не найдено. Попробуйте другой город или улицу.</p>';
      $$('[data-pvz]', pvzList).forEach((b) => b.onclick = () => selectPvz(pvzCache.find((x) => x.id === b.dataset.pvz)));
    } catch (e) {
      pvzList.innerHTML = `<p class="muted small" style="padding:14px">Не удалось загрузить пункты выдачи: ${esc(e.message)}</p>`;
    }
  }

  async function selectPvz(p) {
    if (!p) return;
    state.checkout.pvz = p;
    state.pvzCity = citySel.value || p.city;
    localStorage.setItem('polka_pvz', JSON.stringify(p));
    localStorage.setItem('polka_city', state.pvzCity);
    $$('[data-pvz]', pvzList).forEach((b) => b.classList.toggle('selected', b.dataset.pvz === p.id));
    $('#pvzChosen').classList.remove('hidden');
    $('#pvzChosen').innerHTML = `✅ Выбран пункт: <b>${esc(p.city)}, ${esc(p.address)}</b><br><span class="tiny">${esc(p.type)} · ${esc(p.workHours)} · ${esc(p.maxDimension)}</span>`;
    $('#pill2').classList.add('done');
    await recalc();
  }

  async function recalc() {
    const ids = items.map((i) => ({ id: i.id, qty: i.qty, variant: i.variant || null }));
    $('#delivVal').textContent = 'считаем…';
    try {
      const q = await api('/api/quote', { method: 'POST', body: JSON.stringify({ items: ids, pvzId: state.checkout.pvz?.id }) });
      state.quote = q;
      $('#delivVal').innerHTML = q.delivery.ok
        ? (q.delivery.free ? '<span class="free">Бесплатно</span>' : money(q.delivery.price))
        : '<span class="muted">выберите ПВЗ</span>';
      $('#totalVal').textContent = money(q.total);
      $('#delivDetails').innerHTML = q.delivery.ok ? `<div class="delivery-card" style="margin-top:12px">
          <div class="row"><span class="muted">Способ</span><span>ПВЗ Ozon · ${esc(q.pvz.address)}</span></div>
          <div class="row"><span class="muted">Срок</span><span>${q.delivery.days} дней</span></div>
          <div class="row"><span class="muted">Вес заказа</span><span>${q.delivery.weight} кг</span></div>
          <div class="row"><span class="muted">Доставка</span><span>${q.delivery.free ? '<span class="free">0 ₽</span>' : money(q.delivery.price)}</span></div>
        </div>` : '';
      $('#payBtn').textContent = `Оплатить ${money(q.total)}`;
      $('#payHint').textContent = q.delivery.ok
        ? 'Чек придёт на email сразу после оплаты.'
        : 'Сначала выберите пункт выдачи — добавим стоимость доставки.';
    } catch (e) {
      toast(e.message, 'err');
      $('#delivVal').textContent = '—';
    }
  }

  // города
  try {
    const cities = await api('/api/pvz');
    if (!state.pvzCity) state.pvzCity = cities.cities.includes('Москва') ? 'Москва' : cities.cities[0];
    citySel.innerHTML = cities.cities.map((c) => `<option value="${esc(c)}" ${c === state.pvzCity ? 'selected' : ''}>${esc(c)}</option>`).join('');
    if (state.pvz && state.pvz.city) {
      state.checkout.pvz = state.pvz;
    }
    await loadPvz();
    if (state.checkout.pvz) await recalc();
  } catch (e) { toast(e.message, 'err'); }

  let searchTimer;
  searchInput.oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(loadPvz, 300); };
  citySel.onchange = () => { state.pvzCity = citySel.value; localStorage.setItem('polka_city', citySel.value); loadPvz(); };

  // способ оплаты
  $$('[data-pay]').forEach((el) => el.onclick = () => {
    $$('[data-pay]').forEach((x) => { x.classList.remove('selected'); $('.radio', x).textContent = ''; });
    el.classList.add('selected');
    $('.radio', el).textContent = '✓';
    state.checkout.pay = el.dataset.pay;
  });

  // восстановление контактов
  const saved = JSON.parse(localStorage.getItem('polka_contacts') || '{}');
  $('#cName').value = saved.name || '';
  $('#cPhone').value = saved.phone || '';
  $('#cEmail').value = saved.email || '';

  // подсветка шага 1
  const markStep1 = () => {
    const ok = $('#cName').value.trim().length > 2 && $('#cPhone').value.replace(/\D/g, '').length >= 10;
    $('#pill1').classList.toggle('done', ok);
    $('#pill1').classList.toggle('current', !ok);
    return ok;
  };
  ['#cName', '#cPhone'].forEach((s) => $(s).oninput = markStep1);
  markStep1();

  // отправка
  $('#payBtn').onclick = async () => {
    if (state.checkout.sending) return;
    const name = $('#cName').value.trim();
    const phone = $('#cPhone').value.trim();
    const email = $('#cEmail').value.trim();
    if (name.length < 2) { toast('Укажите имя получателя', 'err'); $('#cName').focus(); return; }
    if (phone.replace(/\D/g, '').length < 10) { toast('Укажите корректный телефон', 'err'); $('#cPhone').focus(); return; }
    if (!state.checkout.pvz) { toast('Выберите пункт выдачи', 'err'); $('#pvzList').scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }

    localStorage.setItem('polka_contacts', JSON.stringify({ name, phone, email }));
    state.checkout.sending = true;
    const btn = $('#payBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Создаём заказ…';
    try {
      const payload = {
        items: items.map((i) => ({ id: i.id, qty: i.qty, variant: i.variant || null })),
        pvzId: state.checkout.pvz.id,
        customer: { name, phone, email },
        comment: $('#cComment').value.trim(),
      };
      const res = await api('/api/orders', { method: 'POST', body: JSON.stringify(payload) });
      state.cart = {};
      saveCart();
      localStorage.setItem('polka_last_order', res.order.number);
      if (res.payment?.payUrl && /^https?:/.test(res.payment.payUrl)) {
        location.href = res.payment.payUrl;
      } else {
        navigate(`#/order?number=${res.order.number}`);
      }
    } catch (e) {
      toast(e.message, 'err');
      btn.disabled = false;
      btn.textContent = 'Оплатить заказ';
      state.checkout.sending = false;
    }
  };
}

/* ---------------- страница заказа ---------------- */
async function viewOrder(number) {
  app.innerHTML = `<div class="page"><div class="wrap"><div class="skeleton" style="height:280px"></div></div></div>`;
  let data;
  try { data = await api('/api/orders/' + encodeURIComponent(number)); }
  catch (e) {
    app.innerHTML = `<div class="page"><div class="wrap"><div class="empty-state"><div class="e">🧾</div><h3>Заказ не найден</h3><p class="muted" style="margin-top:8px">${esc(e.message)}</p><a class="btn btn-primary" style="margin-top:16px" href="#/catalog">В каталог</a></div></div></div>`;
    return;
  }
  const o = data.order;
  const steps = [
    ['awaiting_payment', 'Ожидает оплаты', 'Как только оплата пройдёт, мы начнём собирать заказ'],
    ['paid', 'Оплачен', 'Чек отправлен на email, заказ попал на склад'],
    ['packing', 'Собирается', 'Упаковываем и передаём в Ozon'],
    ['shipped', 'В пути', 'Едет в выбранный ПВЗ, придёт SMS с кодом'],
    ['delivered', 'Получен', 'Заберите заказ в пункте выдачи'],
  ];
  const idx = Math.max(0, steps.findIndex(([s]) => s === o.status));
  const cancelled = o.status === 'cancelled';
  const cfg = state.catalog ? state.catalog : { delivery: { maxDays: 7 } };

  app.innerHTML = `<div class="page"><div class="wrap" style="max-width:860px">
    <div class="success-hero">
      <div class="checkmark">${cancelled ? '✕' : '✓'}</div>
      <h1 style="font-size:clamp(24px,3.4vw,34px)">${cancelled ? 'Заказ отменён' : `Заказ ${esc(o.number)} оформлен`}</h1>
      <p class="muted" style="margin-top:10px">${cancelled ? 'Деньги вернутся тем же способом в течение 3–5 дней.' : 'Мы отправили детали на ' + esc(o.customer.email || o.customer.phone) + '. Ниже — статус и состав заказа.'}</p>
    </div>

    ${!cancelled ? `<div class="panel" style="margin-top:24px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
        <div><h3>Статус: ${esc(o.statusLabel)}</h3><p class="muted small">Оформлен ${new Date(o.createdAt).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })}</p></div>
        <div class="badge-tag ${o.status === 'paid' ? 'sale' : ''}" style="background:${o.status === 'awaiting_payment' ? 'var(--warn)' : 'var(--ok)'}">${esc(o.statusLabel)}</div>
      </div>
      <div class="timeline" style="margin-top:22px">
        ${steps.map(([s, title, sub], i) => `<div class="tl-item ${i <= idx ? 'active' : ''}">
          <div class="tl-dot">${i < idx ? '✓' : i + 1}</div>
          <div><b>${title}</b><p>${sub}</p></div>
        </div>`).join('')}
      </div>
      ${o.status === 'awaiting_payment' ? `<button class="btn btn-primary btn-lg btn-block" id="demoPay">Оплатить ${money(o.total)}</button>
        <p class="legal">Демо-режим: реальный платёж не списывается. После подключения ЮKassa / CloudPayments здесь будет кнопка перехода на страницу банка.</p>` : ''}
    </div>` : ''}

    <div class="panel" style="margin-top:16px">
      <h3>Состав заказа</h3>
      <div style="margin-top:12px">
        ${o.items.map((i) => `<div style="display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--line)">
          <span>${esc(i.name)} <span class="muted small">× ${i.qty}</span></span>
          <span class="nowrap">${money(i.price * i.qty)}</span></div>`).join('')}
      </div>
      <div style="margin-top:14px">
        <div class="sum-row"><span>Товары</span><span class="v">${money(o.subtotal)}</span></div>
        <div class="sum-row"><span>Доставка (ПВЗ Ozon)</span><span class="v">${o.deliveryPrice ? money(o.deliveryPrice) : 'Бесплатно'}</span></div>
        <div class="sum-row total"><span>Итого</span><span class="v">${money(o.total)}</span></div>
      </div>
    </div>

    <div class="panel" style="margin-top:16px">
      <h3>Получение</h3>
      <div class="delivery-card" style="margin-top:12px">
        <div class="row"><span class="muted">Пункт выдачи</span><span>${esc(o.pvz.city)}, ${esc(o.pvz.address)}</span></div>
        <div class="row"><span class="muted">Тип</span><span>${esc(o.pvz.type)} · ${esc(o.pvz.workHours)}</span></div>
        <div class="row"><span class="muted">Получатель</span><span>${esc(o.customer.name)}, ${esc(o.customer.phone)}</span></div>
        <div class="row"><span class="muted">Срок доставки</span><span>2–${cfg.delivery?.maxDays || 7} дня</span></div>
      </div>
      <p class="legal">Возврат в течение 14 дней с момента получения. Для возврата напишите на почту поддержки и укажите номер заказа.</p>
    </div>

    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:20px">
      <a class="btn btn-primary" href="#/catalog">Продолжить покупки</a>
      <a class="btn btn-ghost" href="#/delivery">Доставка и оплата</a>
    </div>
  </div></div>`;

  const payBtn = $('#demoPay');
  if (payBtn) payBtn.onclick = async () => {
    payBtn.disabled = true;
    payBtn.innerHTML = '<span class="spinner"></span> Проводим платёж…';
    try {
      await api(`/api/orders/${encodeURIComponent(o.number)}/demo-pay`, { method: 'POST', body: '{}' });
      toast('Оплата прошла, чек отправлен', 'ok');
      route();
    } catch (e) { toast(e.message, 'err'); payBtn.disabled = false; payBtn.textContent = 'Оплатить'; }
  };
}

/* ---------------- информационные страницы ---------------- */
function viewDelivery() {
  const d = state.catalog.delivery;
  app.innerHTML = `<div class="page"><div class="wrap" style="max-width:900px">
    <div class="crumbs"><a href="#/">Главная</a> / <span>Доставка и оплата</span></div>
    <h1 style="font-size:clamp(24px,3.2vw,34px)">Доставка и оплата</h1>
    <p class="muted" style="margin-top:10px;max-width:60ch">Мы отправляем заказы через Ozon Доставку в пункты выдачи по всей России. Стоимость доставки рассчитывается автоматически, когда вы выбираете ПВЗ при оформлении.</p>

    <div class="two-col" style="grid-template-columns:1fr 1fr;margin-top:26px">
      <div class="panel"><h3>📦 Как считается доставка</h3>
        <ul style="margin-top:12px;padding-left:0;list-style:none;display:grid;gap:10px;font-size:14.5px">
          <li>Базовая стоимость — <b>${money(d.base)}</b> до пункта выдачи</li>
          <li>Плюс <b>${money(d.perKg)}</b> за каждый килограмм свыше 1 кг</li>
          <li>Бесплатно при заказе от <b>${money(d.freeFrom)}</b></li>
          <li>Срок — от 2 до ${d.maxDays} дней в зависимости от региона</li>
        </ul>
        <p class="muted small" style="margin-top:14px">Стоимость видна в корзине и на шаге оформления — до оплаты. Никаких доплат при получении.</p>
      </div>
      <div class="panel"><h3>💳 Оплата и чек</h3>
        <ul style="margin-top:12px;padding-left:0;list-style:none;display:grid;gap:10px;font-size:14.5px">
          <li>Банковские карты Visa, Mastercard, МИР</li>
          <li>СБП — по QR-коду из приложения банка</li>
          <li>Данные карты обрабатывает платёжный сервис, мы их не видим</li>
          <li>Фискальный чек по 54-ФЗ приходит на email сразу после оплаты</li>
        </ul>
      </div>
    </div>

    <div class="panel" style="margin-top:16px" id="faq">
      <h3>Частые вопросы</h3>
      <div style="display:grid;gap:16px;margin-top:14px">
        ${[
          ['Можно ли примерить или проверить товар?', 'Да, в пункте выдачи можно осмотреть заказ до подписания. Если что-то не подошло — сразу откажитесь, деньги вернутся на карту.'],
          ['Сколько идёт доставка?', 'Обычно 2–' + d.maxDays + ' дня. Точный срок показывается при выборе ПВЗ. В отдалённые регионы может занять до 10 дней.'],
          ['Что если товар пришёл с браком?', 'Напишите нам в течение 14 дней с фото — заменим товар или вернём деньги, доставку в этом случае оплачиваем мы.'],
          ['Нужен ли паспорт при получении?', 'Для заказов до 10 000 ₽ достаточно кода из SMS. Для крупных заказов сотрудник ПВЗ может попросить документ.'],
        ].map(([q, a]) => `<div><b>${q}</b><p class="muted small" style="margin-top:4px">${a}</p></div>`).join('')}
      </div>
    </div>

    <div class="panel" style="margin-top:16px" id="return">
      <h3>Возврат</h3>
      <p class="muted small" style="margin-top:8px">Товар надлежащего качества можно вернуть в течение 14 дней, если он не был в использовании, сохранены упаковка и комплектация. Возврат денег — на карту в течение 3–5 рабочих дней после получения товара на складе.</p>
    </div>
  </div></div>`;
}

function viewLegal() {
  app.innerHTML = `<div class="page"><div class="wrap" style="max-width:820px">
    <div class="crumbs"><a href="#/">Главная</a> / <span>Документы</span></div>
    <h1 style="font-size:clamp(24px,3.2vw,32px)">Документы</h1>
    <div class="panel" style="margin-top:20px" id="offer">
      <h3>Публичная оферта</h3>
      <p class="small" style="margin-top:10px;color:var(--ink-2)">Настоящий документ является предложением ${esc(state.catalog.shop.seller)} (ИНН ${esc(state.catalog.shop.inn)}) заключить договор купли-продажи товаров на изложенных ниже условиях. Оформляя заказ, покупатель подтверждает согласие с условиями оферты, составом заказа, ценой и способом доставки.</p>
      <p class="small" style="margin-top:10px;color:var(--ink-2)">Цены указаны в рублях РФ. Продавец вправе изменять цены до момента оформления заказа. Оплата производится в полном объёме в момент оформления. Доставка осуществляется через пункты выдачи Ozon, выбранные покупателем при оформлении.</p>
    </div>
    <div class="panel" style="margin-top:16px" id="privacy">
      <h3>Политика конфиденциальности</h3>
      <p class="small" style="margin-top:10px;color:var(--ink-2)">Мы обрабатываем имя, телефон, email и адрес пункта выдачи исключительно для исполнения заказа и передачи данных в службу доставки. Данные банковской карты обрабатываются платёжным провайдером и не хранятся у нас. По запросу на почту поддержки мы удалим ваши персональные данные в течение 30 дней.</p>
    </div>
    <div class="panel" style="margin-top:16px" id="terms">
      <h3>Условия возврата</h3>
      <p class="small" style="margin-top:10px;color:var(--ink-2)">Возврат товара надлежащего качества — в течение 14 дней с момента получения при сохранении упаковки и комплектации. Товар с браком меняется или возвращается без ограничения срока при подтверждении недостатка.</p>
    </div>
  </div></div>`;
}

/* ---------------- корзина-шторка ---------------- */
function openDrawer() {
  if ($('#cartDrawer')) return;
  const items = cartItems();
  const backdrop = document.createElement('div');
  backdrop.className = 'drawer-backdrop';
  backdrop.onclick = closeDrawer;
  const drawer = document.createElement('aside');
  drawer.className = 'cart-drawer';
  drawer.id = 'cartDrawer';
  drawer.innerHTML = `<header><b>Корзина</b><button class="close-x" aria-label="Закрыть">×</button></header>
    <div class="body" id="drawerBody"></div>
    <footer id="drawerFoot"></footer>`;
  document.body.append(backdrop, drawer);
  $('.close-x', drawer).onclick = closeDrawer;
  document.body.style.overflow = 'hidden';
  paintDrawer();
}
function closeDrawer() {
  $('#cartDrawer')?.remove();
  $('.drawer-backdrop')?.remove();
  document.body.style.overflow = '';
}
function paintDrawer() {
  const items = cartItems();
  const body = $('#drawerBody');
  const foot = $('#drawerFoot');
  if (!body) return;
  if (!items.length) {
    body.innerHTML = `<div class="empty-state" style="padding:50px 10px"><div class="e">🛍️</div><b>Корзина пуста</b><p class="muted small" style="margin-top:6px">Добавьте товары из каталога</p></div>`;
    foot.innerHTML = `<a class="btn btn-primary btn-block" href="#/catalog" onclick="closeDrawer()">В каталог</a>`;
    return;
  }
  body.innerHTML = items.map((i) => `<div class="cart-line" style="grid-template-columns:56px 1fr auto">
    <div class="cart-thumb" style="width:56px;height:56px;font-size:24px;border-radius:12px">${i.emoji}</div>
    <div><div class="small" style="font-weight:550">${esc(i.name)}</div>
      ${i.variant ? `<div class="tiny muted">Размер: ${esc(i.variant)}</div>` : ''}
      <div class="qty" style="margin-top:6px"><button data-d="${i.key}">−</button><span>${i.qty}</span><button data-i="${i.key}">+</button></div>
    </div>
    <div class="small nowrap" style="font-weight:600">${money(i.price * i.qty)}</div>
  </div>`).join('');
  foot.innerHTML = `<div class="sum-row total" style="border:0;margin:0;padding:0"><span>Итого</span><span class="v">${money(cartSum())}</span></div>
    <p class="tiny muted">Доставка рассчитывается при оформлении</p>
    <a class="btn btn-primary btn-block btn-lg" href="#/checkout" onclick="closeDrawer()">Оформить заказ</a>
    <a class="btn btn-ghost btn-block" href="#/cart" onclick="closeDrawer()">Перейти в корзину</a>`;
  $$('[data-i]', body).forEach((b) => b.onclick = () => { const k = b.dataset.i; setQty(k, (state.cart[k] || 0) + 1); });
  $$('[data-d]', body).forEach((b) => b.onclick = () => { const k = b.dataset.d; setQty(k, (state.cart[k] || 0) - 1); });
}

/* ---------------- роутинг ---------------- */
function navigate(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}
function route() {
  const hash = location.hash.replace(/^#/, '') || '/';
  const [, path, qs] = hash.match(/^([^?]*)(?:\?(.*))?$/) || [];
  const params = new URLSearchParams(qs || '');
  window.scrollTo({ top: 0, behavior: 'instant' });

  if (path.startsWith('/catalog')) {
    state.filters.cat = params.get('cat') || '';
    state.filters.q = params.get('q') || '';
    state.filters.sub = '';
    if (params.get('sort')) state.filters.sort = params.get('sort');
    paintCatnav();
    return viewCatalog();
  }
  if (path.startsWith('/product/')) { paintCatnav(); return viewProduct(path.split('/')[2]); }
  if (path === '/cart') { paintCatnav(); return viewCart(); }
  if (path === '/checkout') { paintCatnav(); return viewCheckout(); }
  if (path === '/order') {
    const n = params.get('number') || localStorage.getItem('polka_last_order');
    paintCatnav();
    return n ? viewOrder(n) : viewCart();
  }
  if (path === '/delivery') { paintCatnav(); return viewDelivery(); }
  if (path === '/legal') { paintCatnav(); return viewLegal(); }
  paintCatnav();
  viewHome();
}

/* ---------------- поиск и глобальные клики ---------------- */
$('#searchForm').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = $('#searchInput').value.trim();
  if (!q) return;
  state.filters.q = q;
  navigate(`#/catalog?q=${encodeURIComponent(q)}`);
});
$('#cartBtn').addEventListener('click', openDrawer);

document.addEventListener('click', (e) => {
  const add = e.target.closest('[data-add]');
  if (add) { e.preventDefault(); addToCart(+add.dataset.add); }
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
window.addEventListener('hashchange', route);

/* ---------------- старт ---------------- */
(async function init() {
  try {
    state.catalog = await api('/api/catalog');
    paintCartCount();
    const s = state.catalog.shop;
    const top = $('#freeFromTop');
    if (top && state.catalog.delivery?.freeFrom) {
      top.textContent = `🚚 Бесплатная доставка от ${money(state.catalog.delivery.freeFrom)}`;
    }
    $('#sellerInfo').textContent = `${s.seller} · ИНН ${s.inn}`;
    $('#supportLink').href = `mailto:${s.email}`;
    route();
  } catch (e) {
    app.innerHTML = `<div class="page"><div class="wrap"><div class="empty-state"><div class="e">😕</div>
      <h3>Не удалось загрузить каталог</h3><p class="muted" style="margin-top:8px">${esc(e.message)}</p>
      <button class="btn btn-primary" style="margin-top:16px" onclick="location.reload()">Обновить</button></div></div></div>`;
  }
})();
