// ========== منطق الفيديو الموحد لجميع الصفحات ==========
document.addEventListener('DOMContentLoaded', function() {
    const videos = document.querySelectorAll('[data-reel-video], [data-store-reel-video], [data-owner-reel-video], [data-product-reel-video]');

    function pauseAllVideos(exceptVideo) {
        videos.forEach(video => {
            if (video !== exceptVideo) {
                video.pause();
                const overlay = video.closest('.reel-slide')?.querySelector('[data-play-overlay]');
                if (overlay) overlay.classList.remove('hidden');
                const playBtn = video.closest('.reel-slide')?.querySelector('[data-play-btn]');
                if (playBtn) playBtn.classList.remove('hidden');
            }
        });
    }

    function showSpinner(video) {
        const spinner = video.closest('.reel-slide')?.querySelector('[data-video-spinner]');
        if (spinner) spinner.classList.add('show');
    }

    function hideSpinner(video) {
        const spinner = video.closest('.reel-slide')?.querySelector('[data-video-spinner]');
        if (spinner) spinner.classList.remove('show');
    }

    function showPlayBtn(video) {
        const playBtn = video.closest('.reel-slide')?.querySelector('[data-play-btn]');
        if (playBtn) playBtn.classList.remove('hidden');
        const overlay = video.closest('.reel-slide')?.querySelector('[data-play-overlay]');
        if (overlay) overlay.classList.remove('hidden');
    }

    function hidePlayBtn(video) {
        const playBtn = video.closest('.reel-slide')?.querySelector('[data-play-btn]');
        if (playBtn) playBtn.classList.add('hidden');
        const overlay = video.closest('.reel-slide')?.querySelector('[data-play-overlay]');
        if (overlay) overlay.classList.add('hidden');
    }

    function playVideo(video) {
        if (!video) return;
        pauseAllVideos(video);
        hidePlayBtn(video);
        // عرض مؤشر التحميل إذا لم تكن البيانات جاهزة
        if (video.readyState < 3) {
            showSpinner(video);
        }
        video.muted = false;
        video.play().then(() => {
            hideSpinner(video);
        }).catch((error) => {
            console.warn('تعذر تشغيل الفيديو:', error);
            hideSpinner(video);
            showPlayBtn(video);
        });
    }

    function pauseVideo(video) {
        if (!video) return;
        video.pause();
        showPlayBtn(video);
        hideSpinner(video);
    }

    // ربط الأحداث بجميع الفيديوهات
    videos.forEach(video => {
        const slide = video.closest('.reel-slide');
        if (!slide) return;

        const playBtn = slide.querySelector('[data-play-btn]');
        if (playBtn) {
            playBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                playVideo(video);
            });
        }

        video.addEventListener('click', function() {
            if (video.paused) {
                playVideo(video);
            } else {
                pauseVideo(video);
            }
        });

        video.addEventListener('waiting', function() {
            showSpinner(video);
        });
        video.addEventListener('playing', function() {
            hideSpinner(video);
            hidePlayBtn(video);
        });
        video.addEventListener('canplaythrough', function() {
            hideSpinner(video);
        });
        video.addEventListener('pause', function() {
            showPlayBtn(video);
            hideSpinner(video);
        });
        video.addEventListener('ended', function() {
            showPlayBtn(video);
            hideSpinner(video);
        });
    });

    // مراقب التمرير لتشغيل الفيديو المرئي (فقط للريلز العمودية)
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                const video = entry.target;
                if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
                    if (video.paused) {
                        playVideo(video);
                    }
                } else {
                    if (!video.paused) {
                        pauseVideo(video);
                    }
                }
            });
        }, { threshold: 0.6 });

        videos.forEach(video => {
            // نطبق المراقب فقط على فيديوهات الريلز (التي لها data-reel-video)
            if (video.hasAttribute('data-reel-video')) {
                observer.observe(video);
            }
        });
    }
});

// ========== دوال عامة للتفاعل والمشاركة ==========
function toggleReelReaction(reelId, reactionType, button) {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
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
    .then(data => {
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
