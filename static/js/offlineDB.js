/**
 * offlineDB.js
 * إدارة قاعدة بيانات IndexedDB لتخزين البيانات محليًا
 * الجداول: products, stores, pendingOrders, notifications
 */
const OfflineDB = (function() {
    const DB_NAME = 'husayniyyah_offline_db';
    const DB_VERSION = 3;

    let db = null;

    function openDB() {
        return new Promise((resolve, reject) => {
            if (db) {
                resolve(db);
                return;
            }
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = function(event) {
                const database = event.target.result;

                if (!database.objectStoreNames.contains('products')) {
                    const productsStore = database.createObjectStore('products', { keyPath: 'id' });
                    productsStore.createIndex('store_id', 'store_id', { unique: false });
                    productsStore.createIndex('name', 'name', { unique: false });
                }

                if (!database.objectStoreNames.contains('stores')) {
                    const storesStore = database.createObjectStore('stores', { keyPath: 'id' });
                    storesStore.createIndex('name', 'name', { unique: false });
                }

                if (!database.objectStoreNames.contains('pendingOrders')) {
                    const ordersStore = database.createObjectStore('pendingOrders', { keyPath: 'local_id', autoIncrement: true });
                    ordersStore.createIndex('created_at', 'created_at', { unique: false });
                }

                if (!database.objectStoreNames.contains('notifications')) {
                    const notificationsStore = database.createObjectStore('notifications', { keyPath: 'id' });
                    notificationsStore.createIndex('is_read', 'is_read', { unique: false });
                    notificationsStore.createIndex('created_at', 'created_at', { unique: false });
                }
            };

            request.onsuccess = function(event) {
                db = event.target.result;
                resolve(db);
            };

            request.onerror = function(event) {
                reject(event.target.error);
            };
        });
    }

    async function getStore(storeName, mode = 'readonly') {
        const database = await openDB();
        const transaction = database.transaction(storeName, mode);
        return transaction.objectStore(storeName);
    }

    async function addItem(storeName, item) {
        const store = await getStore(storeName, 'readwrite');
        return new Promise((resolve, reject) => {
            const request = store.put(item);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function getItem(storeName, key) {
        const store = await getStore(storeName);
        return new Promise((resolve, reject) => {
            const request = store.get(key);
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function getAll(storeName) {
        const store = await getStore(storeName);
        return new Promise((resolve, reject) => {
            const request = store.getAll();
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    async function deleteItem(storeName, key) {
        const store = await getStore(storeName, 'readwrite');
        return new Promise((resolve, reject) => {
            const request = store.delete(key);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    async function clearStore(storeName) {
        const store = await getStore(storeName, 'readwrite');
        return new Promise((resolve, reject) => {
            const request = store.clear();
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }

    function normalizeProduct(p) {
        return {
            id: p.id,
            name: p.name || '',
            price: p.price || 0,
            original_price: p.original_price || null,
            is_offer: p.is_offer || false,
            stock_quantity: p.stock_quantity || 0,
            main_image: p.main_image || p.image || '',
            description: p.description || '',
            store_id: p.store_id || (p.store && p.store.id) || null,
            store_name: p.store_name || (p.store && p.store.name) || '',
            store_logo: p.store_logo || (p.store && p.store.logo_url) || ''
        };
    }

    async function saveProduct(product) {
        const item = normalizeProduct(product);
        return addItem('products', item);
    }

    async function saveProducts(products) {
        const store = await getStore('products', 'readwrite');
        const transaction = store.transaction;
        return new Promise((resolve, reject) => {
            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject(transaction.error);
            products.forEach(p => {
                store.put(normalizeProduct(p));
            });
        });
    }

    async function getAllProducts() {
        return getAll('products');
    }

    async function getProductsByStore(storeId) {
        const all = await getAll('products');
        return all.filter(p => p.store_id === storeId);
    }

    async function saveStore(store) {
        return addItem('stores', {
            id: store.id,
            name: store.name || '',
            description: store.description || '',
            logo_url: store.logo_url || '',
            phone: store.phone || '',
            address: store.address || '',
            working_hours: store.working_hours || '',
            subscription_status: store.subscription_status || '',
            is_open: store.is_open || false
        });
    }

    async function saveStores(stores) {
        const store = await getStore('stores', 'readwrite');
        const transaction = store.transaction;
        return new Promise((resolve, reject) => {
            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject(transaction.error);
            stores.forEach(s => {
                store.put({
                    id: s.id,
                    name: s.name || '',
                    description: s.description || '',
                    logo_url: s.logo_url || '',
                    phone: s.phone || '',
                    address: s.address || '',
                    working_hours: s.working_hours || '',
                    subscription_status: s.subscription_status || '',
                    is_open: s.is_open || false
                });
            });
        });
    }

    async function getAllStores() {
        return getAll('stores');
    }

    async function savePendingOrder(order) {
        order.created_at = new Date().toISOString();
        return addItem('pendingOrders', order);
    }

    async function getAllPendingOrders() {
        return getAll('pendingOrders');
    }

    async function deletePendingOrder(localId) {
        return deleteItem('pendingOrders', localId);
    }

    async function saveNotification(notification) {
        return addItem('notifications', notification);
    }

    async function saveNotifications(notifications) {
        const store = await getStore('notifications', 'readwrite');
        const transaction = store.transaction;
        return new Promise((resolve, reject) => {
            transaction.oncomplete = () => resolve();
            transaction.onerror = () => reject(transaction.error);
            notifications.forEach(n => {
                store.put({
                    id: n.id,
                    type: n.type || 'default',
                    title: n.title || '',
                    message: n.message || '',
                    link: n.link || '',
                    is_read: n.is_read || false,
                    created_at: n.created_at || new Date().toISOString()
                });
            });
        });
    }

    async function getAllNotifications() {
        return getAll('notifications');
    }

    async function deleteNotification(notificationId) {
        return deleteItem('notifications', notificationId);
    }

    async function clearNotifications() {
        return clearStore('notifications');
    }

    return {
        saveProduct,
        saveProducts,
        getAllProducts,
        getProductsByStore,
        saveStore,
        saveStores,
        getAllStores,
        savePendingOrder,
        getAllPendingOrders,
        deletePendingOrder,
        saveNotification,
        saveNotifications,
        getAllNotifications,
        deleteNotification,
        clearNotifications,
        clearStore
    };
})();
