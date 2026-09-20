let categories = [];
let products = [];
let cart = []; // { product_id, name, qty, unit_price, is_kitchen_item }
let settings = {};

async function init() {
  categories = await window.api.categories.list();
  products = await window.api.products.list();
  settings = await window.api.settings.get();

  renderProductGrid();
  renderCategorySelect();
  renderCart();
  populateSettingsForm();
  await refreshSalesTable();
  await refreshProductsTable();

  setupNav();
  setupPosHandlers();
  setupProductHandlers();
  setupSettingsHandlers();
}

function setupNav() {
  document.querySelectorAll('.nav-btn[data-view]').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-btn[data-view]').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
      document.getElementById('view-' + btn.dataset.view).classList.add('active');
    });
  });
  document.getElementById('openKitchenBtn').addEventListener('click', () => {
    window.api.kitchen.openWindow();
  });
}

function renderProductGrid() {
  const grid = document.getElementById('productGrid');
  grid.innerHTML = '';
  for (const p of products) {
    const card = document.createElement('div');
    card.className = 'product-card';
    const stockLabel = p.track_stock ? `${p.stock_qty} بالمخزون` : 'غير محدود';
    card.innerHTML = `
      <div class="name">${escapeHtml(p.name)}</div>
      <div class="price">${p.price.toFixed(2)} ${settings.currency || ''}</div>
      <div class="stock">${stockLabel}</div>
    `;
    card.addEventListener('click', () => addToCart(p));
    grid.appendChild(card);
  }
}

function renderCategorySelect() {
  const select = document.getElementById('pCategory');
  select.innerHTML = categories.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
}

function addToCart(product) {
  if (product.track_stock && product.stock_qty <= 0) {
    alert('المنتج غير متوفر بالمخزون');
    return;
  }
  const existing = cart.find((it) => it.product_id === product.id);
  if (existing) {
    existing.qty += 1;
  } else {
    cart.push({
      product_id: product.id,
      name: product.name,
      qty: 1,
      unit_price: product.price,
      is_kitchen_item: product.category_is_kitchen ? 1 : 0,
    });
  }
  renderCart();
}

function renderCart() {
  const container = document.getElementById('cartItems');
  container.innerHTML = '';
  for (const [index, it] of cart.entries()) {
    const row = document.createElement('div');
    row.className = 'cart-row';
    row.innerHTML = `
      <span>${escapeHtml(it.name)}</span>
      <div class="qty-controls" style="display:flex;align-items:center;gap:6px;">
        <button data-action="dec" data-index="${index}">-</button>
        <span>${it.qty}</span>
        <button data-action="inc" data-index="${index}">+</button>
        <button data-action="remove" data-index="${index}">×</button>
      </div>
      <span>${(it.qty * it.unit_price).toFixed(2)}</span>
    `;
    container.appendChild(row);
  }
  container.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const index = Number(btn.dataset.index);
      if (btn.dataset.action === 'inc') cart[index].qty += 1;
      if (btn.dataset.action === 'dec') cart[index].qty = Math.max(1, cart[index].qty - 1);
      if (btn.dataset.action === 'remove') cart.splice(index, 1);
      renderCart();
    });
  });
  updateTotals();
}

function updateTotals() {
  const subtotal = cart.reduce((sum, it) => sum + it.qty * it.unit_price, 0);
  const discount = Number(document.getElementById('discountInput').value) || 0;
  const taxPercent = Number(settings.tax_percent) || 0;
  const taxable = Math.max(subtotal - discount, 0);
  const tax = taxable * (taxPercent / 100);
  const total = taxable + tax;

  document.getElementById('subtotalText').textContent = subtotal.toFixed(2);
  document.getElementById('taxText').textContent = tax.toFixed(2);
  document.getElementById('totalText').textContent = total.toFixed(2);
}

