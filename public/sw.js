/* Public information only. Participant/admin APIs, contact and report data are never cached. */
const CACHE='festival-public-v3';
const SHELL=['/','/styles.css','/app.js','/map-tools.js','/map-ui.js','/vendor/leaflet/leaflet.js','/vendor/leaflet/leaflet.css','/assets/youth-hero.png','/assets/favicon.svg'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)));self.skipWaiting()});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(names=>Promise.all(names.filter(n=>n!==CACHE).map(n=>caches.delete(n)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',event=>{const u=new URL(event.request.url);if(u.origin!==self.location.origin||event.request.method!=='GET')return;
const isPublic=u.pathname==='/api/events'||/^\/api\/events\/[\w-]+$/.test(u.pathname);const isAsset=u.pathname.startsWith('/assets/')||u.pathname.startsWith('/vendor/')||['/styles.css','/app.js','/map-tools.js','/map-ui.js'].includes(u.pathname);const participantNavigation=event.request.mode==='navigate'&&(u.pathname==='/'||u.pathname.startsWith('/e/'));
if(!isPublic&&!isAsset&&!participantNavigation)return;
event.respondWith((async()=>{try{const response=await fetch(event.request);if(response.ok&&(!isPublic||(await response.clone().json()).event?.status!=='draft')){const cache=await caches.open(CACHE);await cache.put(event.request,response.clone())}return response}catch(err){const cache=await caches.open(CACHE);const stored=await cache.match(event.request);if(stored){if(isPublic){const headers=new Headers(stored.headers);headers.set('X-Festival-Offline','1');return new Response(await stored.arrayBuffer(),{status:200,headers})}return stored}if(participantNavigation)return (await cache.match('/'));return new Response('연결이 필요합니다.',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}})}})());
});
