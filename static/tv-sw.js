// Service worker da TV — a copia que garante que ela sempre volta.
const CACHE = 'ms-tv-v1';
const PAGINA = 'tv.html';

self.addEventListener('install', (e) => {
  // Assume o controle sem esperar a proxima visita: a TV so navega uma vez.
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.add(PAGINA)).catch(() => {}));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (e) => {
  // Só a navegação. Tudo o mais — inclusive a busca de 60s — vai direto para a
  // rede, sem passar por cache nenhum.
  if (e.request.mode !== 'navigate') return;
  e.respondWith(
    fetch(e.request)
      .then((r) => {
        if (r && r.ok) {
          const copia = r.clone();
          caches.open(CACHE).then((c) => c.put(PAGINA, copia)).catch(() => {});
        }
        // 502/503 do Railway durante o deploy é uma resposta VÁLIDA em HTTP e
        // não cai no catch — mas para a TV é o mesmo que estar fora do ar.
        if (r && !r.ok) throw new Error('http ' + r.status);
        return r;
      })
      .catch(() => caches.open(CACHE)
        .then((c) => c.match(PAGINA))
        .then((r) => r || Response.error()))
  );
});
