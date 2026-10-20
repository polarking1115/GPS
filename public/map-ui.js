/* Map editing and consent-based GPS stay separate from participation/authentication. */
window.MapUI=(()=>{
 const FM=()=>window.FestivalMap;
 let viewer=null,editor=null,edit=null,watch=null,fence=null,eventId=null,currentRoute=null,gpsMessage='',pendingCorner=null,pendingNode=null,selectedNode=null;
 const defaultMap=()=>({center:[34.7523,127.7468],zoom:17,basemap:'osm'});
 function theme(){return S.mode==='admin'?S.admin.event.settings:S.data.theme}
 function mapState(){return {...defaultMap(),...(theme().outdoor_map||{})}}
 function statusText(){return watch!==null?(gpsMessage||'GPS 수신 대기 · 위치는 기기 안에서만 사용합니다.'):'GPS는 꺼져 있습니다. 직접 출발지를 선택할 수도 있습니다.'}
 function controls(){return `<div class="gps-status" id="gps-status" role="status">${esc(t(statusText()))}</div><div class="map-controls">${button(watch===null?'GPS 안내 시작':'GPS 안내 중지',watch===null?'map-gps-start':'map-gps-stop')}${button('야외 지도','map-manual-outdoor')}${button('자동 전환 안내','map-help')}</div>`}
 function outdoor(){const nodes=S.data.theme.outdoor_nodes||[],config={...mapState(),basemap:S.mapBase||mapState().basemap};return `<div class="card"><h3>${esc(t("야외 길찾기"))}</h3><label for="outdoor-basemap">${esc(t("배경지도"))}</label><select id="outdoor-basemap">${options([['osm','일반 지도 · OpenStreetMap'],['satellite','위성·항공사진 · Esri'],['none','배경 없음 · 배치도·통로만']],config.basemap)}</select><div class="map-status" id="outdoor-map-status" role="status"></div><div class="geo-map" id="outdoor-canvas" aria-label="${esc(t("야외 지도"))}"></div>${select('route-from','출발지',nodes.map(n=>[n.id,n.label||n.name]),'')}${select('route-to','도착지',nodes.map(n=>[n.id,n.label||n.name]),'')}<div class="actions">${button('경로 계산','route','primary',nodes.length?'':'disabled')}${button('GPS 위치 확인','gps')}</div><div id="route-result"></div>${!nodes.length?note('운영자가 보행 지점·통로를 등록하면 경로 계산을 이용할 수 있습니다.'):''}${note('지도 배경은 외부 제공자에서 불러옵니다. GPS 좌표는 앱 서버에 전송하지 않습니다. 행사 내부 경로는 등록된 통로만 이용하며 현장 통제를 우선하세요.')}</div>`}
 function unmount(){viewer?.destroy();viewer=null;if(S.page!=='map'||S.mode!=='participant')stopGPS(false)}
 function mount(){if(S.mode!=='participant'||S.page!=='map')return;
  if(eventId!==S.event){stopGPS(false);eventId=S.event;fence=new (FM().Geofence)(S.data.theme.building_maps||[]);currentRoute=null;S.gps=null}
  if(!fence)fence=new (FM().Geofence)(S.data.theme.building_maps||[]);fence.setBuildings(S.data.theme.building_maps||[]);
  const target=$('#outdoor-canvas');if(!target)return;
  if(!window.L){target.innerHTML=empty('지도 구성요소를 불러오지 못했습니다. 연결 후 새로고침해 주세요.');return}
  const config=mapState();if(S.mapBase)config.basemap=S.mapBase;
  viewer=new (FM().MapView)(target,config,{onStatus:message=>{const el=$('#outdoor-map-status');if(el)el.textContent=t(message)}});
  const nodes=S.data.theme.outdoor_nodes||[],edges=S.data.theme.outdoor_edges||[];viewer.drawGraph(nodes.map(n=>({...n,name:n.label||n.name})),edges);viewer.drawBuildings((S.data.theme.building_maps||[]).map(b=>({...b,name:b.label||b.name})));viewer.drawBooths(boothList(),b=>{S.booth=b;navigate('booth')});
  if(S.gps)viewer.showPosition(S.gps);if(currentRoute)viewer.drawRoute(nodes,currentRoute);
 }
 function route(nodes,r){currentRoute=r;viewer?.drawRoute(nodes,r)}
 function stopGPS(show=true){if(watch!==null)navigator.geolocation?.clearWatch(watch);watch=null;fence?.signalLost();gpsMessage='';if(show)toast('GPS 안내를 중지했습니다.');const status=$('#gps-status');if(status)status.textContent=t(statusText())}
 function fix(position){const c=position.coords,p={lat:c.latitude,lng:c.longitude,accuracy:c.accuracy,timestamp:position.timestamp};S.gps=p;viewer?.showPosition(p);gpsMessage=t('위치 정확도 약 {meters}m · {time} 수신',{meters:Math.round(p.accuracy),time:new Date(p.timestamp).toLocaleTimeString(S.lang==='en'?'en-US':'ko-KR')});
  const el=$('#gps-status');if(el)el.textContent=t(gpsMessage);const nodes=S.data.theme.outdoor_nodes||[];
  if(nodes.length){const nearest=[...nodes].sort((a,b)=>FM().distance(a,p)-FM().distance(b,p))[0];if(FM().distance(nearest,p)<=200&&$('#f-route-from'))$('#f-route-from').value=nearest.id}
  if(watch===null)return;
  const transition=fence?.update(p);if(transition){S.mapBuilding=transition.mode==='indoor'?transition.building:'outdoor';S.mapZoom=1;publicRender().then(()=>toast(transition.mode==='indoor'?t('{building} 통합 평면도로 전환했습니다.',{building:(S.data.theme.building_maps||[]).find(b=>b.name===transition.building)?.label||transition.building}):'건물 밖 위치를 확인해 야외 지도로 전환했습니다.'))}
 }
 function lost(error){fence?.signalLost();gpsMessage=error?.code===1?'위치 권한이 허용되지 않았습니다. 출발지를 직접 선택해 주세요.':'GPS 수신이 불안정합니다. 실내 화면을 유지하며 직접 지도를 선택할 수 있습니다.';const status=$('#gps-status');if(status)status.textContent=t(gpsMessage);if(error?.code===1){stopGPS(false);toast(gpsMessage||'위치 권한을 확인하세요.')}}
 function manual(name){fence?.manual(name);S.mapBuilding=name||'outdoor';currentRoute=null}
 function destroyEditor(){editor?.destroy();editor=null;edit=null;pendingCorner=null;pendingNode=null;selectedNode=null}
 function readFence(){if(!edit||!$('#editor-building'))return;const b=edit.maps.find(b=>b.name===edit.selectedBuilding);if(!b||!b.geofence)return;const f=b.geofence;for(const k of ['entry_radius','exit_buffer','dwell_ms','max_accuracy']){const el=$('#geo-'+k);if(el)f[k]=Number(el.value)}f.enabled=$('#geo-enabled')?.checked||false}
 function fencePanel(){const b=edit.maps.find(b=>b.name===edit.selectedBuilding);if(!b)return note('실내 통합 평면도를 먼저 등록하면 건물 진입 범위를 지정할 수 있습니다.');const f=b.geofence||{};return `<h3>실내 전환 · ${esc(b.name)}</h3>${f.entrance?note('입구 '+f.entrance.map(x=>Number(x).toFixed(6)).join(', ')):note('지도에서 입구와 건물 범위를 지정하세요.')}${f.bounds?note('건물 범위 등록됨'):''}<label class="check"><input id="geo-enabled" type="checkbox" ${f.enabled?'checked':''}>GPS 자동 전환 사용</label>${[['entry_radius','입구 반경(m)',f.entry_radius||20],['exit_buffer','건물 밖 복귀 여유 거리(m)',f.exit_buffer||40],['dwell_ms','진입·이탈 확인 시간(ms)',f.dwell_ms||10000],['max_accuracy','허용 위치 오차(m)',f.max_accuracy||35]].map(([k,l,v])=>`<label for="geo-${k}">${l}</label><input id="geo-${k}" type="number" value="${v}">`).join('')}${note('여러 위치 표본과 정확도를 확인합니다. 실내에서 GPS가 끊겨도 유지하고, 건물 경계 밖에서 안정적으로 확인될 때만 복귀합니다.')}`}
 function refreshFencePanel(){const el=$('#editor-fence');if(el)el.innerHTML=fencePanel()}
 function drawEditor(){if(!editor)return;editor.drawGraph(edit.nodes,edit.edges,{editable:true,onNode:node=>{
   selectedNode=node.id;
   if(edit.mode==='connect'){if(!pendingNode){pendingNode=node.id;toast('두 번째 보행 지점을 선택하세요.');return}if(pendingNode!==node.id&&!edit.edges.some(e=>[e.from,e.to].includes(pendingNode)&&[e.from,e.to].includes(node.id)))edit.edges.push({from:pendingNode,to:node.id,closed:false});pendingNode=null;drawEditor();return}
   $('#editor-selection').textContent='선택 지점: '+node.name+' · 드래그로 위치를 바꿀 수 있습니다.';
  },onEdge:edge=>{if(confirm((edge.closed?'다시 통행 가능한 구간으로':'폐쇄 구간으로')+' 변경할까요?')){edge.closed=!edge.closed;drawEditor()}}});editor.drawBuildings(edit.maps);editor.drawBooths(S.admin.booths,()=>{});
  $('#editor-count').textContent=`보행 지점 ${edit.nodes.length}개 · 통로 ${edit.edges.length}개 · 폐쇄 ${edit.edges.filter(e=>e.closed).length}개`;
 }
 function editorMode(mode){readFence();edit.mode=mode;pendingCorner=null;pendingNode=null;$$('[data-mapmode]').forEach(b=>b.classList.toggle('active',b.dataset.mapmode===mode));$('#editor-instruction').textContent={view:'지도를 이동·확대합니다. 지점을 드래그하거나 통로를 눌러 폐쇄 여부를 변경할 수 있습니다.',node:'지도에서 보행 지점 위치를 클릭하세요.',connect:'연결할 보행 지점 두 개를 차례로 선택하세요.',entrance:'선택한 건물의 입구 위치를 클릭하세요.',building:'건물 외곽을 감싸는 두 모서리를 차례로 클릭하세요.',overlay:'배치도를 덮을 영역의 두 모서리를 차례로 클릭하세요.'}[mode]}
 function normalizeBounds(a,b){return [[Math.min(a.lat,b.lat),Math.min(a.lng,b.lng)],[Math.max(a.lat,b.lat),Math.max(a.lng,b.lng)]]}
 function clickEditor(event){const p=event.latlng;
  if(edit.mode==='node'){const name=prompt('보행 지점 이름');if(!name?.trim())return;edit.nodes.push({id:crypto.randomUUID(),name:name.trim().slice(0,120),lat:p.lat,lng:p.lng});drawEditor();return}
  if(edit.mode==='entrance'){const b=edit.maps.find(b=>b.name===edit.selectedBuilding);if(!b)return toast('건물을 먼저 선택하세요.');b.geofence={enabled:false,entry_radius:20,exit_buffer:40,dwell_ms:10000,max_accuracy:35,...(b.geofence||{}),entrance:[p.lat,p.lng]};refreshFencePanel();if(b.geofence.bounds)drawEditor();toast('입구를 지정했습니다. 건물 범위도 지정하세요.');return}
  if(edit.mode==='building'||edit.mode==='overlay'){if(!pendingCorner){pendingCorner=p;toast('반대편 모서리를 클릭하세요.');return}const bounds=normalizeBounds(pendingCorner,p);pendingCorner=null;if(bounds[0][0]===bounds[1][0]||bounds[0][1]===bounds[1][1])return toast('면적이 있는 범위를 지정하세요.');
   if(edit.mode==='overlay'){if(!edit.config.overlay)return toast('배치도 이미지를 먼저 선택하세요.');edit.config.overlay.bounds=bounds;editor.setOverlay(edit.config.overlay,true,c=>{edit.config.overlay=c})}
   else{const b=edit.maps.find(b=>b.name===edit.selectedBuilding);if(!b)return toast('건물을 선택하세요.');b.geofence={enabled:false,entry_radius:20,exit_buffer:40,dwell_ms:10000,max_accuracy:35,...(b.geofence||{}),bounds};refreshFencePanel();drawEditor()}
  }
 }
 function showEditor(){const settings=S.admin.event.settings;edit={config:structuredClone(settings.outdoor_map||defaultMap()),nodes:structuredClone(settings.outdoor_nodes||[]),edges:structuredClone(settings.outdoor_edges||[]),maps:structuredClone(settings.building_maps||[]),mode:'view',selectedBuilding:(settings.building_maps||[])[0]?.name||''};
  modal('야외 지도·배치도·보행로 편집',`<div class="geo-editor-grid"><section><div class="map-controls"><select id="editor-basemap" aria-label="${esc(t("배경지도"))}">${options([['osm','일반 지도 · OpenStreetMap'],['satellite','위성·항공사진 · Esri'],['none','배경 없음']],edit.config.basemap||'osm')}</select>${button('현재 중심·확대 수준 저장','map-view-save')}</div><div class="map-status" id="editor-map-status" role="status"></div><div class="geo-map editor-map" id="editor-map"></div><div class="editor-toolbar">${[['view','이동'],['node','보행 지점'],['connect','통로 연결'],['entrance','건물 입구'],['building','건물 범위'],['overlay','배치도 범위']].map(([m,l])=>button(l,'map-mode:'+m,m==='view'?'active':'',`data-mapmode="${m}"`)).join('')}</div><p class="geometry-help" id="editor-instruction">지도를 이동·확대하고 지점을 드래그할 수 있습니다. 통로를 클릭하면 폐쇄 여부를 변경합니다.</p><p class="muted" id="editor-count"></p><p class="muted" id="editor-selection"></p>${button('선택 지점 삭제','map-node-delete','text-btn')}<div class="notice info">아직 공개에 적용하지 않은 편집 내용입니다. 저장 전까지 참가자 화면은 바뀌지 않습니다.</div></section><section><div class="card"><h3>배치도 겹치기</h3><label for="overlay-file">배치도 이미지 · PNG/JPEG/WebP</label><input id="overlay-file" type="file" accept="image/png,image/jpeg,image/webp"><div class="overlay-controls"><div><label for="overlay-opacity">투명도</label><input id="overlay-opacity" type="range" min="0" max="1" step=".05" value="${edit.config.overlay?.opacity??.65}"></div><div><label for="overlay-rotation">회전(도)</label><input id="overlay-rotation" type="number" min="-180" max="180" value="${edit.config.overlay?.rotation||0}"></div></div>${button('배치도 제거','map-overlay-remove','text-btn')}${note('모서리 핸들로 크기, 가운데 핸들로 위치를 조절합니다. 투명 배경 이미지를 권장하며 회전은 중심 기준입니다.')}</div><div class="card"><label for="editor-building">실내 통합 평면도 건물</label><select id="editor-building">${options(edit.maps.map(b=>[b.name,b.name]),edit.selectedBuilding)}</select><div id="editor-fence">${fencePanel()}</div></div></section></div><div class="form-actions">${button('변경 취소','close')}${button('미리보기·검토 후 공개 적용','map-editor-save','primary')}</div>`);
  $('.modal-body').classList.add('map-dialog');editor=new (FM().MapView)($('#editor-map'),edit.config,{editing:true,onStatus:m=>{const el=$('#editor-map-status');if(el)el.textContent=m},onOverlayChange:c=>{edit.config.overlay=c},onGraphChange:drawEditor});editor.map.on('click',clickEditor);drawEditor();
 }
 async function action(a){
  if(a==='outdoor-editor'){showEditor();return true}
  if(a==='map-help'){modal('GPS·지도 안내',`<p>${esc(t("GPS 안내를 시작하면 위치 권한을 요청합니다. 등록된 입구 근처에서 정확한 위치가 일정 시간 확인되면 실내 통합 평면도를 엽니다."))}</p><p>${esc(t("실내에서 신호를 잃어도 유지하며, 건물 경계에서 충분히 벗어난 위치가 연속으로 확인돼야 야외 지도로 돌아갑니다. 실내 층은 추적하지 않습니다."))}</p>${note('직접 지도를 바꾸면 1분 동안 자동 전환을 유예합니다. 위치는 서버로 전송하지 않습니다. 배경지도는 외부 제공자에서 받아오며 브라우저가 외부 서버에 접속합니다.')}`);return true}
  if(a==='map-gps-stop'){stopGPS();await publicRender();return true}
  if(a==='map-gps-start'||a==='gps'){if(!navigator.geolocation)throw Error('위치 기능을 사용할 수 없습니다. 출발지를 직접 선택해 주세요.');if(a==='gps'){navigator.geolocation.getCurrentPosition(fix,lost,{enableHighAccuracy:true,timeout:10000,maximumAge:0});return true}if(watch!==null)return true;gpsMessage='GPS 수신 대기';watch=navigator.geolocation.watchPosition(fix,lost,{enableHighAccuracy:true,timeout:15000,maximumAge:0});await publicRender();return true}
  if(a==='map-manual-outdoor'){manual(null);await publicRender();return true}
  if(a.startsWith('map-mode:')){editorMode(a.slice(9));return true}
  if(a==='map-view-save'){const s=editor.snapshot();edit.config.center=s.center;edit.config.zoom=s.zoom;toast('공개 적용 시 이 중심과 확대 수준으로 시작합니다.');return true}
  if(a==='map-node-delete'){if(!selectedNode)throw Error('지점을 먼저 선택하세요.');edit.nodes=edit.nodes.filter(n=>n.id!==selectedNode);edit.edges=edit.edges.filter(e=>e.from!==selectedNode&&e.to!==selectedNode);selectedNode=null;drawEditor();return true}
  if(a==='map-overlay-remove'){delete edit.config.overlay;editor.setOverlay(null);return true}
  if(a==='map-editor-save'){readFence();for(const b of edit.maps)if(b.geofence&&(!b.geofence.entrance||!b.geofence.bounds))throw Error(b.name+'의 입구와 건물 범위를 모두 지정해 주세요.');if(!confirm('지도·통로·실내 전환 설정을 참가자 화면에 적용할까요?'))return true;await api(ep('settings'),'POST',{outdoor_map:edit.config,outdoor:{nodes:edit.nodes,edges:edit.edges},maps:edit.maps});closeModal();await refreshAdmin();await adminRender();toast('지도 설정을 적용했습니다.');return true}
  return false;
 }
 document.addEventListener('change',async e=>{try{
  if(e.target.id==='outdoor-basemap'){S.mapBase=e.target.value;viewer?.setBase(e.target.value)}
  if(e.target.id==='building-filter')manual(e.target.value==='outdoor'?null:e.target.value);
  if(!edit)return;
  if(e.target.id==='editor-building'){readFence();edit.selectedBuilding=e.target.value;refreshFencePanel()}
  if(e.target.id==='editor-basemap'){edit.config.basemap=e.target.value;editor.setBase(e.target.value)}
  if(e.target.id==='overlay-file'){const result=await upload(e.target.files[0]);const bounds=editor.map.getBounds().pad(-.2);edit.config.overlay={image:result.url,bounds:[[bounds.getSouth(),bounds.getWest()],[bounds.getNorth(),bounds.getEast()]],opacity:Number($('#overlay-opacity').value),rotation:Number($('#overlay-rotation').value)};editor.setOverlay(edit.config.overlay,true,c=>{edit.config.overlay=c});toast('배치도를 올렸습니다. 이동·크기·회전을 조정한 뒤 공개 적용하세요.')}
 }catch(err){toast(err.message)}});
 document.addEventListener('input',e=>{if(!edit||!edit.config.overlay)return;if(['overlay-opacity','overlay-rotation'].includes(e.target.id)){const opacity=Number($('#overlay-opacity').value),rotation=Number($('#overlay-rotation').value);if(!Number.isFinite(rotation)||Math.abs(rotation)>180)return;edit.config.overlay.opacity=opacity;edit.config.overlay.rotation=rotation;editor.setOverlay(edit.config.overlay,true,c=>{edit.config.overlay=c})}});
 window.addEventListener('pagehide',()=>stopGPS(false));
 document.addEventListener('visibilitychange',()=>{if(document.hidden)fence?.signalLost()});
 return {controls,outdoor,mount,unmount,route,manual,action,close:destroyEditor,stopGPS};
})();
