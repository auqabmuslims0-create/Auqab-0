/**
 * Navigation Module - تحسين سلوك التنقل ومعالجة مشكلة زر الرجوع
 * v1: تم إصلاح MutationObserver لتجنب الحلقات اللانهائية
 * (كان يقرأ .badge.bg-warning العام ويجد شارات الطلبات).
 */
(function() {
    'use strict';

    // ========== إصلاح مشكلة زر الرجوع بعد الإجراءات ==========
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
        return originalFetch.apply(this, args).then(response => {
            if (response.ok && (args[1]?.method === 'POST' || args[1]?.method === 'PUT' || args[1]?.method === 'DELETE')) {
                replaceCurrentState();
            }
            return response;
        }).catch(err => {
            console.warn('Navigation fetch error:', err);
            throw err;
        });
    };

    const originalXHROpen = XMLHttpRequest.prototype.open;
    const originalXHRSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        this._navMethod = method;
        return originalXHROpen.call(this, method, url, ...rest);
    };
    XMLHttpRequest.prototype.send = function(...args) {
        this.addEventListener('load', function() {
            if (this.status >= 200 && this.status < 300 && this._navMethod && ['POST', 'PUT', 'DELETE'].includes(this._navMethod)) {
                replaceCurrentState();
            }
        });
        return originalXHRSend.apply(this, args);
    };

    function replaceCurrentState() {
        if (window.history && window.history.replaceState) {
            try {
                window.history.replaceState({ nav: true }, document.title, window.location.href);
            } catch (e) {
                console.warn('replaceState failed', e);
            }
        }
    }

    document.addEventListener('click', function(e) {
        const target = e.target.closest('[data-nav-replace]');
        if (target) {
            setTimeout(replaceCurrentState, 0);
        }
    });

    // ========== إغلاق القائمة الجانبية عند النقر على عنصر ==========
    document.addEventListener('click', function(e) {
        const sidebar = document.getElementById('sidebarMenu');
        if (!sidebar || !sidebar.classList.contains('show')) return;

        const menuItem = e.target.closest('.sidebar-menu-item');
        if (menuItem) {
            const offcanvasInstance = bootstrap.Offcanvas.getInstance(sidebar);
            if (offcanvasInstance) {
                offcanvasInstance.hide();
            }
        }
        if (!sidebar.contains(e.target) && !e.target.closest('[data-bs-toggle="offcanvas"]')) {
            const offcanvasInstance = bootstrap.Offcanvas.getInstance(sidebar);
            if (offcanvasInstance) {
                offcanvasInstance.hide();
            }
        }
    });

    // ========== تحديث حالة الأزرار النشطة ==========
    function setActiveNavItems() {
        const currentPath = window.location.pathname;
        const currentHash = window.location.hash;
        const fullPath = currentPath + currentHash;

        document.querySelectorAll('.bottom-nav-item').forEach(link => {
            const href = link.getAttribute('href');
            if (href && fullPath === href) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });

        document.querySelectorAll('.sidebar-menu-item').forEach(link => {
            const href = link.getAttribute('href');
            if (href && fullPath === href) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    // ========== شارة الإشعارات ==========
    // v1: نستهدف فقط شارة الإشعارات داخل السايدبار (وليس أي .badge.bg-warning في الصفحة).
    let _navDotUpdating = false;

    function updateNotificationDot(count) {
        const dot = document.getElementById('navNotificationDot');
        if (!dot) return;
        if (count > 0) {
            dot.style.display = 'flex';
            dot.textContent = count > 9 ? '9+' : String(count);
            dot.style.fontSize = '0.6rem';
            dot.style.alignItems = 'center';
            dot.style.justifyContent = 'center';
            dot.style.width = '16px';
            dot.style.height = '16px';
            dot.style.borderRadius = '50%';
        } else {
            dot.style.display = 'none';
            if (dot.textContent !== '') {
                dot.textContent = '';
            }
            dot.style.width = '10px';
            dot.style.height = '10px';
            dot.style.borderRadius = '50%';
        }
    }

    function syncNotificationDotFromSidebar() {
        // v1: محدود جداً — يقرأ فقط شارة الإشعارات في السايدبار
        if (_navDotUpdating) return;
        const badge = document.querySelector('.sidebar-menu-item .badge.bg-warning');
        if (!badge) return;

        const count = parseInt(badge.textContent, 10);
        if (isNaN(count)) return;

        _navDotUpdating = true;
        try {
            updateNotificationDot(count);
        } finally {
            // نحرر القفل بعد إطارين لتفادي الحلقات المتسلسلة
            setTimeout(() => { _navDotUpdating = false; }, 100);
        }
    }

    // v1: نراقب فقط العقد المُضافة/المُحذوفة، مع throttle عبر setTimeout
    let observerThrottle = null;
    const observer = new MutationObserver(() => {
        if (observerThrottle) return;
        observerThrottle = setTimeout(() => {
            observerThrottle = null;
            syncNotificationDotFromSidebar();
        }, 200);
    });

    document.addEventListener('DOMContentLoaded', function() {
        setActiveNavItems();
        syncNotificationDotFromSidebar();

        // نبدأ المراقبة فقط بعد التحميل الكامل
        const target = document.getElementById('sidebarMenu');
        if (target) {
            observer.observe(target, { childList: true, subtree: true });
        }

        if (typeof LocalStore !== 'undefined') {
            const updateTopThemeBtn = function() {
                const topThemeBtn = document.getElementById('topbarThemeToggle');
                if (!topThemeBtn) return;
                const theme = LocalStore.getTheme();
                const icon = topThemeBtn.querySelector('i');
                if (icon) {
                    if (theme === 'dark') {
                        icon.className = 'bi bi-sun';
                    } else if (theme === 'light') {
                        icon.className = 'bi bi-moon-stars';
                    } else {
                        icon.className = 'bi bi-circle-half';
                    }
                }
            };
            updateTopThemeBtn();
            window.addEventListener('themeChanged', updateTopThemeBtn);
        }
    });

    window.Navigation = {
        replaceCurrentState: replaceCurrentState,
        setActiveNavItems: setActiveNavItems,
        updateNotificationDot: updateNotificationDot
    };

})();
