const APP_PREFIX = 'CDSS_';
const VERSION = '1.271'; // Update the version when you make changes
const CACHE_NAME = APP_PREFIX + VERSION;

const URLS = [
  '/AbxLinks.json',
  '/Antimicrobial CDSS Frequently Asked Questions.pdf',
  '/AppInstall.html',
  '/AppInstall.jpg',
  '/CDSSLogo.png',
  '/CDSSLogoApp.png',
  '/CDSSLogoLarge.png',
  '/CDSSLogoTab.png',
  '/CDSSVALogo.png',
  '/Disclaimer.html',
  '/Resources.html',
  '/VASeal.jpg',
  '/index.html',
  '/manifest.webmanifest',
  '/service-worker.js',
  
  '/stations/001-TestStation/TestStationCDSS.html',

  '/stations/437-Fargo/FargoCDSS.html',
  '/stations/437-Fargo/FargoItemLinks.json',

  '/stations/438-SiouxFalls/SiouxFallsCDSS.html',

  '/stations/442-Cheyenne/CheyenneCDSS.html',

  '/stations/568-BlackHills/BlackHillsCDSS.html',

  '/stations/618-Minneapolis/MinneapolisCDSS.html',

  '/stations/636-Omaha/OmahaCDSS.html',

  '/stations/636A6-DesMoines/DesMoinesCDSS.html',

  '/stations/656-StCloud/StCloudCDSS.html',

  '/Fonts/PTSerif-Bold.eot',
  '/Fonts/PTSerif-Bold.svg',
  '/Fonts/PTSerif-Bold.ttf',
  '/Fonts/PTSerif-Bold.woff',
  '/Fonts/PTSerif-Bold.woff2',

  '/Fonts/PTSerif-BoldItalic.eot',
  '/Fonts/PTSerif-BoldItalic.svg',
  '/Fonts/PTSerif-BoldItalic.ttf',
  '/Fonts/PTSerif-BoldItalic.woff',
  '/Fonts/PTSerif-BoldItalic.woff2',

  '/Fonts/PTSerif-Italic.eot',
  '/Fonts/PTSerif-Italic.svg',
  '/Fonts/PTSerif-Italic.ttf',
  '/Fonts/PTSerif-Italic.woff',
  '/Fonts/PTSerif-Italic.woff2',

  '/Fonts/PTSerif-Regular.eot',
  '/Fonts/PTSerif-Regular.svg',
  '/Fonts/PTSerif-Regular.ttf',
  '/Fonts/PTSerif-Regular.woff',
  '/Fonts/PTSerif-Regular.woff2',
];

self.addEventListener('install', function (e) {
  console.log('Installing service worker: ' + CACHE_NAME);

  e.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      console.log('Caching files: ' + URLS.join(', '));
      return cache.addAll(URLS);
    }).then(function () {
      // Activate updated service worker without waiting for all tabs to close.
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (e) {
  console.log('Activating service worker: ' + CACHE_NAME);

  e.waitUntil(
    caches.keys().then(function (keyList) {
      return Promise.all(keyList.map(function (key) {
        if (key !== CACHE_NAME) {
          console.log('Deleting old cache: ' + key);
          return caches.delete(key);
        }
      }));
    }).then(function () {
      console.log('Service worker activated.');
      return self.clients.claim();
    })
  );
});

self.addEventListener('fetch', function (e) {
  console.log('Fetch request: ' + e.request.url);

  if (!e.request.url.startsWith(self.location.origin)) {
    console.log('Skipping caching for third-party resource: ' + e.request.url);
    return;
  }

  const requestUrl = new URL(e.request.url);
  const isCmsContentRequest =
    e.request.method === 'GET' &&
    (requestUrl.pathname.endsWith('.json') || requestUrl.pathname.endsWith('.txml'));

  const isHtmlRequest =
    e.request.method === 'GET' &&
    (e.request.mode === 'navigate' || requestUrl.pathname.endsWith('.html'));

  // CMS-managed content should prefer the network so saved edits appear quickly.
  if (isCmsContentRequest) {
    // Force revalidation/bypass of HTTP disk cache for CMS content.
    const networkRequest = new Request(e.request, { cache: 'no-store' });

    e.respondWith(
      fetch(networkRequest).then(function (networkResponse) {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(e.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(function () {
        return caches.match(e.request);
      })
    );
    return;
  }

  // Prefer network for HTML shell/navigation to avoid stale first-load pages.
  if (isHtmlRequest) {
    e.respondWith(
      fetch(e.request).then(function (networkResponse) {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(e.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(function () {
        return caches.match(e.request);
      })
    );
    return;
  }

  e.respondWith(
    caches.match(e.request).then(function (response) {
      // Reload assets if version has changed.
      const fetchRequest = e.request.clone();

      return (
        response || fetch(fetchRequest).then(function (networkResponse) {
          // Check if we received a valid response
          if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
            return networkResponse;
          }

          const responseToCache = networkResponse.clone();

          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(e.request, responseToCache);
          });

          return networkResponse;
        }).catch(function (error) {
          console.error('Fetch error: ' + error);
        })
      );
    })
  );
});
