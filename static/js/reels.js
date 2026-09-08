// ========== منطق صفحة الريلز ==========
document.addEventListener('DOMContentLoaded', function() {
    const videos = document.querySelectorAll('[data-reel-video]');

    function pauseAllVideos() {
        videos.forEach(video => {
            video.pause();
            const overlay = video.closest('.reel-slide')?.querySelector('[data-play-overlay]');
            if (overlay) overlay.classList.remove('hidden');
        });
    }

    function playVideo(video) {
        pauseAllVideos();
        const slide = video.closest('.reel-slide');
        if (!slide) return;
        const spinner = slide.querySelector('[data-video-spinner]');
        if (video.readyState < 3 && spinner) {
            spinner.classList.add('show');
        }
        video.muted = false;
        video.play().then(() => {
            if (spinner) spinner.classList.remove('show');
            const overlay = slide.querySelector('[data-play-overlay]');
            if (overlay) overlay.classList.add('hidden');
            const reelId = slide.dataset.reelId;
            if (reelId && !slide.dataset.viewRecorded) {
                fetch(`/api/reels/${reelId}/view`, { method: 'POST' })
                    .then(() => { slide.dataset.viewRecorded = 'true'; })
                    .catch(() => {});
            }
        }).catch(() => {
            if (spinner) spinner.classList.remove('show');
        });
    }

    document.querySelectorAll('[data-play-btn]').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const video = this.closest('.reel-slide')?.querySelector('[data-reel-video]');
            if (video) playVideo(video);
        });
    });

    videos.forEach(video => {
        video.addEventListener('click', function() {
            if (video.paused) {
                playVideo(video);
            } else {
                video.pause();
                const overlay = video.closest('.reel-slide')?.querySelector('[data-play-overlay]');
                if (overlay) overlay.classList.remove('hidden');
            }
        });
        video.addEventListener('canplaythrough', function() {
            const spinner = video.closest('.reel-slide')?.querySelector('[data-video-spinner]');
            if (spinner) spinner.classList.remove('show');
        });
        video.addEventListener('waiting', function() {
            const spinner = video.closest('.reel-slide')?.querySelector('[data-video-spinner]');
            if (spinner) spinner.classList.add('show');
        });
        video.addEventListener('playing', function() {
            const spinner = video.closest('.reel-slide')?.querySelector('[data-video-spinner]');
            if (spinner) spinner.classList.remove('show');
        });
    });

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target;
            const slide = video.closest('.reel-slide');
            if (!slide) return;
            const overlay = slide.querySelector('[data-play-overlay]');
            if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
                playVideo(video);
            } else {
                video.pause();
                if (overlay) overlay.classList.remove('hidden');
            }
        });
    }, { threshold: 0.6 });

    videos.forEach(video => observer.observe(video));
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
