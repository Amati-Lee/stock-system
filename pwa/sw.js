var CACHE_NAME = 'stock-viewer-20260716082617';
var ASSETS = ['./index.html', './manifest.json', './icons/icon-144.png', './icons/icon-192.png', './icons/icon-512.png'];

self.addEventListener('install', function(e) {
    e.waitUntil(caches.open(CACHE_NAME).then(function(c) { return c.addAll(ASSETS); }));
    self.skipWaiting();
});

self.addEventListener('activate', function(e) {
    e.waitUntil(
        caches.keys().then(function(keys) {
            return Promise.all(keys.filter(function(k) { return k !== CACHE_NAME; }).map(function(k) { return caches.delete(k); }));
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', function(e) {
    var url = e.request.url;
    if (url.indexOf('/ohlc/') !== -1 || url.indexOf('alerts.json') !== -1 || url.indexOf('.csv') !== -1 || url.indexOf('.json') !== -1) {
        e.respondWith(
            fetch(e.request).then(function(res) {
                var clone = res.clone();
                caches.open(CACHE_NAME).then(function(c) { c.put(e.request, clone); });
                return res;
            }).catch(function() { return caches.match(e.request); })
        );
    } else if (e.request.mode === 'navigate') {
        e.respondWith(
            fetch(e.request).then(function(res) {
                var clone = res.clone();
                caches.open(CACHE_NAME).then(function(c) { c.put(e.request, clone); });
                return res;
            }).catch(function() { return caches.match(e.request); })
        );
    } else {
        e.respondWith(
            caches.match(e.request).then(function(cached) { return cached || fetch(e.request); })
        );
    }
});
