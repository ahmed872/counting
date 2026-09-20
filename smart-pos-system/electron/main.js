const path = require('node:path');
const { app, BrowserWindow, ipcMain } = require('electron');

let store;
let mainWindow;
let kitchenWindow;

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: 'Smart POS',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));
}

function createKitchenWindow() {
  if (kitchenWindow) {
    kitchenWindow.focus();
    return;
  }
  kitchenWindow = new BrowserWindow({
    width: 900,
    height: 700,
    title: 'شاشة المطبخ - Smart POS',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  kitchenWindow.loadFile(path.join(__dirname, '..', 'renderer', 'kitchen.html'));
  kitchenWindow.on('closed', () => {
    kitchenWindow = null;
  });
}

app.whenReady().then(() => {
  store = require('./db.js');
  registerIpcHandlers();
  createMainWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

function registerIpcHandlers() {
  ipcMain.handle('categories:list', () => store.getCategories());
  ipcMain.handle('categories:save', (_e, name, isKitchen) => store.saveCategory(name, isKitchen));

  ipcMain.handle('products:list', () => store.getProducts());
  ipcMain.handle('products:save', (_e, product) => store.saveProduct(product));
  ipcMain.handle('products:delete', (_e, id) => store.deleteProduct(id));

  ipcMain.handle('sales:create', (_e, payload) => store.createSale(payload));
  ipcMain.handle('sales:list', (_e, limit) => store.getSales(limit));
  ipcMain.handle('sales:items', (_e, saleId) => store.getSaleItems(saleId));

  ipcMain.handle('kitchen:list', () => store.getKitchenOrders());
  ipcMain.handle('kitchen:updateStatus', (_e, saleId, status) => store.updateKitchenStatus(saleId, status));
  ipcMain.handle('kitchen:openWindow', () => createKitchenWindow());

  ipcMain.handle('settings:get', () => store.getSettings());
  ipcMain.handle('settings:save', (_e, key, value) => store.saveSetting(key, value));
}
