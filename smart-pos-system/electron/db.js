const path = require('node:path');
const fs = require('node:fs');
const { app } = require('electron');
const Database = require('better-sqlite3');

const dbDir = app.getPath('userData');
if (!fs.existsSync(dbDir)) fs.mkdirSync(dbDir, { recursive: true });
const dbPath = path.join(dbDir, 'smart-pos.db');

const db = new Database(dbPath);
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  is_kitchen INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  barcode TEXT UNIQUE,
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  price REAL NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0,
  stock_qty REAL NOT NULL DEFAULT 0,
  track_stock INTEGER NOT NULL DEFAULT 1,
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  pin TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'cashier',
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sales (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_number TEXT NOT NULL UNIQUE,
  user_id INTEGER REFERENCES users(id),
  customer_id INTEGER REFERENCES customers(id),
  subtotal REAL NOT NULL,
  discount REAL NOT NULL DEFAULT 0,
  tax REAL NOT NULL DEFAULT 0,
  total REAL NOT NULL,
  payment_method TEXT NOT NULL DEFAULT 'cash',
  kitchen_status TEXT NOT NULL DEFAULT 'none',
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sale_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
  product_id INTEGER REFERENCES products(id),
  name TEXT NOT NULL,
  qty REAL NOT NULL,
  unit_price REAL NOT NULL,
  line_total REAL NOT NULL,
  is_kitchen_item INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stock_movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES products(id),
  change_qty REAL NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
`);

function seedIfEmpty() {
  const productCount = db.prepare('SELECT COUNT(*) AS c FROM products').get().c;
  if (productCount > 0) return;

  const insertCategory = db.prepare('INSERT INTO categories (name, is_kitchen) VALUES (?, ?)');
  const foodCat = insertCategory.run('مأكولات', 1).lastInsertRowid;
  const drinksCat = insertCategory.run('مشروبات', 1).lastInsertRowid;
  const generalCat = insertCategory.run('عام', 0).lastInsertRowid;

  const insertProduct = db.prepare(`
    INSERT INTO products (name, barcode, category_id, price, cost, stock_qty, track_stock)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `);
  insertProduct.run('برجر لحم', '1001', foodCat, 85, 45, 0, 0);
  insertProduct.run('بيتزا مارجريتا', '1002', foodCat, 120, 60, 0, 0);
  insertProduct.run('بطاطس مقلية', '1003', foodCat, 35, 15, 0, 0);
  insertProduct.run('عصير برتقال', '2001', drinksCat, 25, 10, 40, 1);
  insertProduct.run('مياه معدنية', '2002', drinksCat, 10, 4, 100, 1);
  insertProduct.run('قهوة تركي', '2003', drinksCat, 20, 8, 0, 0);
  insertProduct.run('منتج عام', '3001', generalCat, 15, 7, 25, 1);

  const insertUser = db.prepare('INSERT INTO users (username, pin, role) VALUES (?, ?, ?)');
  insertUser.run('admin', '1234', 'admin');

  const insertSetting = db.prepare('INSERT INTO settings (key, value) VALUES (?, ?)');
  insertSetting.run('store_name', 'متجري');
  insertSetting.run('currency', 'ج.م');
  insertSetting.run('tax_percent', '0');
}
seedIfEmpty();

function nextSaleNumber() {
  const row = db.prepare(`SELECT sale_number FROM sales ORDER BY id DESC LIMIT 1`).get();
  const lastNum = row ? parseInt(row.sale_number.replace(/\D/g, ''), 10) || 0 : 0;
  return 'INV-' + String(lastNum + 1).padStart(6, '0');
}

module.exports = {
  db,

  getCategories() {
    return db.prepare('SELECT * FROM categories ORDER BY name').all();
  },

  getProducts() {
    return db.prepare(`
      SELECT p.*, c.name AS category_name, c.is_kitchen AS category_is_kitchen
      FROM products p
      LEFT JOIN categories c ON c.id = p.category_id
      WHERE p.is_active = 1
      ORDER BY p.name
    `).all();
  },

  saveProduct(product) {
    if (product.id) {
      db.prepare(`
        UPDATE products SET name=?, barcode=?, category_id=?, price=?, cost=?, track_stock=?
        WHERE id=?
      `).run(product.name, product.barcode || null, product.category_id || null,
        product.price, product.cost || 0, product.track_stock ? 1 : 0, product.id);
      return product.id;
    }
    const info = db.prepare(`
      INSERT INTO products (name, barcode, category_id, price, cost, stock_qty, track_stock)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(product.name, product.barcode || null, product.category_id || null,
      product.price, product.cost || 0, product.stock_qty || 0, product.track_stock ? 1 : 0);
    return info.lastInsertRowid;
  },

  deleteProduct(id) {
    db.prepare('UPDATE products SET is_active = 0 WHERE id = ?').run(id);
  },

  saveCategory(name, isKitchen) {
    const info = db.prepare('INSERT INTO categories (name, is_kitchen) VALUES (?, ?)').run(name, isKitchen ? 1 : 0);
    return info.lastInsertRowid;
  },

  createSale(payload) {
    const { items, discount = 0, taxPercent = 0, paymentMethod = 'cash', customerId = null, userId = null } = payload;
    const subtotal = items.reduce((sum, it) => sum + it.qty * it.unit_price, 0);
    const taxable = Math.max(subtotal - discount, 0);
    const tax = taxable * (taxPercent / 100);
    const total = taxable + tax;
    const hasKitchenItems = items.some((it) => it.is_kitchen_item);

    const insertSale = db.prepare(`
      INSERT INTO sales (sale_number, user_id, customer_id, subtotal, discount, tax, total, payment_method, kitchen_status)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    const insertItem = db.prepare(`
      INSERT INTO sale_items (sale_id, product_id, name, qty, unit_price, line_total, is_kitchen_item)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    const decrementStock = db.prepare(`
      UPDATE products SET stock_qty = stock_qty - ? WHERE id = ? AND track_stock = 1
    `);
    const insertMovement = db.prepare(`
      INSERT INTO stock_movements (product_id, change_qty, reason) VALUES (?, ?, 'sale')
    `);

    const saleNumber = nextSaleNumber();

    const tx = db.transaction(() => {
      const saleId = insertSale.run(
        saleNumber, userId, customerId, subtotal, discount, tax, total,
        paymentMethod, hasKitchenItems ? 'pending' : 'none'
      ).lastInsertRowid;

      for (const it of items) {
        insertItem.run(saleId, it.product_id || null, it.name, it.qty, it.unit_price,
          it.qty * it.unit_price, it.is_kitchen_item ? 1 : 0);
        if (it.product_id) {
          decrementStock.run(it.qty, it.product_id);
          insertMovement.run(it.product_id, -it.qty);
        }
      }
      return saleId;
    });

    const saleId = tx();
    return { saleId, saleNumber, subtotal, tax, total };
  },

  getSales(limit = 100) {
    return db.prepare('SELECT * FROM sales ORDER BY id DESC LIMIT ?').all(limit);
  },

  getSaleItems(saleId) {
    return db.prepare('SELECT * FROM sale_items WHERE sale_id = ?').all(saleId);
  },

  getKitchenOrders() {
    return db.prepare(`
      SELECT s.id AS sale_id, s.sale_number, s.kitchen_status, s.created_at
      FROM sales s
      WHERE s.kitchen_status IN ('pending', 'preparing')
      ORDER BY s.id ASC
    `).all().map((sale) => ({
      ...sale,
      items: db.prepare('SELECT * FROM sale_items WHERE sale_id = ? AND is_kitchen_item = 1').all(sale.sale_id),
    }));
  },

  updateKitchenStatus(saleId, status) {
    db.prepare('UPDATE sales SET kitchen_status = ? WHERE id = ?').run(status, saleId);
  },

  getSettings() {
    const rows = db.prepare('SELECT key, value FROM settings').all();
    return Object.fromEntries(rows.map((r) => [r.key, r.value]));
  },

  saveSetting(key, value) {
    db.prepare('INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run(key, value);
  },
};
