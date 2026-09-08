/**
 * Navigation Module - تحسين سلوك التنقل ومعالجة مشكلة زر الرجوع
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

    // ========== تحديث حالة الأزرار النشطة تلقائيًا ==========
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

    // ========== تحسين شارة الإشعارات في الشريط العلوي ==========
    function updateNotificationDot(count) {
        const dot = document.getElementById('navNotificationDot');
        if (dot) {
            if (count > 0) {
                dot.style.display = 'flex';
                dot.textContent = count > 9 ? '9+' : count;
                dot.style.fontSize = '0.6rem';
                dot.style.alignItems = 'center';
                dot.style.justifyContent = 'center';
                dot.style.width = '16px';
                dot.style.height = '16px';
                dot.style.borderRadius = '50%';
            } else {
                dot.style.display = 'none';
                dot.textContent = '';
                dot.style.width = '10px';
                dot.style.height = '10px';
                dot.style.borderRadius = '50%';
            }
        }
    }

    const originalFetchUpdates = window.fetchUpdates;
    if (typeof originalFetchUpdates === 'function') {
        window.fetchUpdates = function() {
            originalFetchUpdates.apply(this, arguments);
            const badge = document.querySelector('.badge.bg-warning');
            if (badge) {
                updateNotificationDot(parseInt(badge.textContent) || 0);
            }
        };
    } else {
        document.addEventListener('DOMContentLoaded', function() {
            const badge = document.querySelector('.badge.bg-warning');
            if (badge) {
                updateNotificationDot(parseInt(badge.textContent) || 0);
            }
        });
    }

    setInterval(() => {
        const badge = document.querySelector('.badge.bg-warning');
        if (badge) {
            updateNotificationDot(parseInt(badge.textContent) || 0);
        }
    }, 30000);

    document.addEventListener('DOMContentLoaded', function() {
        setActiveNavItems();

        const topThemeBtn = document.getElementById('topbarThemeToggle');
        if (topThemeBtn && typeof LocalStore !== 'undefined') {
            topThemeBtn.addEventListener('click', function() {
                LocalStore.toggleTheme();
                LocalStore.updateThemeButton();
            });
        }

        if (typeof LocalStore !== 'undefined') {
            const updateTopThemeBtn = function() {
                const theme = LocalStore.getTheme();
                const icon = topThemeBtn?.querySelector('i');
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
            const originalToggleTheme = LocalStore.toggleTheme;
            if (originalToggleTheme) {
                LocalStore.toggleTheme = function() {
                    originalToggleTheme.apply(this, arguments);
                    updateTopThemeBtn();
                };
            }
            updateTopThemeBtn();
        }
    });

    window.Navigation = {
        replaceCurrentState: replaceCurrentState,
        setActiveNavItems: setActiveNavItems,
        updateNotificationDot: updateNotificationDot
    };

})();
