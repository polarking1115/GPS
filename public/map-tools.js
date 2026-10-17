/* Geometry and geofence state are testable without a browser or external tile service. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.FestivalMap=api})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const radians=d=>d*Math.PI/180;
function distance(a,b){const x=Math.sin(radians(b.lat-a.lat)/2)**2+Math.cos(radians(a.lat))*Math.cos(radians(b.lat))*Math.sin(radians(b.lng-a.lng)/2)**2;return 12742000*Math.atan2(Math.sqrt(Math.min(1,x)),Math.sqrt(Math.max(0,1-x)))}
function coordinate(p){return !!p&&Number.isFinite(p.lat)&&Number.isFinite(p.lng)&&Math.abs(p.lat)<=85&&Math.abs(p.lng)<=180}
function inside(p,bounds,buffer=0){if(!coordinate(p)||!bounds)return false;const lat=buffer/111320,lng=buffer/(111320*Math.max(.01,Math.cos(radians(p.lat))));return p.lat>=bounds[0][0]-lat&&p.lat<=bounds[1][0]+lat&&p.lng>=bounds[0][1]-lng&&p.lng<=bounds[1][1]+lng}
function fenceAllowed(building,p){const f=building?.geofence;return !!f?.enabled&&coordinate(p)&&Number.isFinite(p.accuracy)&&p.accuracy>0&&p.accuracy<=f.max_accuracy}
class Geofence {
 constructor(buildings=[]){this.buildings=buildings;this.active=null;this.enter=null;this.exit=null;this.lastTimestamp=0;this.manualUntil=0}
 setBuildings(buildings){this.buildings=buildings;if(this.active&&!buildings.some(b=>b.name===this.active&&b.geofence?.enabled))this.active=null}
 manual(name,now=Date.now()){this.active=name&&this.buildings.some(b=>b.name===name)?name:null;this.enter=null;this.exit=null;this.manualUntil=now+60000}
 update(p,now=Date.now()){
  if(!coordinate(p)||!Number.isFinite(p.timestamp)||p.timestamp<=this.lastTimestamp||now-p.timestamp>30000||p.timestamp>now+5000)return null;
  this.lastTimestamp=p.timestamp;
  if(now<this.manualUntil)return null;
  if(this.active){const b=this.buildings.find(b=>b.name===this.active);if(!b?.geofence?.enabled||!fenceAllowed(b,p)){this.exit=null;return null}const f=b.geofence;
   if(inside(p,f.bounds,f.exit_buffer)){this.exit=null;return null}
   if(!this.exit)this.exit={since:now,count:0};this.exit.count++;
   if(this.exit.count>=2&&now-this.exit.since>=f.dwell_ms){const old=this.active;this.active=null;this.exit=null;this.enter=null;return {mode:'outdoor',previous:old}}
   return null;
  }
  const candidates=this.buildings.filter(b=>fenceAllowed(b,p)&&distance(p,{lat:b.geofence.entrance[0],lng:b.geofence.entrance[1]})<=b.geofence.entry_radius);
  if(!candidates.length){this.enter=null;return null}
  candidates.sort((a,b)=>distance(p,{lat:a.geofence.entrance[0],lng:a.geofence.entrance[1]})-distance(p,{lat:b.geofence.entrance[0],lng:b.geofence.entrance[1]}));
  if(candidates.length>1){const a=candidates[0].geofence.entrance,b=candidates[1].geofence.entrance;const delta=Math.abs(distance(p,{lat:a[0],lng:a[1]})-distance(p,{lat:b[0],lng:b[1]}));if(delta<p.accuracy){this.enter=null;return null}}
  const target=candidates[0];if(this.enter?.name!==target.name)this.enter={name:target.name,since:now,count:0};this.enter.count++;
  if(this.enter.count>=2&&now-this.enter.since>=target.geofence.dwell_ms){this.active=target.name;this.enter=null;return {mode:'indoor',building:target.name}}
  return null;
 }
 signalLost(){this.enter=null;this.exit=null} // Keep indoor mode on loss of signal.
}
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pinIcon=(text,cls='')=>L.divIcon({className:'geo-pin '+cls,html:'<span>'+escape(text)+'</span>',iconSize:null,iconAnchor:[15,15]});
class MapView {
 constructor(element,config={},options={}){
  this.options=options;this.config=config;this.handles=[];this.layers=[];this.tileFailures=0;
  this.map=L.map(element,{zoomControl:true,scrollWheelZoom:false,attributionControl:true,zoomAnimation:false,fadeAnimation:false,markerZoomAnimation:false}).setView(config.center||[34.7523,127.7468],config.zoom||17);
  this.map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
  this.setBase(config.basemap||'osm');if(config.overlay)this.setOverlay(config.overlay,!!options.editing,options.onOverlayChange);
  this.resize=new ResizeObserver(()=>this.map?.invalidateSize({pan:false}));this.resize.observe(element);setTimeout(()=>this.map?.invalidateSize(),0);
 }
 setBase(kind){if(this.tiles)this.map.removeLayer(this.tiles);this.tileFailures=0;this.config.basemap=kind;if(kind==='none'){this.status('배경지도 없음 · 등록된 통로와 배치도는 표시됩니다.');return}
  const source=kind==='satellite'?{url:'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',attribution:'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'}:{url:'https://tile.openstreetmap.org/{z}/{x}/{y}.png',attribution:'© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'};
  this.tiles=L.tileLayer(source.url,{attribution:source.attribution,maxZoom:20,maxNativeZoom:kind==='satellite'?19:19,referrerPolicy:'strict-origin-when-cross-origin'}).addTo(this.map);
  this.status('배경지도 연결 중…');this.tiles.on('tileerror',()=>{this.tileFailures++;this.status('배경지도를 불러오지 못했습니다. 등록된 배치도·보행로는 계속 사용할 수 있습니다.')});this.tiles.on('load',()=>{if(!this.tileFailures)this.status(kind==='satellite'?'위성·항공사진 · 촬영 시점과 현장 상황은 다를 수 있습니다.':'일반 지도 · 행사장 내부 통행은 등록된 보행로 기준입니다.')});
 }
 status(msg){this.options.onStatus?.(msg)}
 setOverlay(config,editing=false,onChange){
  if(this.overlay)this.map.removeLayer(this.overlay);for(const h of this.handles)this.map.removeLayer(h);this.handles=[];this.overlay=null;
  if(!config)return;this.config.overlay=structuredClone(config);const bounds=config.bounds;this.overlay=L.imageOverlay(config.image,bounds,{opacity:config.opacity??.65,interactive:false,zIndex:250}).addTo(this.map);
  const rotate=()=>{const el=this.overlay?.getElement();if(el){el.style.rotate=(config.rotation||0)+'deg';el.style.transformOrigin='center'}};this.overlay.on('load',rotate);rotate();
  if(editing){const center=L.latLngBounds(bounds).getCenter();const handles=[{label:'남서',point:bounds[0],corner:0},{label:'북동',point:bounds[1],corner:1},{label:'이동',point:center,corner:-1}];
   for(const h of handles){const marker=L.marker(h.point,{draggable:true,icon:pinIcon(h.label,'overlay-handle')}).addTo(this.map);marker.on('dragend',()=>{const p=marker.getLatLng();let next=structuredClone(config);if(h.corner===-1){const delta=[p.lat-center.lat,p.lng-center.lng];next.bounds=next.bounds.map(b=>[b[0]+delta[0],b[1]+delta[1]])}else next.bounds[h.corner]=[p.lat,p.lng];if(next.bounds[0][0]>=next.bounds[1][0]||next.bounds[0][1]>=next.bounds[1][1]){this.setOverlay(config,true,onChange);return}this.setOverlay(next,true,onChange);onChange?.(next)});this.handles.push(marker)}
  }
 }
 clearFeatures(){for(const l of this.layers)this.map.removeLayer(l);this.layers=[]}
 drawGraph(nodes,edges,{editable=false,onNode,onEdge}={}){
  this.clearFeatures();const byId=new Map(nodes.map(n=>[n.id,n]));
  for(const edge of edges){const a=byId.get(edge.from),b=byId.get(edge.to);if(!a||!b)continue;const line=L.polyline([[a.lat,a.lng],[b.lat,b.lng]],{color:edge.closed?'#d6536b':'#8daec8',weight:5,dashArray:edge.closed?'6 7':null}).addTo(this.map);if(editable&&onEdge)line.on('click',event=>{L.DomEvent.stopPropagation(event.originalEvent);onEdge(edge)});this.layers.push(line)}
  for(const n of nodes){const marker=L.marker([n.lat,n.lng],{icon:pinIcon(n.name),draggable:editable}).addTo(this.map);if(onNode)marker.on('click',event=>{L.DomEvent.stopPropagation(event.originalEvent);onNode(n)});if(editable)marker.on('dragend',()=>{const p=marker.getLatLng();n.lat=p.lat;n.lng=p.lng;this.options.onGraphChange?.()});marker.bindTooltip(escape(n.name));this.layers.push(marker)}
 }
 drawBuildings(buildings){for(const b of buildings){const f=b.geofence;if(!f?.bounds||!f?.entrance)continue;this.layers.push(L.rectangle(f.bounds,{color:'#9475c5',weight:1,fillOpacity:.04,interactive:false}).addTo(this.map));this.layers.push(L.circle(f.entrance,{radius:f.entry_radius,color:'#9475c5',weight:1,fillOpacity:.08,interactive:false}).addTo(this.map))}}
 drawBooths(booths,onSelect){for(const b of booths){if(b.building||!coordinate(b))continue;const marker=L.marker([b.lat,b.lng],{icon:pinIcon(b.code||b.name,'booth-pin')}).addTo(this.map);marker.on('click',()=>onSelect?.(b));marker.bindTooltip(escape(b.name));this.layers.push(marker)}}
 drawRoute(nodes,result){if(this.route)this.map.removeLayer(this.route);const byId=new Map(nodes.map(n=>[n.id,n]));const coords=result.path.map(id=>[byId.get(id).lat,byId.get(id).lng]);this.route=L.polyline(coords,{color:'#075de5',weight:6,opacity:.9}).addTo(this.map);if(coords.length>1)this.map.fitBounds(this.route.getBounds(),{padding:[35,35],maxZoom:19});else this.map.setView(coords[0],18)}
 showPosition(p){if(this.location)this.map.removeLayer(this.location);if(this.accuracy)this.map.removeLayer(this.accuracy);this.location=L.circleMarker([p.lat,p.lng],{radius:7,color:'white',weight:3,fillColor:'#1767e8',fillOpacity:1}).addTo(this.map);this.accuracy=L.circle([p.lat,p.lng],{radius:Math.min(p.accuracy||0,500),weight:1,color:'#1767e8',fillOpacity:.07,interactive:false}).addTo(this.map)}
 snapshot(){return {...this.config,center:[this.map.getCenter().lat,this.map.getCenter().lng],zoom:this.map.getZoom()}}
 destroy(){this.resize?.disconnect();this.map?.stop();this.map?.remove();this.map=null}
}
return {distance,inside,coordinate,Geofence,MapView};
});
