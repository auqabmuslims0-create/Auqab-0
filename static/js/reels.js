// ========== منطق الفيديو الموحد لجميع الصفحات ==========
(function() {
    'use strict';

    // مجموعة لتتبع الفيديوهات التي تم تسجيل مشاهدتها في هذه الجلسة (لمنع التكرار)
    const viewedReels = new Set();

    function getVideoContainer(video) {
        return video.closest('.reel-slide, .product-reel-slide') || video.parentElement;
    }

    function getOverlay(container, attr) {
        return container ? container.querySelector(`[${attr}]`) : null;
    }

    function pauseAllVideos(exceptVideo) {
        document.querySelectorAll('video').forEach(video => {
            if (video !== exceptVideo && !video.paused) {
                video.pause();
                const container = getVideoContainer(video);
                if (container) {
                    const overlay = getOverlay(container, 'data-play-overlay');
                    if (overlay) overlay.classList.remove('hidden');
                }
            }
        });
    }

    function showSpinner(video) {
        const spinner = getOverlay(getVideoContainer(video), 'data-video-spinner');
        if (spinner) spinner.classList.add('show');
    }

    function hideSpinner(video) {
        const spinner = getOverlay(getVideoContainer(video), 'data-video-spinner');
        if (spinner) spinner.classList.remove('show');
    }

    function showPlayOverlay(video) {
        const overlay = getOverlay(getVideoContainer(video), 'data-play-overlay');
        if (overlay) overlay.classList.remove('hidden');
    }

    function hidePlayOverlay(video) {
        const overlay = getOverlay(getVideoContainer(video), 'data-play-overlay');
        if (overlay) overlay.classList.add('hidden');
    }

    // ===== U12: زر الإيقاف المؤقت =====
    function showPauseButton(video) {
        const container = getVideoContainer(video);
        const overlay = getOverlay(container, 'data-pause-overlay');
        if (!overlay) return;
        overlay.classList.remove('hidden');
        overlay.classList.add('visible');
        // إخفاء تلقائي بعد 1.2 ثانية
        clearTimeout(overlay._hideTimer);
        overlay._hideTimer = setTimeout(() => {
            overlay.classList.remove('visible');
        }, 1200);
    }

    function hidePauseButton(video) {
        const overlay = getOverlay(getVideoContainer(video), 'data-pause-overlay');
        if (!overlay) return;
        clearTimeout(overlay._hideTimer);
        overlay.classList.remove('visible');
        overlay.classList.add('hidden');
    }

    // ===== S2: تسجيل المشاهدة =====
    function recordView(video) {
        const reelId = video.getAttribute('data-reel-id');
        if (!reelId || viewedReels.has(reelId)) return;
        // نسجل فقط فيديوهات الريلز (وليس فيديوهات المنتجات في لوحة صاحب المتجر)
        if (!video.hasAttribute('data-reel-video')) return;
        viewedReels.add(reelId);
        fetch(`/api/reels/${reelId}/view`, {
            method: 'POST',
            headers: { 'Accept': 'application/json' }
        }).catch(() => { /* تجاهل الأخطاء بصمت */ });
    }

    function playVideo(video) {
        if (!video) return;
        pauseAllVideos(video);
        hidePlayOverlay(video);
        if (video.readyState < 3) showSpinner(video);
        video.muted = false;
        const playPromise = video.play();
        if (playPromise && playPromise.then) {
            playPromise.then(() => {
                hideSpinner(video);
                showPauseButton(video);
                // بدء مؤقّت تسجيل المشاهدة
                clearTimeout(video._viewTimer);
                video._viewTimer = setTimeout(() => recordView(video), 2000);
            }).catch((error) => {
                console.warn('تعذر تشغيل الفيديو:', error);
                hideSpinner(video);
                showPlayOverlay(video);
            });
        }
    }

    function pauseVideo(video) {
        if (!video) return;
        video.pause();
        showPlayOverlay(video);
        hidePauseButton(video);
        hideSpinner(video);
        clearTimeout(video._viewTimer);
    }

    function toggleVideo(video) {
        if (video.paused) playVideo(video);
        else pauseVideo(video);
    }

    function attachVideo(video) {
        const container = getVideoContainer(video);
        if (!container) return;

        // زر التشغيل (يظهر عند الإيقاف)
        const playBtn = getOverlay(container, 'data-play-btn');
        if (playBtn) {
            playBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                playVideo(video);
            });
        }

        // U12: زر الإيقاف المؤقت (يظهر عند التشغيل)
        const pauseBtn = getOverlay(container, 'data-pause-btn');
        if (pauseBtn) {
            pauseBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                pauseVideo(video);
            });
        }

        // النقر على الفيديو يبدّل
        video.addEventListener('click', function() {
            toggleVideo(video);
        });

        // أحداث الحالة
        video.addEventListener('waiting', () => showSpinner(video));
        video.addEventListener('playing', () => {
            hideSpinner(video);
            hidePlayOverlay(video);
            showPauseButton(video);
        });
        video.addEventListener('canplaythrough', () => hideSpinner(video));
        video.addEventListener('pause', () => {
            showPlayOverlay(video);
            hidePauseButton(video);
            hideSpinner(video);
        });
        video.addEventListener('ended', () => {
            showPlayOverlay(video);
            hidePauseButton(video);
            hideSpinner(video);
        });

        // S2: فيديوهات صاحب المتجر — لا تشغيل تلقائي
        if (video.hasAttribute('data-owner-reel-video')) {
            video.pause();
            video.autoplay = false;
        }
    }

    document.addEventListener('DOMContentLoaded', function() {
        const videos = document.querySelectorAll(
            '[data-reel-video], [data-store-reel-video], [data-owner-reel-video], [data-product-reel-video]'
        );
        videos.forEach(attachVideo);

        // مراقب التمرير: تشغيل تلقائي فقط لريلز الزبون (data-reel-video)
        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    const video = entry.target;
                    if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
                        if (video.paused) playVideo(video);
                    } else {
                        if (!video.paused) pauseVideo(video);
                    }
                });
            }, { threshold: 0.6 });

            videos.forEach(video => {
                if (video.hasAttribute('data-reel-video')) {
                    observer.observe(video);
                }
            });
        }
    });
})();

// ========== دوال عامة للتفاعل والمشاركة ==========
function toggleReelReaction(reelId, reactionType, button) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || window.csrfToken || '';
    fetch(`/api/reels/${reelId}/reaction`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken
        },
        body: JSON.stringify({ reaction_type: reactionType })
    })
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(() => {
        button.classList.toggle('active');
        const icon = button.querySelector('i');
        if (icon) {
            icon.classList.toggle('bi-heart');
            icon.classList.toggle('bi-heart-fill');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        if (typeof showToast === 'function') showToast('حدث خطأ، حاول لاحقاً', 'error');
    });
}

function shareReel(reelId, title) {
    if (navigator.share) {
        navigator.share({
            title: title || 'ريلز',
            url: `${window.location.origin}/reels#reel-${reelId}`
        }).catch(() => {});
    } else {
        const url = `${window.location.origin}/reels#reel-${reelId}`;
        navigator.clipboard.writeText(url).then(() => {
            if (typeof showToast === 'function') showToast('تم نسخ الرابط', 'success');
        }).catch(() => {
            if (typeof showToast === 'function') showToast('تعذر نسخ الرابط', 'error');
        });
    }
}
