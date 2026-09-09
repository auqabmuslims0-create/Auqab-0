/**
 * notifications.js - إدارة صفحة الإشعارات (جلب وعرض ديناميكي، pagination، Push)
 */
document.addEventListener('DOMContentLoaded', function() {
    const listContainer = document.getElementById('notificationsList');
    const paginationContainer = document.getElementById('paginationContainer');
    const offlineContainer = document.getElementById('offlineNotificationsContainer');
    const offlineList = document.getElementById('offlineNotificationsList');
    const onlineContent = document.getElementById('onlineNotificationsContent');
    const selectAllCheckbox = document.getElementById('selectAllCheckbox');

    let currentPage = window.notificationsConfig?.currentPage || 1;
    let totalPages = window.notificationsConfig?.totalPages || 1;
    const userId = window.notificationsConfig?.userId;

    let isOnline = navigator.onLine;

    function showToast(message, type = 'info') {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        }
    }

    function getIconHtml(notif) {
        const iconMap = {
            'order': 'bi-bag-check',
            'subscription': 'bi-arrow-repeat',
            'delivery': 'bi-truck',
            'message': 'bi-chat-dots',
            'alert': 'bi-exclamation-triangle',
            'store_follow': 'bi-person-plus',
            'new_product': 'bi-box-seam',
            'new_offer': 'bi-tags',
            'reel': 'bi-film',
            'default': 'bi-bell'
        };
        const icon = iconMap[notif.type] || iconMap.default;
        return `<i class="bi ${icon}"></i>`;
    }

    function notificationItemHtml(notif) {
        const readClass = notif.is_read ? 'read' : 'unread';
        const typeClass = `icon-${notif.type || 'default'}`;
        const linkHtml = notif.link ? `<a href="${notif.link}" class="btn-link-view"><i class="bi bi-box-arrow-up-left"></i> عرض</a>` : '';
        const markReadBtn = !notif.is_read ? `
            <button class="btn btn-action btn-mark-read mark-read-btn" data-id="${notif.id}" title="تعليم كمقروء">
                <i class="bi bi-check"></i>
            </button>` : '';
        return `
            <div class="notification-item ${readClass}" data-id="${notif.id}" data-read="${notif.is_read}">
                <div class="notification-check">
                    <input type="checkbox" class="form-check-input notif-checkbox" value="${notif.id}">
                </div>
                <div class="notification-icon ${typeClass}">
                    ${getIconHtml(notif)}
                </div>
                <div class="notification-content">
                    ${notif.title ? `<div class="notification-title">${notif.title}</div>` : ''}
                    <div class="notification-message">${notif.message}</div>
                    <div class="notification-meta">
                        <span class="notification-time"><i class="bi bi-clock"></i> ${notif.created_at || ''}</span>
                        ${linkHtml}
                    </div>
                </div>
                <div class="notification-actions">
                    ${markReadBtn}
                    <button class="btn btn-action btn-delete delete-notif-btn" data-id="${notif.id}" title="حذف">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }

    function renderPagination(page, total) {
        if (!paginationContainer) return;
        if (total <= 1) {
            paginationContainer.innerHTML = '';
            return;
        }
        let html = '';
        for (let i = 1; i <= total; i++) {
            html += `<button class="btn btn-sm ${i === page ? 'btn-primary' : 'btn-outline-primary'} page-link-btn" data-page="${i}">${i}</button>`;
        }
        paginationContainer.innerHTML = html;
    }

    async function loadNotifications(page) {
        try {
            const offset = (page - 1) * 20;
            const response = await fetch(`/api/notifications?offset=${offset}&limit=20`, {
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin'
            });
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            const data = await response.json();
            if (data.notifications && data.notifications.length > 0) {
                if (listContainer) {
                    listContainer.innerHTML = data.notifications.map(notificationItemHtml).join('');
                }
                currentPage = page;
                if (data.total_pages !== undefined) {
                    totalPages = data.total_pages;
                } else {
                    totalPages = page;
                }
                renderPagination(page, totalPages);
                attachEventListeners();
                if (selectAllCheckbox) selectAllCheckbox.checked = false;
            } else {
                if (listContainer) {
                    listContainer.innerHTML = `<div class="text-center text-muted mt-5"><i class="bi bi-bell-slash fs-1"></i><p>لا توجد إشعارات</p></div>`;
                }
                if (paginationContainer) paginationContainer.innerHTML = '';
                if (selectAllCheckbox) selectAllCheckbox.checked = false;
            }
            if (data.total_unread !== undefined && typeof window.updateUnreadBadge === 'function') {
                window.updateUnreadBadge(data.total_unread);
            }
        } catch (err) {
            console.error('Error loading notifications:', err);
            // في حال الفشل، نحافظ على المحتوى الأصلي ولا نعرض رسالة خطأ
        }
    }

    function getSelectedIds() {
        return Array.from(document.querySelectorAll('.notif-checkbox:checked')).map(cb => parseInt(cb.value));
    }

    function attachEventListeners() {
        if (selectAllCheckbox) {
            selectAllCheckbox.onchange = function() {
                const checkboxes = document.querySelectorAll('.notif-checkbox');
                checkboxes.forEach(cb => cb.checked = this.checked);
            };
        }

        document.querySelectorAll('.mark-read-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const id = btn.dataset.id;
                try {
                    const res = await fetch(`/api/notifications/${id}/read`, {
                        method: 'POST',
                        headers: { 'X-CSRF-Token': window.csrfToken, 'Content-Type': 'application/json' }
                    });
                    if (res.ok) {
                        loadNotifications(currentPage);
                        showToast('تم تحديد الإشعار كمقروء', 'success');
                    } else {
                        showToast('فشل التحديث', 'error');
                    }
                } catch (err) {
                    console.error(err);
                    showToast('خطأ في الاتصال', 'error');
                }
            });
        });

        document.querySelectorAll('.delete-notif-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const id = btn.dataset.id;
                const confirmed = await window.showConfirm('هل تريد حذف هذا الإشعار؟');
                if (confirmed) {
                    try {
                        const res = await fetch(`/api/notifications/${id}`, {
                            method: 'DELETE',
                            headers: { 'X-CSRF-Token': window.csrfToken, 'Content-Type': 'application/json' }
                        });
                        if (res.ok) {
                            loadNotifications(currentPage);
                            showToast('تم حذف الإشعار', 'success');
                        } else {
                            showToast('فشل الحذف', 'error');
                        }
                    } catch (err) {
                        console.error(err);
                        showToast('خطأ في الاتصال', 'error');
                    }
                }
            });
        });

        document.querySelectorAll('.page-link-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const page = parseInt(btn.dataset.page);
                loadNotifications(page);
            });
        });
    }

    // أزرار الإجراءات الجماعية
    const markAllReadBtn = document.getElementById('markAllReadBtn');
    if (markAllReadBtn) {
        markAllReadBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/notifications/read-all', {
                    method: 'POST',
                    headers: { 'X-CSRF-Token': window.csrfToken, 'Content-Type': 'application/json' }
                });
                if (res.ok) {
                    loadNotifications(currentPage);
                    showToast('تم تحديد الكل كمقروء', 'success');
                }
            } catch (err) {
                console.error(err);
                showToast('خطأ في الاتصال', 'error');
            }
        });
    }

    const deleteReadBtn = document.getElementById('deleteReadBtn');
    if (deleteReadBtn) {
        deleteReadBtn.addEventListener('click', async () => {
            const confirmed = await window.showConfirm('هل تريد حذف جميع الإشعارات المقروءة؟');
            if (confirmed) {
                try {
                    const res = await fetch('/api/notifications/read', {
                        method: 'DELETE',
                        headers: { 'X-CSRF-Token': window.csrfToken, 'Content-Type': 'application/json' }
                    });
                    if (res.ok) {
                        loadNotifications(currentPage);
                        showToast('تم حذف المقروءة', 'success');
                    }
                } catch (err) {
                    console.error(err);
                    showToast('خطأ في الاتصال', 'error');
                }
            }
        });
    }

    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    if (deleteSelectedBtn) {
        deleteSelectedBtn.addEventListener('click', async () => {
            const ids = getSelectedIds();
            if (ids.length === 0) {
                showToast('الرجاء تحديد إشعارات للحذف', 'warning');
                return;
            }
            const confirmed = await window.showConfirm(`هل تريد حذف ${ids.length} إشعار محدد؟`);
            if (confirmed) {
                try {
                    const res = await fetch('/api/notifications/delete-selected', {
                        method: 'POST',
                        headers: { 'X-CSRF-Token': window.csrfToken, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ids: ids })
                    });
                    if (res.ok) {
                        loadNotifications(currentPage);
                        showToast('تم حذف المحدد', 'success');
                    } else {
                        showToast('فشل الحذف', 'error');
                    }
                } catch (err) {
                    console.error(err);
                    showToast('خطأ في الاتصال', 'error');
                }
            }
        });
    }

    const enablePushBtn = document.getElementById('enablePushBtn');
    if (enablePushBtn) {
        enablePushBtn.addEventListener('click', async () => {
            await window.enablePushNotifications();
        });
    }

    function showOfflineNotifications() {
        if (onlineContent) onlineContent.style.display = 'none';
        if (offlineContainer) offlineContainer.style.display = 'block';
        loadOfflineNotifications();
    }

    function showOnlineNotifications() {
        if (onlineContent) onlineContent.style.display = 'block';
        if (offlineContainer) offlineContainer.style.display = 'none';
    }

    async function loadOfflineNotifications() {
        try {
            if (typeof OfflineDB === 'undefined') return;
            const notifications = await OfflineDB.getAllNotifications();
            if (offlineList) {
                if (notifications && notifications.length > 0) {
                    offlineList.innerHTML = notifications.map(n => `
                        <div class="offline-notification-item">
                            <div class="d-flex align-items-start gap-2">
                                <div class="notification-icon icon-${n.type || 'default'}">
                                    <i class="bi bi-bell"></i>
                                </div>
                                <div class="flex-grow-1">
                                    ${n.title ? `<div class="notification-title">${n.title}</div>` : ''}
                                    <div class="notification-message">${n.message}</div>
                                    <div class="notification-meta">
                                        <span><i class="bi bi-clock"></i> ${new Date(n.created_at).toLocaleString('ar')}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `).join('');
                } else {
                    offlineList.innerHTML = '<p class="text-muted text-center">لا توجد إشعارات محفوظة</p>';
                }
            }
        } catch (err) {
            console.error('خطأ في تحميل الإشعارات من IndexedDB:', err);
        }
    }

    window.addEventListener('online', function() {
        isOnline = true;
        showOnlineNotifications();
        loadNotifications(currentPage);
    });

    window.addEventListener('offline', function() {
        isOnline = false;
        showOfflineNotifications();
    });

    // التهيئة: عرض البيانات الموجودة في الصفحة (من الخادم) بدلاً من الجلب الفوري
    if (isOnline) {
        showOnlineNotifications();
        // استدعاء الجلب لتحديث البيانات عند التحميل فقط إذا كانت الصفحة الأولى
        if (currentPage === 1) {
            // لا نقوم بالجلب الفوري لتفادي استبدال المحتوى إذا فشل، لكن يمكننا استدعاؤه
            loadNotifications(currentPage);
        }
    } else {
        showOfflineNotifications();
    }
});
