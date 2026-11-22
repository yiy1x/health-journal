'use strict';
const CACHE = 'health-journal-phone-1.2.1-release2';
const ASSETS = ['./', './index.html', './phone.css', './phone.js', './core.js', './db.js', './manifest.webmanifest', './icon.svg', './catalog.json', './LICENSE.txt'];
const approved = new Set(ASSETS.map(path => new URL(path, self.registration.scope).href));
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('health-journal-phone-') && key !== CACHE).map(key => caches.delete(key))))));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  url.hash = '';
  if (event.request.method !== 'GET' || !approved.has(url.href)) return;
  event.respondWith(caches.open(CACHE).then(async cache => (await cache.match(url.href)) || fetch(event.request)));
});