function setupPosHandlers() {
  document.getElementById('discountInput').addEventListener('input', updateTotals);

  document.getElementById('clearCartBtn').addEventListener('click', () => {
    cart = [];
    renderCart();
  });

  document.getElementById('checkoutBtn').addEventListener('click', async () => {
    if (cart.length === 0) {
      alert('الفاتورة فارغة');
      return;
    }
    const discount = Number(document.getElementById('discountInput').value) || 0;
    const taxPercent = Number(settings.tax_percent) || 0;
    const paymentMethod = document.getElementById('paymentMethod').value;

    const result = await window.api.sales.create({
      items: cart,
      discount,
      taxPercent,
      paymentMethod,
    });

    alert(`تم إتمام البيع - فاتورة رقم ${result.saleNumber} بإجمالي ${result.total.toFixed(2)}`);
    cart = [];
    document.getElementById('discountInput').value = 0;
    renderCart();
    products = await window.api.products.list();
    renderProductGrid();
    await refreshSalesTable();
  });
}

async function refreshSalesTable() {
  const sales = await window.api.sales.list(100);
  const body = document.getElementById('salesTableBody');
  body.innerHTML = sales.map((s) => `
    <tr>
      <td>${s.sale_number}</td>
      <td>${s.created_at}</td>
      <td>${s.total.toFixed(2)}</td>
      <td>${s.payment_method === 'cash' ? 'نقدًا' : 'بطاقة'}</td>
    </tr>
  `).join('');
}

async function refreshProductsTable() {
  const body = document.getElementById('productsTableBody');
  body.innerHTML = products.map((p) => `
    <tr>
      <td>${escapeHtml(p.name)}</td>
      <td>${escapeHtml(p.category_name || '-')}</td>
      <td>${p.price.toFixed(2)}</td>
      <td>${p.track_stock ? p.stock_qty : '—'}</td>
      <td><button class="secondary" data-delete="${p.id}">حذف</button></td>
    </tr>
  `).join('');
  body.querySelectorAll('[data-delete]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await window.api.products.delete(Number(btn.dataset.delete));
      products = await window.api.products.list();
      renderProductGrid();
      await refreshProductsTable();
    });
  });
}

function setupProductHandlers() {
  document.getElementById('saveProductBtn').addEventListener('click', async () => {
    const name = document.getElementById('pName').value.trim();
    if (!name) { alert('اسم المنتج مطلوب'); return; }
    await window.api.products.save({
      name,
      barcode: document.getElementById('pBarcode').value.trim(),
      category_id: Number(document.getElementById('pCategory').value) || null,
      price: Number(document.getElementById('pPrice').value) || 0,
      cost: Number(document.getElementById('pCost').value) || 0,
      stock_qty: Number(document.getElementById('pStock').value) || 0,
      track_stock: document.getElementById('pTrackStock').checked,
    });
    document.getElementById('pName').value = '';
    document.getElementById('pBarcode').value = '';
    document.getElementById('pPrice').value = '';
    document.getElementById('pCost').value = '';
    document.getElementById('pStock').value = '';
    products = await window.api.products.list();
    renderProductGrid();
    await refreshProductsTable();
  });
}

function populateSettingsForm() {
  document.getElementById('sStoreName').value = settings.store_name || '';
  document.getElementById('sCurrency').value = settings.currency || '';
  document.getElementById('sTax').value = settings.tax_percent || 0;
}

function setupSettingsHandlers() {
  document.getElementById('saveSettingsBtn').addEventListener('click', async () => {
    await window.api.settings.save('store_name', document.getElementById('sStoreName').value);
    await window.api.settings.save('currency', document.getElementById('sCurrency').value);
    await window.api.settings.save('tax_percent', document.getElementById('sTax').value);
    settings = await window.api.settings.get();
    renderProductGrid();
    alert('تم حفظ الإعدادات');
  });

  document.getElementById('addCategoryBtn').addEventListener('click', async () => {
    const name = document.getElementById('catName').value.trim();
    if (!name) return;
    await window.api.categories.save(name, document.getElementById('catIsKitchen').checked);
    categories = await window.api.categories.list();
    renderCategorySelect();
    document.getElementById('catName').value = '';
    alert('تمت إضافة الفئة');
  });
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

init();
