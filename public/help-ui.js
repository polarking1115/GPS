/* Guided tours point at live controls, never click or submit them. No field values are read. */
window.HelpUI=(()=>{
 let tour=null,scheduled=false;
 const state=()=>{try{return typeof S==='object'?S:{}}catch{return {}}};
 const en=()=>state().lang==='en';
 const tr=(ko,english)=>en()?english:ko;
 const visible=el=>!!el&&el.isConnected&&!el.closest('[hidden]')&&el.getClientRects().length>0&&getComputedStyle(el).visibility!=='hidden';
 const dialog=()=>document.querySelector('#modal:not([hidden]) .modal-body');
 const scope=()=>dialog()||document.querySelector('#app');
 const context=()=>[location.pathname,state().mode,state().page,dialog()?.querySelector('h2')?.textContent||''].join('|');
 const label=el=>{
  const linked=el.id?[...document.querySelectorAll('label[for]')].find(l=>l.htmlFor===el.id):null;
  return (el.getAttribute('aria-label')||linked?.textContent||el.closest('label')?.textContent||(el.matches('input,textarea,select')?'':el.textContent)||el.getAttribute('placeholder')||el.name||tr('화면 항목','Screen control')).trim().replace(/\s+/g,' ').slice(0,100);
 };
 const pageInfo={
  'participant:home':['행사 홈','지도·부스 찾기, 프로그램, 미션과 전체 설문으로 이동합니다. 하단 메뉴로 언제든 화면을 바꿀 수 있습니다.','Event home','Find booths, browse programs and missions, or open the event survey. Use the bottom menu to switch screens.'],
  'participant:programs':['프로그램','날짜를 고르고 상세 안내·위치 보기를 확인하세요. 관심 일정은 이 기기에 저장합니다.','Programs','Filter by date, open details and location, and save programs on this device.'],
  'participant:map':['지도·부스','야외는 GPS와 등록 보행로로 안내하고, 실내는 건물별 통합 평면도에서 부스 위치를 표시합니다.','Map and booths','Use GPS and registered outdoor paths, or find booths on a building’s combined indoor plan.'],
  'participant:booth':['부스 안내','체험 내용을 확인하고 위치를 찾습니다. 참여 인증은 체험 후 현장 부스 QR을 스캔해 진행합니다.','Booth information','Read the booth details and find its location. Scan the booth QR after your visit to check in.'],
  'participant:certify':['부스 참여 인증','별점을 남기거나 평가 없이 인증할 수 있습니다. 안내 중에는 인증이 실행되지 않습니다.','Booth check-in','Choose a rating or check in without one. The tour only explains the controls.'],
  'participant:certified':['인증 완료','완료된 참여 기록을 확인하고 다음 미션이나 부스를 찾아보세요.','Check-in complete','Review your check-in and find another mission or booth.'],
  'participant:missions':['미션','공개된 미션은 신청 없이 수행합니다. 부스 QR 인증은 해당 미션의 진행도에 자동 반영됩니다.','Missions','No mission signup is required. Booth check-ins automatically update matching missions.'],
  'participant:mine':['내 참여','인증 부스·미션·관심 일정과 설문·추첨 결과를 확인합니다. 같은 기기·브라우저를 이용하세요.','My visit','Review check-ins, missions, saved programs and survey or prize results. Keep using the same device and browser.'],
  'participant:survey':['행사 전체 설문','설문 안내와 동의를 확인한 후 제출합니다. 연락처는 추첨 응모를 선택할 때 입력하며 같은 번호는 최초 유효 응모 한 번만 인정합니다.','Event survey','Review the consent before submitting. Contact details are for optional prize entry; only the first valid entry per number is accepted.'],
  'participant:safety':['안전·날씨','날씨의 관측 시각과 공식 특보를 확인하고 안전시설·신고 메뉴를 이용합니다. 급박한 위험은 112·119에 전화하세요.','Safety and weather','Check observation times, official warnings and safety facilities. Call 112 or 119 for immediate danger.'],
  'participant:report':['안전 신고','현장 위치와 필요한 상황을 적고 제출합니다. 안내 중에는 신고를 전송하지 않습니다. 급박한 위험은 긴급 전화로 도움을 요청하세요.','Safety report','Describe the location and essential facts. The tour does not send a report. Call emergency services for immediate danger.'],
  'admin:dashboard':['현장 운영 대시보드','행사장 날씨, 부스·존 참여, 문의와 업무 알림을 확인합니다. 인증 집계는 현재 체류 인원과 다릅니다.','Operations dashboard','Review venue weather, check-in counts, inquiries and staff notices. Check-in counts do not show current occupancy.'],
  'admin:booths':['공간·부스 관리','존을 구성하고 부스를 검토·수정합니다. 지도에 위치를 배치하고 부스별 QR과 관리 접근을 설정합니다.','Zones and booths','Set up zones, review booths, place them on maps and manage QR codes and staff access.'],
  'admin:content':['공지·프로그램','참가자 공지와 프로그램을 등록하고 공개 영어 번역을 검토합니다.','Notices and programs','Publish participant notices and programs, and review English translations.'],
  'admin:missions':['미션·전체 설문','미션을 개설하고 전체 설문을 구성합니다. 설문 원문 붙여넣기와 표준 문항을 사용할 수 있습니다.','Missions and survey','Create missions and the event survey using pasted questions or standard templates.'],
  'admin:draw':['추첨·상품권','응모 마감 후 후보를 확인해 추첨합니다. 발송용 CSV와 외부 발송 결과를 관리합니다. 안내는 실제 추첨을 실행하지 않습니다.','Prize draw','Review eligible entries after closing, run draws and manage delivery exports. This tour never runs a draw.'],
  'admin:messages':['소통·현장 대응','유형별 부스 문의에 답변하고 담당자·처리 상태를 지정합니다. 업무 알림의 확인 현황도 조회합니다.','Staff communication','Reply to categorized inquiries, assign staff and track resolution and notice acknowledgements.'],
  'admin:safety':['안전 신고 대응','일반 신고와 민감 신고는 권한에 따라 조회합니다. 접수·확인·진행·완료 상태와 답변을 기록합니다.','Safety response','View reports according to your permissions and record their status and replies.'],
  'admin:reports':['통계·결과 보고서','참여·평가·설문을 집계하고 CSV·보고서를 출력합니다. 탄소·경제 효과는 근거가 확인된 범위에서 해석하세요.','Reports','Review participation, ratings and surveys, then export CSV or print reports. Interpret estimates using verified evidence.'],
  'admin:settings':['행사 설정','행사 정보·설문 자격·테마·권한·날씨를 설정합니다. 개인정보 삭제는 되돌릴 수 없으므로 처리 범위를 확인하세요.','Event settings','Manage event details, eligibility, branding, permissions and weather. Review the scope before deleting private data.'],
  'staff:staff-home':['부스 현황','부스 참여·평가·업무 알림을 확인합니다. 운영 상태 변경은 모든 공동 관리 담당자에게 적용됩니다.','Booth overview','Review participation, ratings and notices. Booth status changes apply to all staff sharing this booth.'],
  'staff:staff-info':['부스 정보','소개·체험 내용을 수정합니다. 부스명·존·위치 변경은 운영본부에 요청하세요.','Booth details','Edit the booth description. Ask headquarters to change its name, zone or location.'],
  'staff:staff-qr':['참가 인증 QR','참가자가 스캔할 QR을 출력합니다. 관리 주소·공통 비밀번호는 담당자에게만 공유하세요.','Check-in QR','Print the participant QR. Share management access and the shared password only with booth staff.'],
  'staff:staff-messages':['운영본부 소통','용건 유형을 고르고 문의를 보냅니다. 업무 알림은 내용을 확인한 후 확인 버튼을 누르세요.','Contact headquarters','Choose an inquiry category and send your message. Acknowledge notices after reading them.'],
  'staff:staff-survey':['부스 운영 실적','부스 전체 기준의 이동·인쇄·지출 실적을 작성합니다. 모르는 값은 비우고 공동 담당자와 중복 입력을 조정하세요.','Booth activity survey','Report transport, materials and spending for the whole booth. Leave unknown values blank and coordinate with other staff.']
 };
 const actions={
  'new-event':['행사 정보를 입력해 새 비공개 행사를 만듭니다. 기존 행사 설정을 복제할 수도 있습니다.','Create a private event or copy another event’s settings.'],
  'add-zone':['운영자가 존 이름과 표시 색상을 등록합니다. 부스 담당자는 등록된 존을 선택합니다.','Create a named, color-coded zone for booth registration.'],
  'registration-link':['이 행사의 부스 등록 링크를 확인해 담당자에게 전달합니다.','Copy this event’s booth registration link for organizers.'],
  'map-editor':['건물 통합 평면도를 등록하고 부스를 배치합니다. 야외 지도 편집에서는 배치도·보행로·건물 진입 범위를 설정합니다.','Upload combined indoor plans, place booths, and edit outdoor overlays, paths and building entrances.'],
  'outdoor-editor':['야외 배경·배치도·통로·실내 전환 범위를 편집합니다. 공개 적용 전 실제 장소와 위치를 확인하세요.','Edit outdoor overlays, paths and indoor transition boundaries. Check them against the actual venue before publishing.'],
  'services-settings':['날씨 기준 지역과 서버 연결 상태를 확인합니다. 행사 총괄 권한으로 날씨 지역을 저장할 수 있습니다.','Review provider connections and weather locations. Event owners can save location settings.'],
  'visual-editor':['앱 배경과 원본 포스터를 나누고 글자·필터·배치를 조절합니다. 모바일·PC 미리보기 후 적용해야 공개 화면에 저장됩니다.','Adjust artwork, poster, typography, filters and positioning. Preview mobile and desktop layouts before applying.'],
  'visual-device':['모바일 또는 PC에서 보이는 홈 화면을 미리 봅니다. 이 버튼만으로 설정이 저장되지는 않습니다.','Preview the mobile or desktop home screen without saving changes.'],
  'visual-readable':['선택한 단색 바탕을 기준으로 대비가 높은 남색 또는 흰색 글자를 추천합니다. 이미지 위에서는 실제 미리보기도 확인하세요.','Choose navy or white text for contrast with the selected solid surface; also check the actual image preview.'],
  'weather-refresh':['날씨를 다시 조회합니다. 관측 시각을 확인하세요. 기상청 발표와 서버 캐시 주기에 따라 수치는 유지될 수 있습니다.','Request weather again and check its observation time. Provider publication and caching may retain the same reading.'],
  'translations-open':['영어 초안을 작성·검토하고 공개합니다. 검토한 최신 원문의 번역만 참가자에게 표시합니다.','Write and review English drafts. Only approved translations matching the current source are published.'],
  'translations-generate':['공개 문구의 번역 초안을 생성합니다. 서버 번역 키가 필요하며 API 비용이 발생할 수 있습니다.','Generate translation drafts for public content. A server key is required and API charges may apply.'],
  'edit-survey':['설문 원문을 붙여넣거나 표준 문항을 선택한 후 질문·선택지·동의문을 확인합니다.','Paste survey text or select templates, then review the questions, choices and consent.'],
  'templates-add':['선택한 표준 설문 문항을 편집 목록에 추가합니다. 저장 전 중복 문항과 실제 수집 목적을 확인하세요.','Add selected template questions. Review duplicates and collection purposes before saving.'],
  'parse-survey':['붙여넣은 텍스트를 질문과 선택지 초안으로 구성합니다. 자동 구성 결과를 검토하세요.','Turn pasted text into draft questions and choices, then review the result.'],
  'draw':['실제 추첨 전에 후보·정원·마감 조건을 확인하는 화면을 엽니다.','Review eligible entries, capacity and closing conditions before a draw.'],
  'confirm-draw':['확인 후 실제 추첨을 실행하는 버튼입니다. 튜토리얼을 끝내고 대상과 조건을 검토한 뒤 사용하세요.','This runs the actual draw. Finish the tour and review the candidates and conditions first.'],
  'export':['현재 권한으로 CSV 파일을 내려받습니다. 연락처가 포함된 파일은 접근·보관 범위를 관리하세요.','Download an authorized CSV export and manage access to files containing contact information.'],
  'purge':['개인정보 삭제 확인 절차를 엽니다. 삭제 범위와 별도 백업·다운로드 파일의 보관 상태를 확인하세요.','Open the deletion review. Check the scope and separately retained backups and exports.'],
  'print':['현재 출력 화면을 인쇄하거나 PDF로 저장합니다.','Print the current view or save it as PDF.'],
  'staff-qr':['참가자용 부스 인증 QR을 확인·다운로드·인쇄합니다.','View, download or print the participant check-in QR.'],
  'ack':['업무 알림 내용을 확인했다는 기록을 남깁니다. 확인은 처리 완료와 별도로 관리됩니다.','Record that the notice has been read. Acknowledgement is tracked separately from resolution.'],
  'inquiry':['대화와 처리 현황을 열어 답변·진행 상태를 확인합니다.','Open the conversation and check replies and progress.'],
  'rate':['참가 인증에 남길 별점을 고릅니다. 평가 없이 인증할 수도 있습니다.','Choose an optional rating. Check-in is also available without a rating.'],
  'certify':['현재 운영 상태를 확인한 뒤 참여 인증을 제출합니다. 중단·종료 부스는 인증할 수 없습니다.','Submit a booth check-in when it is open. Paused or closed booths do not accept check-ins.'],
  'certify-skip':['별점 없이도 같은 참여·미션 인증을 제출할 수 있습니다.','Check in without a rating for the same participation and mission credit.'],
  'gps-start':['기기 위치 권한을 허용하면 GPS 안내를 시작합니다. GPS가 불안정하면 지도를 직접 선택할 수 있습니다.','Allow device location to begin GPS guidance. Select the map manually when GPS is unreliable.'],
  'logout':['관리 화면의 로그인을 종료합니다.','Sign out of the management screen.']
 };
 const fields={
  'weather-location':['확인할 행사장 기준 지역을 선택합니다. 선택한 지역의 자료만 표시합니다.','Choose a venue weather location. Only that location’s readings are shown.'],
  'staff-status':['운영 중·일시 중단·운영 종료를 선택합니다. 중단·종료 시 참가자 QR 인증이 차단됩니다.','Choose open, paused or closed. Paused and closed booths block participant check-ins.'],
  'event-switch':['관리할 행사를 선택합니다. 날씨·참여 현황·설정은 선택한 행사 기준입니다.','Select the event to manage. Weather, counts and settings follow the selected event.'],
  'weather-locations':['한 줄에 지역명, nx, ny를 입력합니다. 지도 중심으로 격자 초안을 추가한 뒤 실제 행사장 기준인지 확인하세요.','Enter location name, nx and ny on each line. Check map-derived grid coordinates against the actual venue.'],
  'phone':['추첨 응모를 선택하면 당첨 연락을 받을 번호를 입력합니다. 동일 연락처는 최초 유효 응모 한 건만 인정합니다.','For optional prize entry, provide a contact number. Only the first valid entry per number is accepted.'],
  'phone_check':['앞에서 입력한 연락처와 같은 번호를 다시 입력해 오타를 확인합니다.','Enter the same contact number again to check for typing errors.'],
  'age_group':['연령 구분을 선택합니다. 보호자 동의 확인 기능 준비 전에는 만 14세 미만 개인정보 설문을 제출할 수 없습니다.','Select the age group. Personal-data survey submission for under-14s is unavailable until guardian consent verification is supported.'],
  'category':['용건 유형을 선택하면 운영본부가 문의를 분류·집계하고 담당자를 배정하는 데 도움이 됩니다.','Choose an inquiry category to help headquarters classify, analyze and assign it.'],
  'zone':['행사 운영자가 만든 존 중 해당 부스가 속할 존을 선택합니다.','Choose the booth’s zone from the zones created by the event organizer.'],
  'password':['이 화면의 계정 또는 부스 관리 비밀번호를 입력합니다. 안내는 입력값을 읽거나 전송하지 않습니다.','Enter the account or booth management password. This tour never reads field values.'],
  'manager':['운영본부에서 받은 부스 관리 코드를 입력합니다. 참가자 인증 QR와는 다른 담당자용 접근 정보입니다.','Enter the management code supplied by headquarters for booth staff.'],
  'display':['이번 접속 담당자의 표시명을 입력합니다. 업무 알림 확인과 처리 기록에 사용합니다.','Enter a staff display name for acknowledgement and activity records.']
 };
 function intro(root){const s=state(),modal=dialog(),heading=root.querySelector('h1,h2,.app-header strong');
  if(modal)return {el:modal.querySelector('.modal-header')||modal,title:heading?.textContent||tr('상세 화면 안내','Detail screen'),body:tr('화면에 있는 실제 입력칸과 버튼을 순서대로 안내합니다. 안내 중에는 값이 입력되거나 작업이 실행되지 않습니다.','Follow the real fields and buttons. The tour does not enter values or perform actions.')};
  const entry=root.querySelector('.login form')?.dataset.form;
  const entries={
   'login':['운영자 로그인','Render에 지정한 관리자 이메일·비밀번호 또는 초대받은 계정으로 로그인합니다.','Organizer login','Sign in with the owner credentials configured on the host, or your invited account.'],
   'setup':['첫 관리자 설정','이메일·표시명·12자 이상 비밀번호로 최초 관리자를 만듭니다. 초기 설정은 허용된 로컬 환경에서만 진행합니다.','First administrator','Create the initial owner using an email, display name and a password of at least 12 characters in the allowed local environment.'],
   'booth-register':['부스 등록','행사의 소속 존을 선택하고 부스 소개·공통 관리 비밀번호를 입력합니다. 등록 후 운영자의 승인을 기다립니다.','Booth registration','Choose a zone, describe your booth and set its shared password, then wait for organizer approval.'],
   'booth-login':['부스 담당자 로그인','관리 코드·공통 비밀번호·이번 접속 표시명으로 담당자 화면에 접속합니다.','Booth staff login','Use the management code, shared password and your staff display name.'],
   'invite':['운영본부 초대 수락','받은 초대 코드와 계정 정보를 확인한 뒤 초대를 수락합니다.','Accept an invitation','Review your invitation code and account information before accepting.']
  };
  const info=entry?entries[entry]:pageInfo[s.mode+':'+s.page];
  return {el:heading||root,title:info?tr(info[0],info[2]):heading?.textContent||tr('이용방법','How to use'),body:info?tr(info[1],info[3]):tr('이 화면의 입력칸과 버튼을 순서대로 확인합니다. 안내를 마친 뒤 직접 입력하고 진행하세요.','Review this screen’s fields and buttons, then enter your details after finishing the tour.')};
 }
 function steps(root){const result=[intro(root)],seen=new Set(),modal=dialog();
  if(!modal){const nav=root.querySelector('.sidebar-nav,.staff-nav,nav[aria-label="참가자 메뉴"]');if(visible(nav))result.push({el:nav,title:tr('화면 메뉴','Screen menu'),body:tr('각 메뉴로 이동한 뒤 이용방법을 누르면 해당 화면의 버튼과 입력칸을 안내합니다.','Open any menu and select How to use for a tour of that screen.')});
   for(const [selector,title,body,englishTitle,englishBody] of [
    ['.dashboard-weather','행사장 날씨','기온·풍속·습도·강수와 초단기예보를 확인합니다. 1분마다 확인하며 관측 시각·수신 시각·지연 안내를 함께 보세요.','Venue weather','Review temperature, wind, humidity, rain and near-term forecasts. Checks run every minute; review observation times and delay notices.'],
    ['.stats','참여·현황 집계','현재 화면의 참여·평가·응모 집계를 확인합니다. 참가 패스 기준 수치이며 현재 체류 인원과 같지 않습니다.','Activity counts','Review counts for this screen. Participant pass counts do not equal current occupancy.'],
    ['.grid3:has(.zone-card)','존별 참여 합계','소속 부스별 참여자를 합산합니다. 여러 부스를 이용한 참가자는 부스별로 합산됩니다.','Zone totals','Totals add up booth participation, including visitors who attended multiple booths.']
   ]){const el=root.querySelector(selector);if(visible(el))result.push({el,title:tr(title,englishTitle),body:tr(body,englishBody)});}
  }
  for(const el of root.querySelectorAll('input:not([type="hidden"]),textarea,select,button,a[href]')){
   if(!visible(el)||el.matches('[data-help-start]')||el.closest('.sidebar-nav,.staff-nav,nav[aria-label="참가자 메뉴"],.leaflet-control-container,#kv-preview-stage')||el.dataset.action==='close')continue;
   const action=el.dataset.action||'',prefix=action.split(':')[0],name=label(el),field=el.id||el.name;
   const key=el.matches('input,textarea,select')?'field:'+((el.name||field).startsWith('q_')?'survey-question':el.name||field):'button:'+(action?prefix+(['nav','staff-nav','load-reports','report','zoom','program-date'].includes(prefix)?':'+action.split(':')[1]:''):name);
   if(seen.has(key))continue;seen.add(key);
   let body;
   if(el.matches('input,textarea,select')){
    const spec=fields[field]||fields[el.name];
    body=spec?tr(...spec):el.type==='checkbox'?tr('안내 내용을 확인한 후 선택합니다. 필수 동의와 선택 동의를 구분해 주세요.','Read the description before selecting it. Distinguish required and optional consent.'):el.type==='file'?tr('기기에서 사용할 이미지나 파일을 선택합니다. 표시된 형식과 용량을 확인하세요.','Choose a file from your device and check the listed size and format requirements.'):el.tagName==='SELECT'?tr('목록에서 현재 작업에 맞는 값을 선택합니다.','Choose the appropriate value from the list.'):tr('표시된 항목에 맞게 입력합니다. 별표·필수 표시와 입력 조건을 확인하세요.','Enter the requested information and check required fields and validation rules.');
   }else if(actions[prefix])body=tr(...actions[prefix]);
   else if(el.type==='submit')body=tr('입력 내용과 동의를 확인한 뒤 이 버튼으로 제출·저장합니다. 튜토리얼은 제출하지 않습니다.','Review your entries and consent, then use this button to submit or save. The tour does not submit.');
   else if(el.getAttribute('href')?.startsWith('tel:'))body=tr('실제 이용 시 이 번호로 전화를 걸어 도움을 요청합니다.','Use this telephone link to call for assistance.');
   else if(el.disabled)body=tr('현재 사용할 수 없는 버튼입니다. 화면의 안내와 필요한 권한·설정·기간을 확인하세요.','This control is currently unavailable. Check its instructions, permissions, configuration and dates.');
   else body=tr('이 항목을 누르면 관련 안내·상세 화면 또는 다음 단계로 이동합니다.','Use this control to open related details or continue to the next step.');
   result.push({el,title:name,body});
  }
  return result;
 }
 function launcher(){let button=document.querySelector('#help-launcher');if(!button){button=document.createElement('button');button.id='help-launcher';button.type='button';button.className='help-launcher';button.dataset.helpStart=''}
  const root=document.querySelector('#app');let host=root?.querySelector('.admin-top,.app-header .tools,.app-header');
  if(!host&&root){const parent=root.querySelector('.login,.page')||root;host=parent.querySelector(':scope > .screen-help');if(!host){host=document.createElement('div');host.className='screen-help';parent.prepend(host)}}
  if(host&&button.parentElement!==host)host.append(button);const hidden=!!dialog();if(button.hidden!==hidden)button.hidden=hidden;const text=tr('이용방법','How to use');if(button.textContent!==text)button.textContent=text;
  const header=dialog()?.querySelector('.modal-header');if(header&&!header.querySelector('[data-help-start]')){const b=document.createElement('button');b.type='button';b.className='help-trigger';b.dataset.helpStart='';b.textContent=tr('이용방법','How to use');header.insertBefore(b,header.lastElementChild)}
 }
 function stop(){if(!tour)return;const old=tour;tour=null;old.layer.remove();for(const [el,inert] of old.background)if(el.isConnected)el.inert=inert;document.body.style.overflow=old.overflow;window.removeEventListener('resize',position);document.removeEventListener('scroll',position,true);if(old.focus?.isConnected&&!old.focus.closest('[hidden]'))old.focus.focus({preventScroll:true});else document.querySelector('#help-launcher')?.focus({preventScroll:true});launcher()}
 function position(){if(!tour)return;const step=tour.steps[tour.index];if(!visible(step.el)){stop();return}const r=step.el.getBoundingClientRect(),margin=6,top=Math.max(4,r.top-margin),left=Math.max(4,r.left-margin),right=Math.min(innerWidth-4,r.right+margin),bottom=Math.min(innerHeight-4,r.bottom+margin);
  Object.assign(tour.spot.style,{top:top+'px',left:left+'px',width:Math.max(0,right-left)+'px',height:Math.max(0,bottom-top)+'px'});
  const box=tour.panel.getBoundingClientRect(),x=Math.max(8,Math.min(left,innerWidth-box.width-8));
  let y=bottom+12;if(y+box.height>innerHeight-8)y=top-box.height-12;if(y<8)y=Math.max(8,innerHeight-box.height-8);
  Object.assign(tour.panel.style,{left:x+'px',top:y+'px'});
 }
 function show(index){if(!tour)return;tour.index=Math.max(0,Math.min(index,tour.steps.length-1));const step=tour.steps[tour.index];if(!visible(step.el)){stop();return}step.el.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
  tour.counter.textContent=tr('단계 ','Step ')+(tour.index+1)+' / '+tour.steps.length;tour.title.textContent=step.title;tour.body.textContent=step.body;tour.previous.disabled=tour.index===0;tour.next.textContent=tour.index===tour.steps.length-1?tr('안내 마치기','Finish'):tr('다음','Next');
  tour.next.focus({preventScroll:true});requestAnimationFrame(position);
 }
 function start(){stop();const root=scope();if(!root)return;const all=steps(root).filter(s=>visible(s.el));if(!all.length)return;
  const layer=document.createElement('div');layer.className='tour-layer';layer.setAttribute('role','dialog');layer.setAttribute('aria-modal','true');layer.setAttribute('aria-labelledby','tour-title');
  layer.innerHTML='<div class="tour-spot" aria-hidden="true"></div><section class="tour-panel"><div class="tour-top"><small class="tour-counter"></small><button type="button" class="tour-exit"></button></div><h2 id="tour-title"></h2><p class="tour-copy"></p><div class="tour-controls"><button type="button" class="tour-previous"></button><button type="button" class="tour-next primary"></button></div></section>';
  const background=[document.querySelector('#app'),document.querySelector('#modal'),document.querySelector('#help-launcher')].filter(Boolean).map(el=>[el,el.inert]);
  tour={layer,steps:all,index:0,key:context(),focus:document.activeElement,overflow:document.body.style.overflow,background,spot:layer.querySelector('.tour-spot'),panel:layer.querySelector('.tour-panel'),counter:layer.querySelector('.tour-counter'),title:layer.querySelector('h2'),body:layer.querySelector('.tour-copy'),previous:layer.querySelector('.tour-previous'),next:layer.querySelector('.tour-next')};
  for(const [el] of background)el.inert=true;document.body.style.overflow='hidden';document.body.append(layer);
  const exit=layer.querySelector('.tour-exit');exit.textContent=tr('안내 닫기','Close tour');exit.onclick=stop;tour.previous.textContent=tr('이전','Back');tour.previous.onclick=()=>show(tour.index-1);tour.next.onclick=()=>tour.index===tour.steps.length-1?stop():show(tour.index+1);
  layer.addEventListener('keydown',event=>{event.stopPropagation();if(event.key==='Escape'){event.preventDefault();stop();return}if(event.key==='Tab'){const buttons=[...layer.querySelectorAll('button:not(:disabled)')];const current=buttons.indexOf(document.activeElement);event.preventDefault();buttons[(current+(event.shiftKey?-1:1)+buttons.length)%buttons.length].focus()}if(event.key==='ArrowRight'){event.preventDefault();if(tour.index<tour.steps.length-1)show(tour.index+1)}if(event.key==='ArrowLeft'){event.preventDefault();show(tour.index-1)}});
  window.addEventListener('resize',position);document.addEventListener('scroll',position,true);show(0);
 }
 document.addEventListener('click',event=>{if(event.target.closest('[data-help-start]')){event.preventDefault();event.stopImmediatePropagation();start()}},true);
 const observer=new MutationObserver(()=>{if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;launcher();if(tour&&(tour.key!==context()||!tour.steps[tour.index].el.isConnected))stop()})});
 for(const el of [document.querySelector('#app'),document.querySelector('#modal')])if(el)observer.observe(el,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden']});
 launcher();
 return {start,stop,isActive:()=>!!tour};
})();
