/* Админка ПОЛКА */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const money = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n)) + ' ₽';
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let TOKEN = localStorage.getItem('polka_admin_token') || '';
let productsCache = [];
let currentCatTitles = {};
let ordersCache = [];
let statusesMap = {};

function toast(msg, kind = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 2800);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN}`, ...(opts.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) { logout(); throw new Error('Сессия истекла, войдите снова'); }
  if (!res.ok) throw new Error(data.error || 'Ошибка запроса');
  return data;
}

/* ---------- вход ---------- */
$('#loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('#loginForm button');
  btn.disabled = true;
  $('#loginErr').classList.add('hidden');
  try {
    const res = await fetch('/api/admin/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: $('#password').value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Неверный пароль');
    TOKEN = data.token;
    localStorage.setItem('polka_admin_token', TOKEN);
    enterPanel();
  } catch (e) {
    $('#loginErr').textContent = e.message;
    $('#loginErr').classList.remove('hidden');
  } finally {
    btn.disabled = false;
  }
});

function logout() {
  TOKEN = '';
  localStorage.removeItem('polka_admin_token');
  $('#panel').classList.add('hidden');
  $('#loginScreen').classList.remove('hidden');
}
$('#logout').onclick = logout;

async function enterPanel() {
  try {
    await api('/api/admin/session');
  } catch { return; }
  $('#loginScreen').classList.add('hidden');
  $('#panel').classList.remove('hidden');
  await Promise.all([loadStats(), loadProducts(), loadOrders()]);
}

/* ---------- вкладки ---------- */
$('#tabs').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-tab]');
  if (!b) return;
  $$('#tabs button').forEach((x) => x.classList.toggle('active', x === b));
  ['dashboard', 'products', 'orders'].forEach((t) => $('#tab-' + t).classList.toggle('hidden', t !== b.dataset.tab));
});
$$('[data-goto]').forEach((b) => b.onclick = () => $(`#tabs [data-tab="${b.dataset.goto}"]`).click());

/* ---------- сводка ---------- */
async function loadStats() {
  try {
    const s = await api('/api/admin/stats');
    $('#statGrid').innerHTML = `
      <div class="stat-card accent"><div class="label">Выручка</div><div class="value">${money(s.revenue)}</div><div class="sub">${s.paidOrders} оплаченных заказов</div></div>
      <div class="stat-card"><div class="label">Всего заказов</div><div class="value">${s.orders}</div><div class="sub">на сумму ${money(s.ordersSum)}</div></div>
      <div class="stat-card"><div class="label">Ждут оплаты</div><div class="value">${s.awaitingPayment}</div><div class="sub">напомните клиенту</div></div>
      <div class="stat-card"><div class="label">Нет в наличии</div><div class="value">${s.outOfStock}</div><div class="sub">${s.lowStock} заканчивается</div></div>`;
    const days = s.revenueByDay.slice().reverse();
    const max = Math.max(1, ...days.map((d) => d.s || 0));
    $('#revenueChart').innerHTML = days.length ? days.map((d) => `
      <div class="bar-wrap">
        <div class="bar" style="height:${Math.max(4, ((d.s || 0) / max) * 110)}px" title="${money(d.s || 0)}"></div>
        <div class="cap">${d.d?.slice(8, 10)}.${d.d?.slice(5, 7)}</div>
      </div>`).join('') : '<p class="muted small">Пока нет оплаченных заказов</p>';
  } catch (e) { toast(e.message, 'err'); }
}

/* ---------- товары ---------- */
async function loadProducts() {
  try {
    const [data, catalog] = await Promise.all([api('/api/admin/products'), fetch('/api/catalog').then((r) => r.json())]);
    productsCache = data.products;
    const catTitle = Object.fromEntries(catalog.categories.map((c) => [c.id, `${c.emoji} ${c.title}`]));
    currentCatTitles = catTitle;
    const sel = $('#catFilter');
    if (!sel.options.length) {
      sel.innerHTML = '<option value="">Все категории</option>' +
        catalog.categories.map((c) => `<option value="${c.id}">${c.title}</option>`).join('');
    }
    renderProducts(catTitle);
  } catch (e) { toast(e.message, 'err'); }
}

