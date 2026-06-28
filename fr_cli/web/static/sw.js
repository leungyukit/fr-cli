"""
PWA Service Worker —— 离线缓存 fr-cli Web 控制台
"""
const CACHE_NAME = 'fr-cli-console-v1';
const STATIC_ASSETS = [
    '/',
    '/manifest.json',
    '/icon.svg',
];

// 安装:预缓存静态资源
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS).catch(() => {
                // 部分资源可能不存在,跳过
            });
        })
    );
    self.skipWaiting();
});

// 激活:清理旧缓存
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.filter((name) => name !== CACHE_NAME)
                    .map((name) => caches.delete(name))
            );
        })
    );
    self.clients.claim();
});

// fetch:网络优先,失败降级到缓存
self.addEventListener('fetch', (event) => {
    const { request } = event;

    // SSE 不缓存(实时数据)
    if (request.url.includes('/api/events')) {
        return;
    }

    // API 请求:网络优先,失败降级到缓存
    if (request.url.includes('/api/')) {
        event.respondWith(
            fetch(request).catch(() => {
                return new Response(JSON.stringify({
                    ok: false,
                    error: '离线模式,数据可能不是最新',
                    offline: true,
                }), {
                    headers: { 'Content-Type': 'application/json' },
                    status: 503,
                });
            })
        );
        return;
    }

    // 静态资源:缓存优先
    event.respondWith(
        caches.match(request).then((cached) => {
            if (cached) {
                // 后台更新
                fetch(request).then((response) => {
                    if (response.ok) {
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(request, response);
                        });
                    }
                }).catch(() => {});
                return cached;
            }
            return fetch(request).then((response) => {
                if (response.ok && request.method === 'GET') {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(request, responseClone);
                    });
                }
                return response;
            }).catch(() => {
                return new Response('离线模式', { status: 503 });
            });
        })
    );
});