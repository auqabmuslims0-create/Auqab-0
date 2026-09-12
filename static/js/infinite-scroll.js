/* التمرير اللانهائي — يعمل على صفحات: السوق، العروض، المتاجر، الريلز */
(function () {
  function initInfiniteScroll() {
    var sentinel = document.getElementById('scroll-sentinel');
    if (!sentinel) return;

    var targetSel = sentinel.dataset.target || '#items-grid';
    var target    = document.querySelector(targetSel);
    var loader    = document.getElementById('scroll-loader');
    if (!target) return;

    var loading  = false;
    var nextPage = sentinel.dataset.nextPage || '';
    if (!nextPage) return; // لا مزيد من الصفحات

    function loadMore() {
      if (loading || !nextPage) return;
      loading = true;
      if (loader) {
        loader.style.display = 'block';
        loader.textContent = 'جارٍ التحميل…';
      }

      var params = new URLSearchParams(window.location.search);
      params.set('page', nextPage);
      params.set('format', 'json');

      fetch(window.location.pathname + '?' + params.toString(), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
        cache: 'no-store'
      })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (data.html) target.insertAdjacentHTML('beforeend', data.html);

        if (data.has_next && data.next_page) {
          nextPage = data.next_page;
          sentinel.dataset.nextPage = nextPage;
          if (loader) loader.style.display = 'none';
        } else {
          nextPage = '';
          sentinel.dataset.nextPage = '';
          if (loader) {
            loader.textContent = '— لا توجد نتائج أخرى —';
            loader.style.display = 'block';
          }
          observer.disconnect();
        }
      })
      .catch(function (e) {
        console.error('[infinite-scroll]', e);
        if (loader) loader.textContent = 'تعذّر التحميل، حاول مجدداً.';
      })
      .finally(function () { loading = false; });
    }

    var observer = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) loadMore();
    }, { rootMargin: '400px 0px' });

    observer.observe(sentinel);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initInfiniteScroll);
  } else {
    initInfiniteScroll();
  }
})();
