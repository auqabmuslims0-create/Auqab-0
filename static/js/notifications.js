/**
 * notifications.js - منطق صفحة الإشعارات
 * - فلترة (الكل/غير مقروء/النوع)
 * - تجميع زمني (اليوم/أمس/آخر 7 أيام/أقدم)
 * - تحديثات فورية (optimistic)
 * - Load More
 */
(function() {
    'use strict';

    const API = '/api/notifications';
    const PER_PAGE = 20;

    let state = {
        type: null,
        read: null,
        page: 1,
        totalPages: 1,
        items: [],
        loading: false,
        selectMode: false,
        selectedIds: new Set(),
    };

    // ═════ عناصر DOM ═════
    const listEl = document.getElementById('notificationsList');
    const loadMoreWrapper = document.getElementById('loadMoreWrapper');
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    const emptyStateEl = document.getElementById('notificationsEmpty');
    const loadingSpinner = document.getElementById('notificationsLoading');
    const filterTabs = document.querySelectorAll('[data-filter]');
    const toolbar = document.getElementById('notificationsToolbar');
    const selectModeBtn = document.getElementById('selectModeBtn');
    const actionsDropdown = document.getElementById('bulkActionsDropdown');
    const cancelSelectBtn = document.getElementById('cancelSelectBtn');
    const selectedCountEl = document.getElementById('selectedCount');
    const bulkMarkReadBtn = document.getElementById('bulkMarkReadBtn');
    const bulkDeleteBtn = document.getElementById('bulkDeleteBtn');

    // ═════ أدوات مساعدة ═════
    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function showToastSafe(msg, type) {
        if (typeof window.showToast === 'function') window.showToast(msg, type);
    }

    async function confirmAction(msg) {
        if (typeof window.showConfirm === 'function') return await window.showConfirm(msg);
        return window.confirm(msg);
    }

    function getCsrfToken() {
        return window.csrfToken || '';
    }

    // ═════ تجميع زمني ═════
    function getTimeGroup(isoString) {
        if (!isoString) return { label: 'أقدم', order: 4 };
        const date = new Date(isoString);
        const now = new Date();
        const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const startOfYesterday = new Date(startOfToday);
        startOfYesterday.setDate(startOfYesterday.getDate() - 1);
        const sevenDaysAgo = new Date(startOfToday);
        sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

        if (date >= startOfToday) return { label: 'اليوم', order: 1 };
        if (date >= startOfYesterday) return { label: 'أمس', order: 2 };
        if (date >= sevenDaysAgo) return { label: 'آخر 7 أيام', order: 3 };
        return { label: 'أقدم', order: 4 };
    }

    // ═════ أيقونات ═════
    function getIconClass(type) {
        return `icon-${type || 'default'}`;
    }
    function getIconName(type) {
        const map = {
            'order': 'bi-bag-check',
            'subscription': 'bi-arrow-repeat',
            'delivery': 'bi-truck',
            'message': 'bi-chat-dots',
            'alert': 'bi-exclamation-triangle-fill',
            'store_follow': 'bi-person-plus',
            'new_product': 'bi-box-seam',
            'new_offer': 'bi-tags',
            'reel': 'bi-film',
        };
        return map[type] || 'bi-bell';
    }

    // ═════ HTML البطاقة ═════
    function notificationCardHtml(notif) {
        const readClass = notif.is_read ? 'read' : 'unread';
        const checked = state.selectedIds.has(notif.id) ? 'checked' : '';
        const selectCheckbox = state.selectMode
            ? `<label class="notif-checkbox-wrap">
                   <input type="checkbox" class="notif-checkbox" data-id="${notif.id}" ${checked}>
               </label>`
            : '';
        const unreadDot = !notif.is_read ? '<span class="unread-dot"></span>' : '';
        const linkHtml = notif.link
            ? `<a href="${escapeHtml(notif.link)}" class="notif-open-btn" data-id="${notif.id}">
                   <i class="bi bi-box-arrow-up-left"></i> عرض
               </a>`
            : '';
        const time = notif.created_at ? notif.created_at.substring(11, 16) : '';
        const dateFull = notif.created_at || '';

        return `
        <div class="notif-card ${readClass}" data-id="${notif.id}" data-iso="${escapeHtml(notif.created_at_iso || '')}">
            ${unreadDot}
            ${selectCheckbox}
            <div class="notif-icon ${getIconClass(notif.type)}">
                <i class="bi ${getIconName(notif.type)}"></i>
            </div>
            <div class="notif-body">
                ${notif.title ? `<div class="notif-title">${escapeHtml(notif.title)}</div>` : ''}
                <div class="notif-message">${escapeHtml(notif.message)}</div>
                <div class="notif-meta">
                    <span class="notif-time" title="${escapeHtml(dateFull)}">
                        <i class="bi bi-clock"></i> ${escapeHtml(time)}
                    </span>
                    ${linkHtml}
                </div>
            </div>
            ${!state.selectMode ? `
            <div class="notif-actions">
                ${!notif.is_read ? `
                <button class="notif-action-btn" data-action="mark-read" data-id="${notif.id}" title="تعليم كمقروء">
                    <i class="bi bi-check2"></i>
                </button>` : ''}
                <button class="notif-action-btn danger" data-action="delete" data-id="${notif.id}" title="حذف">
                    <i class="bi bi-trash"></i>
                </button>
            </div>` : ''}
        </div>`;
    }

    // ═════ render القائمة ═════
    function renderList() {
        if (!listEl) return;

        if (state.items.length === 0) {
            listEl.innerHTML = '';
            if (emptyStateEl) emptyStateEl.style.display = 'block';
            if (loadMoreWrapper) loadMoreWrapper.style.display = 'none';
            return;
        }

        if (emptyStateEl) emptyStateEl.style.display = 'none';

        // تجميع حسب الزمن
        const groups = {};
        state.items.forEach(n => {
            const g = getTimeGroup(n.created_at_iso);
            if (!groups[g.label]) groups[g.label] = { order: g.order, items: [] };
            groups[g.label].items.push(n);
        });

        const sortedGroups = Object.entries(groups)
            .sort((a, b) => a[1].order - b[1].order);

        let html = '';
        sortedGroups.forEach(([label, group]) => {
            html += `<div class="notif-group">
                <div class="notif-group-header">${escapeHtml(label)}</div>
                <div class="notif-group-body">`;
            group.items.forEach(n => {
                html += notificationCardHtml(n);
            });
            html += `</div></div>`;
        });

        listEl.innerHTML = html;

        // حالة زر load more
        if (loadMoreWrapper) {
            loadMoreWrapper.style.display = state.page < state.totalPages ? 'block' : 'none';
        }
    }

    // ═════ جلب البيانات ═════
    async function fetchNotifications({ append = false } = {}) {
        if (state.loading) return;
        state.loading = true;

        if (loadingSpinner) loadingSpinner.style.display = 'block';

        const params = new URLSearchParams();
        if (state.type) params.set('type', state.type);
        if (state.read === false) params.set('read', 'false');
        if (state.read === true) params.set('read', 'true');
        params.set('page', state.page);
        params.set('per_page', PER_PAGE);

        try {
            const res = await fetch(`${API}?${params.toString()}`, {
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin',
            });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();

            if (append) {
                state.items = state.items.concat(data.notifications || []);
            } else {
                state.items = data.notifications || [];
            }
            state.totalPages = data.pagination?.total_pages || 1;
            state.page = data.pagination?.page || 1;

            renderList();

            // تحديث شارات الفلترة
            fetchCounts();

            // تحديث شارة السايدبار
            updateSidebarBadge(data.unread_count);
        } catch (err) {
            console.error('fetch notifications failed:', err);
            showToastSafe('تعذر تحميل الإشعارات', 'error');
        } finally {
            state.loading = false;
            if (loadingSpinner) loadingSpinner.style.display = 'none';
        }
    }

    async function fetchCounts() {
        try {
            const res = await fetch(`${API}/counts`, {
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin',
            });
            if (!res.ok) return;
            const data = await res.json();
            updateFilterBadges(data);
        } catch (_) { /* صامت */ }
    }

    function updateFilterBadges(counts) {
        document.querySelectorAll('[data-filter-badge]').forEach(el => {
            const key = el.dataset.filterBadge;
            let value = 0;
            if (key === 'total') value = counts.total || 0;
            else if (key === 'unread') value = counts.unread || 0;
            else if (counts.by_type && counts.by_type[key] !== undefined) value = counts.by_type[key];
            if (value > 0) {
                el.textContent = value > 99 ? '99+' : value;
                el.style.display = 'inline-block';
            } else {
                el.style.display = 'none';
            }
        });
    }

    function updateSidebarBadge(count) {
        const badge = document.querySelector('.nav-badge-notifications[data-notif-badge]');
        const dot = document.getElementById('navNotificationDot');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline';
            } else {
                badge.style.display = 'none';
            }
        }
        if (dot) {
            dot.style.display = count > 0 ? 'flex' : 'none';
        }
    }

    // ═════ أحداث القائمة (event delegation) ═════
    if (listEl) {
        listEl.addEventListener('click', async (e) => {
            const actionBtn = e.target.closest('[data-action]');
            if (actionBtn) {
                const id = parseInt(actionBtn.dataset.id);
                const action = actionBtn.dataset.action;

                if (action === 'mark-read') {
                    await markRead(id);
                } else if (action === 'delete') {
                    const ok = await confirmAction('هل تريد حذف هذا الإشعار؟');
                    if (ok) await deleteNotification(id);
                }
                return;
            }

            const openBtn = e.target.closest('.notif-open-btn');
            if (openBtn) {
                const id = parseInt(openBtn.dataset.id);
                markRead(id, { silent: true });
                return;
            }

            // النقر على البطاقة في وضع التحديد يبدّل الـ checkbox
            const card = e.target.closest('.notif-card');
            if (card && state.selectMode) {
                const cb = card.querySelector('.notif-checkbox');
                if (cb && e.target !== cb && !e.target.closest('.notif-checkbox-wrap')) {
                    cb.checked = !cb.checked;
                    onCheckboxChange(cb);
                }
            }
        });

        listEl.addEventListener('change', (e) => {
            if (e.target.classList.contains('notif-checkbox')) {
                onCheckboxChange(e.target);
            }
        });
    }

    function onCheckboxChange(cb) {
        const id = parseInt(cb.dataset.id);
        if (cb.checked) state.selectedIds.add(id);
        else state.selectedIds.delete(id);
        updateSelectionUI();
    }

    // ═════ عمليات ═════
    async function markRead(id, { silent = false } = {}) {
        // تحديث فوري
        const idx = state.items.findIndex(n => n.id === id);
        if (idx >= 0 && state.items[idx].is_read) return; // مقروء أصلاً

        const previous = idx >= 0 ? { ...state.items[idx] } : null;
        if (idx >= 0) {
            state.items[idx].is_read = true;
            renderList();
        }

        try {
            const res = await fetch(`${API}/${id}/read`, {
                method: 'POST',
                headers: { 'X-CSRF-Token': getCsrfToken(), 'Accept': 'application/json' },
            });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            updateSidebarBadge(data.unread_count);
            if (!silent) showToastSafe('تم التحديد كمقروء', 'success');
        } catch (err) {
            // rollback
            if (previous && idx >= 0) {
                state.items[idx] = previous;
                renderList();
            }
            if (!silent) showToastSafe('فشل التحديث', 'error');
        }
    }

    async function deleteNotification(id) {
        const idx = state.items.findIndex(n => n.id === id);
        if (idx < 0) return;
        const removed = state.items.splice(idx, 1)[0];
        state.selectedIds.delete(id);
        renderList();

        try {
            const res = await fetch(`${API}/${id}`, {
                method: 'DELETE',
                headers: { 'X-CSRF-Token': getCsrfToken(), 'Accept': 'application/json' },
            });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            updateSidebarBadge(data.unread_count);
            showToastSafe('تم الحذف', 'success');
            // أعد جلب العدّادات
            fetchCounts();
        } catch (err) {
            // rollback
            state.items.splice(idx, 0, removed);
            renderList();
            showToastSafe('فشل الحذف', 'error');
        }
    }

    // ═════ الفلترة ═════
    filterTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            filterTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const filter = tab.dataset.filter;
            const val = tab.dataset.value;

            if (filter === 'read') {
                state.read = null;
            } else if (filter === 'unread') {
                state.read = false;
            } else if (filter === 'type') {
                state.type = val || null;
                state.read = null;
            } else {
                state.type = null;
                state.read = null;
            }

            state.page = 1;
            state.items = [];
            exitSelectMode();
            fetchNotifications();
        });
    });

    // ═════ Load More ═════
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', async () => {
            if (state.page >= state.totalPages || state.loading) return;
            state.page++;
            await fetchNotifications({ append: true });
        });
    }

    // ═════ إجراءات جماعية ═════
    if (selectModeBtn) {
        selectModeBtn.addEventListener('click', () => {
            state.selectMode = !state.selectMode;
            state.selectedIds.clear();
            updateSelectionUI();
            renderList();
        });
    }

    if (cancelSelectBtn) {
        cancelSelectBtn.addEventListener('click', () => {
            exitSelectMode();
            renderList();
        });
    }

    function exitSelectMode() {
        state.selectMode = false;
        state.selectedIds.clear();
        updateSelectionUI();
    }

    function updateSelectionUI() {
        if (selectedCountEl) selectedCountEl.textContent = state.selectedIds.size;
        if (toolbar) toolbar.classList.toggle('active', state.selectMode);
        if (bulkMarkReadBtn) bulkMarkReadBtn.disabled = state.selectedIds.size === 0;
        if (bulkDeleteBtn) bulkDeleteBtn.disabled = state.selectedIds.size === 0;
    }

    if (bulkMarkReadBtn) {
        bulkMarkReadBtn.addEventListener('click', async () => {
            const ids = Array.from(state.selectedIds);
            if (ids.length === 0) return;
            for (const id of ids) {
                await markRead(id, { silent: true });
            }
            showToastSafe(`تم تحديد ${ids.length} إشعار كمقروء`, 'success');
            exitSelectMode();
            renderList();
        });
    }

    if (bulkDeleteBtn) {
        bulkDeleteBtn.addEventListener('click', async () => {
            const ids = Array.from(state.selectedIds);
            if (ids.length === 0) return;
            const ok = await confirmAction(`هل تريد حذف ${ids.length} إشعار محدد؟`);
            if (!ok) return;

            try {
                const res = await fetch(`${API}/delete-selected`, {
                    method: 'POST',
                    headers: {
                        'X-CSRF-Token': getCsrfToken(),
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                    },
                    body: JSON.stringify({ ids }),
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                state.items = state.items.filter(n => !ids.includes(n.id));
                updateSidebarBadge(data.unread_count);
                showToastSafe(`تم حذف ${ids.length} إشعار`, 'success');
                exitSelectMode();
                renderList();
                fetchCounts();
            } catch (err) {
                showToastSafe('فشل الحذف الجماعي', 'error');
            }
        });
    }

    // ═════ شريط الأدوات ═════
    const markAllReadBtn = document.getElementById('markAllReadBtn');
    if (markAllReadBtn) {
        markAllReadBtn.addEventListener('click', async () => {
            try {
                const res = await fetch(`${API}/read-all`, {
                    method: 'POST',
                    headers: { 'X-CSRF-Token': getCsrfToken(), 'Accept': 'application/json' },
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                showToastSafe('تم تحديد الكل كمقروء', 'success');
                state.items = [];
                state.page = 1;
                await fetchNotifications();
            } catch (err) {
                showToastSafe('فشل التحديث', 'error');
            }
        });
    }

    const deleteReadBtn = document.getElementById('deleteReadBtn');
    if (deleteReadBtn) {
        deleteReadBtn.addEventListener('click', async () => {
            const ok = await confirmAction('هل تريد حذف جميع الإشعارات المقروءة؟');
            if (!ok) return;
            try {
                const res = await fetch(`${API}/read`, {
                    method: 'DELETE',
                    headers: { 'X-CSRF-Token': getCsrfToken(), 'Accept': 'application/json' },
                });
                if (!res.ok) throw new Error('HTTP ' + res.status);
                showToastSafe('تم حذف المقروءة', 'success');
                state.items = [];
                state.page = 1;
                await fetchNotifications();
            } catch (err) {
                showToastSafe('فشل الحذف', 'error');
            }
        });
    }

    // ═════ Push ═════
    const enablePushBtn = document.getElementById('enablePushBtn');
    if (enablePushBtn) {
        enablePushBtn.addEventListener('click', async () => {
            if (typeof window.enablePushNotifications === 'function') {
                await window.enablePushNotifications();
            } else {
                showToastSafe('ميزة الإشعارات الفورية غير متوفرة', 'error');
            }
        });
    }

    // ═════ أوفلاين ═════
    function updateOnlineState() {
        const offlineBanner = document.getElementById('offlineBanner');
        if (offlineBanner) {
            offlineBanner.style.display = navigator.onLine ? 'none' : 'block';
        }
    }
    window.addEventListener('online', () => {
        updateOnlineState();
        state.page = 1;
        state.items = [];
        fetchNotifications();
    });
    window.addEventListener('offline', updateOnlineState);

    // ═════ تهيئة ═════
    updateOnlineState();
    fetchNotifications();
})();
