/* Re-authenticate without replacing the editor or losing selected files. */
window.SessionUI=(()=>{
 let pending=null;
 function reauthenticate(){
  if(pending)return pending;
  pending=new Promise((resolve,reject)=>{
   const dialog=document.createElement('dialog');dialog.className='reauth-dialog';dialog.setAttribute('aria-labelledby','reauth-title');
   dialog.innerHTML=`<h2 id="reauth-title">관리자 다시 로그인</h2><p>다시 로그인이 필요합니다. 작성 중인 내용과 선택한 파일은 유지되며, 로그인하면 진행 중인 작업을 이어서 처리합니다.</p><form><label for="reauth-email">로그인 이메일</label><input id="reauth-email" name="email" type="email" autocomplete="username" value="${esc(S.me?.user?.email||'')}" required><label for="reauth-password">로그인 비밀번호</label><input id="reauth-password" name="password" type="password" autocomplete="current-password" required><p class="reauth-error" role="alert"></p><div class="actions"><button type="button" class="reauth-cancel">편집으로 돌아가기</button><button type="submit" class="primary">로그인하고 계속</button></div></form>`;
   let submitting=false,finished=false;
   const finish=error=>{if(finished)return;finished=true;dialog.close();dialog.remove();error?reject(error):resolve()};
   const cancel=()=>{if(!submitting)finish(Error('다시 로그인이 필요합니다. 입력 내용은 유지됩니다. 저장을 다시 눌러 로그인해 주세요.'))};
   // Let the native dialog handle focus/Escape without closing the editor below.
   dialog.addEventListener('keydown',event=>event.stopPropagation());
   dialog.addEventListener('cancel',event=>{event.preventDefault();cancel()});
   dialog.querySelector('.reauth-cancel').addEventListener('click',cancel);
   dialog.querySelector('form').addEventListener('submit',async event=>{
    event.preventDefault();if(submitting)return;submitting=true;
    const form=event.currentTarget,buttons=[...form.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);dialog.querySelector('.reauth-error').textContent='';
    try{
     const result=await api('/api/login','POST',{email:form.elements.email.value,password:form.elements.password.value});
     token=result.token;sessionStorage.setItem('festival_management_token',token);
     S.me=await api('/api/me','GET',undefined,false);finish();
    }catch(error){dialog.querySelector('.reauth-error').textContent=error.message}
    finally{submitting=false;buttons.forEach(b=>b.disabled=false);if(dialog.isConnected)form.elements.password.focus()}
   });
   document.body.append(dialog);dialog.showModal();dialog.querySelector(S.me?.user?.email?'#reauth-password':'#reauth-email').focus();
  }).finally(()=>{pending=null});
  return pending;
 }
 return {reauthenticate};
})();
