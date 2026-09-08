/**
 * LocalStore - إدارة السلة والمفضلة والملف الشخصي والوضع الداكن محلياً مع مزامنة خادم
 * يعتمد على OfflineDB لتخزين بيانات المنتجات والمتاجر في IndexedDB
 * تم تحسين sync بإضافة debounce وتقليل الطلبات المتكررة،
 * مع تطبيع البيانات قبل التخزين.
 */
const LocalStore = (function() {
    const CART_KEY = 'local_cart';
    const FAVORITES_KEY = 'local_favorites';
    const PRODUCTS_CACHE_KEY = 'local_products_cache';
    const PROFILE_KEY = 'local_profile';
    const THEME_KEY = 'theme';

    let debounceTimer = null;
    let isSyncing = false;
    const DEBOUNCE_DELAY = 500;

    // ==================== الوضع الداكن ====================
    function getTheme() {
        try {
            return localStorage.getItem(THEME_KEY) || 'system';
        } catch (e) {
            return 'system';
        }
    }

    function applyTheme(theme) {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const isDark = theme === 'dark' || (theme === 'system' && prefersDark);

        document.documentElement.classList.toggle('dark-mode', isDark);
        if (document.body) {
            document.body.classList.toggle('dark-mode', isDark);
        }
    }

    function setTheme(theme) {
        localStorage.setItem(THEME_KEY, theme);
        applyTheme(theme);
        // مزامنة مع الخادم إذا كان المستخدم مسجلاً
        if (window.csrfToken && window.isAuthenticated !== false) {
            const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
            fetch('/account/theme', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': window.csrfToken
                },
                body: JSON.stringify({ dark_mode: isDark })
            }).catch(err => console.warn('Theme sync failed:', err));
        }
    }

    function toggleTheme() {
        const current = getTheme();
        if (current === 'dark') setTheme('light');
        else if (current === 'light') setTheme('system');
        else setTheme('dark');
        updateThemeButton();
    }

    function updateThemeButton() {
        const sidebarBtn = document.getElementById('sidebarThemeToggle');
        if (sidebarBtn) {
            const icon = sidebarBtn.querySelector('i');
            const label = sidebarBtn.querySelector('span') || sidebarBtn;
            const current = getTheme();
            if (current === 'dark') {
                if (icon) icon.className = 'bi bi-sun ms-1';
                label.textContent = 'الوضع الفاتح';
            } else if (current === 'light') {
                if (icon) icon.className = 'bi bi-moon-stars ms-1';
                label.textContent = 'الوضع الداكن';
            } else {
                if (icon) icon.className = 'bi bi-circle-half ms-1';
                label.textContent = 'تلقائي';
            }
        }

        const topBtn = document.getElementById('topbarThemeToggle');
        if (topBtn) {
            const icon = topBtn.querySelector('i');
            const current = getTheme();
            if (current === 'dark') {
                if (icon) icon.className = 'bi bi-sun';
            } else if (current === 'light') {
                if (icon) icon.className = 'bi bi-moon-stars';
            } else {
                if (icon) icon.className = 'bi bi-circle-half';
            }
        }
    }

    function initTheme() {
        applyTheme(getTheme());
        updateThemeButton();
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (getTheme() === 'system') {
                applyTheme('system');
            }
        });
    }

    // ==================== السلة والمفضلة ====================
    function getCart() {
        try { return JSON.parse(localStorage.getItem(CART_KEY)) || {}; } catch (e) { return {}; }
    }
    function setCart(cart) { localStorage.setItem(CART_KEY, JSON.stringify(cart)); }

    function getFavorites() {
        try { return JSON.parse(localStorage.getItem(FAVORITES_KEY)) || { products: [], stores: [] }; } catch (e) { return { products: [], stores: [] }; }
    }
    function setFavorites(favs) { localStorage.setItem(FAVORITES_KEY, JSON.stringify(favs)); }

    function getProductsCache() {
        try { return JSON.parse(localStorage.getItem(PRODUCTS_CACHE_KEY)) || {}; } catch (e) { return {}; }
    }
    function setProductsCache(cache) { localStorage.setItem(PRODUCTS_CACHE_KEY, JSON.stringify(cache)); }

    function cacheProduct(product) {
        if (!product || !product.id) return;
        const cache = getProductsCache();
        cache[product.id] = {
            id: product.id,
            name: product.name,
            price: product.price,
            image: product.image || product.main_image || '',
            store_name: product.store_name || (product.store && product.store.name) || '',
            store_id: product.store_id || (product.store && product.store.id) || null
        };
        setProductsCache(cache);
        if (typeof OfflineDB !== 'undefined') {
            OfflineDB.saveProduct(product).catch(err => console.warn('OfflineDB saveProduct failed:', err));
        }
    }

    function cacheStores(stores) {
        if (typeof OfflineDB !== 'undefined' && Array.isArray(stores) && stores.length > 0) {
            OfflineDB.saveStores(stores).catch(err => console.warn('OfflineDB saveStores failed:', err));
        }
    }

    function cacheStore(store) {
        if (typeof OfflineDB !== 'undefined' && store) {
            OfflineDB.saveStore(store).catch(err => console.warn('OfflineDB saveStore failed:', err));
        }
    }

    function getProfile() {
        try { return JSON.parse(localStorage.getItem(PROFILE_KEY)) || null; } catch (e) { return null; }
    }
    function setProfile(profile) { localStorage.setItem(PROFILE_KEY, JSON.stringify(profile)); }

    function cacheProfile(user) {
        if (!user) return;
        setProfile({
            id: user.id,
            username: user.username,
            email: user.email,
            phone: user.phone || '',
            bio: user.bio || '',
            avatar: user.avatar || '',
            public_id: user.public_id || '',
            role: user.role || '',
            dark_mode: user.dark_mode || false
        });
    }

    function updateCartBadges() {
        const cart = getCart();
        const count = Object.values(cart).reduce((sum, qty) => sum + qty, 0);
        document.querySelectorAll('.cart-badge').forEach(b => {
            b.textContent = count;
            if (count > 0) {
                b.classList.remove('d-none');
                b.classList.add('cart-badge-pulse');
            } else {
                b.classList.add('d-none');
                b.classList.remove('cart-badge-pulse');
            }
        });
    }

    async function syncPendingOrders() {
        if (!navigator.onLine || typeof OfflineDB === 'undefined') return;
        try {
            const pending = await OfflineDB.getAllPendingOrders();
            if (!pending || pending.length === 0) return;
            for (const order of pending) {
                try {
                    const csrfToken = window.csrfToken || '';
                    const response = await fetch(`/cart/checkout/${order.store_id}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-Token': csrfToken,
                            'Accept': 'application/json'
                        },
                        body: JSON.stringify({
                            items: order.items,
                            delivery_address: order.delivery_address,
                            latitude: order.latitude,
                            longitude: order.longitude
                        })
                    });
                    if (response.ok) {
                        await OfflineDB.deletePendingOrder(order.local_id);
                        console.log('تم إرسال طلب معلق بنجاح');
                    } else {
                        const data = await response.json().catch(() => ({}));
                        console.warn('فشل إرسال الطلب المعلق:', data.message || response.status);
                        if (response.status === 403) {
                            console.warn('CSRF token expired، توقف المزامنة');
                            break;
                        }
                    }
                } catch (err) {
                    console.warn('خطأ في إرسال الطلب المعلق:', err);
                }
            }
        } catch (err) {
            console.warn('فشل جلب الطلبات المعلقة:', err);
        }
    }

    async function performSync() {
        if (!navigator.onLine || isSyncing) return;
        isSyncing = true;
        try {
            const cart = getCart();
            const favs = getFavorites();
            const csrfToken = window.csrfToken || '';

            await fetch('/api/cart/sync', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                body: JSON.stringify({ cart })
            }).catch(err => console.warn('Cart sync failed:', err));

            await fetch('/api/favorites/sync', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                body: JSON.stringify({ favorites: favs })
            }).catch(err => console.warn('Favorites sync failed:', err));

            const profile = getProfile();
            if (profile) {
                await syncProfile(profile);
            }
        } catch (err) {
            console.log('Local sync failed:', err);
        } finally {
            isSyncing = false;
        }
        await syncPendingOrders();
    }

    function sync() {
        if (!navigator.onLine) return;
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            debounceTimer = null;
            performSync();
        }, DEBOUNCE_DELAY);
    }

    async function syncProfile(profile) {
        if (!navigator.onLine) return false;
        try {
            const csrfToken = window.csrfToken || '';
            const response = await fetch('/api/profile/sync', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken},
                body: JSON.stringify(profile)
            });
            return response.ok;
        } catch (err) {
            console.log('Profile sync failed:', err);
            return false;
        }
    }

    function addToCart(productId, qty, productData) {
        const cart = getCart();
        const key = String(productId);
        cart[key] = (cart[key] || 0) + qty;
        setCart(cart);
        if (productData) cacheProduct(productData);
        updateCartBadges();
        sync();
    }

    function updateCart(productId, qty) {
        const cart = getCart();
        const key = String(productId);
        if (qty < 1) delete cart[key];
        else cart[key] = qty;
        setCart(cart);
        updateCartBadges();
        sync();
    }

    function removeFromCart(productId) {
        updateCart(productId, 0); // تحديث محلي وحذف من localStorage

        // إرسال طلب حذف للخادم لتحديث الجلسة وقاعدة البيانات
        if (navigator.onLine && typeof csrfToken !== 'undefined' && csrfToken) {
            fetch(`/cart/update/${productId}`, {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': csrfToken,
                    'Accept': 'application/json'
                },
                body: new URLSearchParams({ action: 'remove' })
            }).then(res => res.json())
              .then(data => {
                  if (data.status === 'success') {
                      updateCartBadges();
                  }
              })
              .catch(err => console.warn('Remove from server failed:', err));
        }
    }

    function toggleFavorite(type, id, itemData) {
        const favs = getFavorites();
        const key = type === 'product' ? 'products' : 'stores';
        const index = favs[key].indexOf(id);
        if (index > -1) {
            favs[key].splice(index, 1);
        } else {
            favs[key].push(id);
            if (itemData && type === 'product') cacheProduct(itemData);
            else if (itemData && type === 'store') cacheStore(itemData);
        }
        setFavorites(favs);
        sync();
    }

    function isFavorite(type, id) {
        const favs = getFavorites();
        const key = type === 'product' ? 'products' : 'stores';
        return favs[key].includes(id);
    }

    // الاستماع لعودة الاتصال
    window.addEventListener('online', () => {
        if (debounceTimer) {
            clearTimeout(debounceTimer);
            debounceTimer = null;
        }
        performSync();
    });

    // تهيئة الثيم عند التحميل
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }

    // مزامنة عند التحميل
    if (document.readyState === 'complete') {
        sync();
    } else {
        window.addEventListener('load', () => {
            if (navigator.onLine) sync();
        });
    }

    return {
        getTheme, setTheme, toggleTheme, updateThemeButton, applyTheme,
        getCart, setCart, getFavorites, setFavorites, getProductsCache,
        updateCartBadges, sync, syncProfile, addToCart, updateCart,
        removeFromCart, toggleFavorite, isFavorite, cacheProduct,
        cacheStores, cacheStore, getProfile, setProfile, cacheProfile
    };
})();