function renderProducts(catTitle) {
  const q = $('#prodSearch').value.trim().toLowerCase();
  const cat = $('#catFilter').value;
  const rows = productsCache.filter((p) => (!cat || p.category === cat) && (!q || p.name.toLowerCase().includes(q)));
  $('#prodTable tbody').innerHTML = rows.map((p) => {
    const pill = p.stock === 0 ? 'out' : p.stock <= 5 ? 'low' : 'ok';
    const label = p.stock === 0 ? 'нет' : p.stock <= 5 ? 'мало' : 'в наличии';
    return `<tr data-id="${p.id}">
      <td class="emoji-cell">${p.emoji}</td>
      <td><div class="name">${esc(p.name)}</div><div class="sku">PLK-${String(p.id).padStart(4, '0')}</div></td>
      <td class="muted small">${esc((catTitle[p.category] || '').replace(/^[^ ]+ /, ''))}</td>
      <td><input class="cell-input" type="number" min="0" step="10" value="${p.price}" data-field="price"></td>
      <td><input class="cell-input" type="number" min="0" step="1" value="${p.stock}" data-field="stock"></td>
      <td><span class="pill-stock ${pill}">${label} · ${p.stock}</span></td>
      <td><button class="row-save" data-save>Сохранить</button></td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" class="muted" style="padding:24px;text-align:center">Ничего не найдено</td></tr>';

  $$('#prodTable [data-field]').forEach((inp) => inp.oninput = () => {
    const tr = inp.closest('tr');
    const price = tr.querySelector('[data-field="price"]').value;
    const stock = tr.querySelector('[data-field="stock"]').value;
    const p = productsCache.find((x) => x.id === +tr.dataset.id);
    tr.querySelector('[data-save]').classList.toggle('dirty', +price !== p.price || +stock !== p.stock);
  });

  $$('#prodTable [data-save]').forEach((btn) => btn.onclick = async () => {
    const tr = btn.closest('tr');
    const id = +tr.dataset.id;
    const price = +tr.querySelector('[data-field="price"]').value;
    const stock = +tr.querySelector('[data-field="stock"]').value;
    btn.disabled = true;
    try {
      await api('/api/admin/product', { method: 'POST', body: JSON.stringify({ id, price, stock }) });
      const p = productsCache.find((x) => x.id === id);
      p.price = price; p.stock = stock;
      btn.classList.remove('dirty');
      toast('Сохранено', 'ok');
      await loadProducts();
      if ($('#tab-dashboard').classList.contains('hidden') === false) loadStats();
    } catch (e) { toast(e.message, 'err'); }
    finally { btn.disabled = false; }
  });
}

$('#prodSearch').oninput = () => renderProducts(currentCatTitles);
$('#catFilter').onchange = () => renderProducts(currentCatTitles);

$('#bulkBtn').onclick = async () => {
  const v = prompt('Установить одинаковый остаток для ВСЕХ товаров.\nВведите число (например, 100):', '100');
  if (v === null) return;
  const stock = parseInt(v, 10);
  if (Number.isNaN(stock) || stock < 0) return toast('Нужно целое число ≥ 0', 'err');
  if (!confirm(`Выставить остаток ${stock} шт. на все товары? Текущие остатки перезапишутся.`)) return;
  try {
    await api('/api/admin/bulk-stock', { method: 'POST', body: JSON.stringify({ stock }) });
    toast('Остатки обновлены', 'ok');
    await loadProducts();
  } catch (e) { toast(e.message, 'err'); }
};

/* ---------- заказы ---------- */
async function loadOrders() {
  try {
    const data = await api('/api/admin/orders');
    ordersCache = data.orders;
    statusesMap = data.statuses;
    renderOrders();
  } catch (e) { toast(e.message, 'err'); }
}

function renderOrders() {
  const f = $('#orderFilter').value;
  const rows = ordersCache.filter((o) => !f || o.status === f);
  $('#ordersList').innerHTML = rows.length ? rows.map((o) => `
    <div class="order-card" data-num="${o.number}">
      <div class="order-head">
        <div>
          <b>${o.number}</b>
          <div class="meta">${new Date(o.created_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · ${esc(o.customer.name || '—')} · ${esc(o.customer.phone || '')}</div>
        </div>
        <div class="meta">${o.items.reduce((s, i) => s + i.qty, 0)} поз. · ${o.weight} кг</div>
        <div><b>${money(o.total)}</b><div class="meta">${o.delivery_price ? 'доставка ' + money(o.delivery_price) : 'доставка бесплатно'}</div></div>
        <div style="text-align:right"><span class="status-badge st-${o.status}">${o.statusLabel}</span></div>
      </div>
      <div class="order-body hidden">
        <div>
          <h4 style="font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:14px 0 8px">Состав</h4>
          ${o.items.map((i) => `<div class="order-item"><span>${esc(i.name)} × ${i.qty}</span><span>${money(i.price * i.qty)}</span></div>`).join('')}
          <div class="order-item" style="border:0;font-weight:600;margin-top:6px"><span>Итого</span><span>${money(o.total)}</span></div>
        </div>
        <div>
          <h4 style="font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:14px 0 8px">Доставка и контакты</h4>
          <div class="small" style="line-height:1.7">
            <div><span class="muted">ПВЗ:</span> ${esc(o.pvz.city || '')}, ${esc(o.pvz.address || '')}</div>
            <div><span class="muted">Тип:</span> ${esc(o.pvz.type || '')}</div>
            <div><span class="muted">Получатель:</span> ${esc(o.customer.name || '')} · ${esc(o.customer.phone || '')}</div>
            <div><span class="muted">Email:</span> ${esc(o.customer.email || '—')}</div>
            <div><span class="muted">Оплата:</span> ${esc(o.payment_provider || '—')}${o.paid_at ? ' · ' + new Date(o.paid_at).toLocaleString('ru-RU') : ''}</div>
          </div>
          <div style="display:flex;gap:8px;margin-top:14px;align-items:center;flex-wrap:wrap">
            <select class="status-select" data-status="${o.number}">
              ${Object.entries(statusesMap).map(([k, v]) => `<option value="${k}" ${k === o.status ? 'selected' : ''}>${v}</option>`).join('')}
            </select>
            <button class="row-save" data-apply="${o.number}">Применить</button>
          </div>
        </div>
      </div>
    </div>`).join('') : '<p class="muted" style="padding:20px;text-align:center">Заказов пока нет</p>';

  $$('.order-head').forEach((h) => h.onclick = () => $('.order-body', h.parentElement).classList.toggle('hidden'));
  $$('[data-apply]').forEach((b) => b.onclick = async () => {
    const number = b.dataset.apply;
    const status = $(`[data-status="${number}"]`).value;
    if (status === 'cancelled' && !confirm('Отменить заказ и вернуть товар на склад?')) return;
    try {
      await api('/api/admin/order-status', { method: 'POST', body: JSON.stringify({ number, status }) });
      toast('Статус обновлён', 'ok');
      await Promise.all([loadOrders(), loadStats()]);
    } catch (e) { toast(e.message, 'err'); }
  });
}
$('#orderFilter').onchange = renderOrders;

/* ---------- старт ---------- */
(async function init() {
  if (TOKEN) await enterPanel();
})();
