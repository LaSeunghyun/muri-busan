const CACHE_NAME = 'muriopbs-v2';
const STATIC = ['/', '/onboarding.html', '/results.html', '/course.html', '/share.html', '/offline.html', '/css/style.css', '/js/app.js', '/js/onboarding.js', '/js/results.js', '/js/course.js', '/js/share.js', '/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/') || url.pathname === '/runtime-config.js') {
    // Network First for API and runtime config
    e.respondWith(
      fetch(e.request).catch(() => {
        if (url.pathname === '/runtime-config.js') {
          return new Response(
            'window.RUNTIME_CONFIG = window.RUNTIME_CONFIG || {};\nwindow.RUNTIME_CONFIG.kakaoMapKey = null;\nwindow.KAKAO_MAP_KEY = window.RUNTIME_CONFIG.kakaoMapKey;\n',
            { headers: { 'Content-Type': 'application/javascript' } }
          );
        }
        return new Response('{"error":"offline"}', { headers: {'Content-Type':'application/json'} });
      })
    );
  } else {
    // Cache First for static, offline.html fallback for navigation
    e.respondWith(caches.match(e.request).then(cached => cached || fetch(e.request).then(r => {
      const clone = r.clone();
      caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
      return r;
    }).catch(() => {
      if (e.request.mode === 'navigate') {
        return caches.match('/offline.html');
      }
      return new Response('', { status: 408 });
    })));
  }
});
