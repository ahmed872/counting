const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  categories: {
    list: () => ipcRenderer.invoke('categories:list'),
    save: (name, isKitchen) => ipcRenderer.invoke('categories:save', name, isKitchen),
  },
  products: {
    list: () => ipcRenderer.invoke('products:list'),
    save: (product) => ipcRenderer.invoke('products:save', product),
    delete: (id) => ipcRenderer.invoke('products:delete', id),
  },
  sales: {
    create: (payload) => ipcRenderer.invoke('sales:create', payload),
    list: (limit) => ipcRenderer.invoke('sales:list', limit),
    items: (saleId) => ipcRenderer.invoke('sales:items', saleId),
  },
  kitchen: {
    list: () => ipcRenderer.invoke('kitchen:list'),
    updateStatus: (saleId, status) => ipcRenderer.invoke('kitchen:updateStatus', saleId, status),
    openWindow: () => ipcRenderer.invoke('kitchen:openWindow'),
  },
  settings: {
    get: () => ipcRenderer.invoke('settings:get'),
    save: (key, value) => ipcRenderer.invoke('settings:save', key, value),
  },
});
