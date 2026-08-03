const CACHE_NAME = 'ogim-offline-v2'
const PRECACHE_URLS = ['/', '/index.html', '/manifest.json']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).catch(() => undefined)
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  const isApi =
    url.pathname.startsWith('/api/') ||
    url.pathname.startsWith('/stream/') ||
    url.pathname.startsWith('/kpi/') ||
    url.pathname.startsWith('/security/')

  if (isApi) {
    // API: شبکه اول؛ در خطا پاسخ خالی/کش
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone()
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
          }
          return response
        })
        .catch(() =>
          caches.match(request).then(
            (cached) =>
              cached ||
              new Response(JSON.stringify({ offline: true, alerts: [], count: 0 }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
              })
          )
        )
    )
    return
  }

  // استاتیک / اپ: کش اول، سپس شبکه و ذخیره برای آفلاین بعدی
  event.respondWith(
    caches.match(request).then((cached) => {
      const networkFetch = fetch(request)
        .then((response) => {
          if (response && response.ok) {
            const clone = response.clone()
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
          }
          return response
        })
        .catch(() => cached)
      return cached || networkFetch
    })
  )
})

self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {}
  const title = data.title || 'هشدار میدان دهلران'
  const options = {
    body: data.body || 'هشدار جدید',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    tag: data.tag || 'ogim-alert',
    data: { url: data.url || '/alerts' },
    vibrate: [200, 100, 200],
    actions: [
      { action: 'view', title: 'مشاهده' },
      { action: 'dismiss', title: 'بستن' },
    ],
  }
  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(url) && 'focus' in client) return client.focus()
      }
      return self.clients.openWindow(url)
    })
  )
})
