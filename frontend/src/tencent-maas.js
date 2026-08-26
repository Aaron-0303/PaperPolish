const PROVIDER_KEY='paperpolish_remote_provider_v1'
const GENERIC_MODEL_KEY='paperpolish_generic_remote_model_v1'
const LEGACY_BROWSER_KEY='paperpolish_remote_api_key_v1'
const REMOTE_MODEL_KEY='paperpolish_remote_model_v1'
const ENGINE_KEY='paperpolish_final_engine_v1'
const TENCENT_MODEL='hy-mt2-pro'
const SERVER_KEY='__SERVER__'

// Vue still expects a non-empty remoteApiKey. This sentinel is not a secret;
// the backend resolves it to the provider-specific key stored on the server.
localStorage.setItem(LEGACY_BROWSER_KEY,SERVER_KEY)

let keyStatus={generic:false,tencent:false}
const nativeFetch=window.fetch.bind(window)
let mountQueued=false

function setVueInput(input,value){
  if(!input||input.value===value) return
  const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set
  if(setter) setter.call(input,value)
  else input.value=value
  input.dispatchEvent(new Event('input',{bubbles:true}))
  input.dispatchEvent(new Event('change',{bubbles:true}))
}

function setVueTextarea(input,value){
  if(!input||input.value===value) return
  const setter=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')?.set
  if(setter) setter.call(input,value)
  else input.value=value
  input.dispatchEvent(new Event('input',{bubbles:true}))
  input.dispatchEvent(new Event('change',{bubbles:true}))
}

function setText(node,value){
  if(node&&node.textContent!==value) node.textContent=value
}

function provider(){
  return localStorage.getItem(PROVIDER_KEY)==='tencent'?'tencent':'generic'
}

function providerLabel(value){
  return value==='tencent'?'腾讯云 Hy-MT2 Pro':'通用 OpenAI API'
}

function currentRemoteModel(){
  if(provider()==='tencent') return TENCENT_MODEL
  return localStorage.getItem(REMOTE_MODEL_KEY)||localStorage.getItem(GENERIC_MODEL_KEY)||''
}

function activeTerms(){
  try{
    const groups=JSON.parse(localStorage.getItem('paperpolish_selected_glossaries_v3')||'[]')
    const terms=JSON.parse(localStorage.getItem('paperpolish_glossary_terms_v3')||'[]')
    return terms.filter(term=>groups.includes(term.groupId)).map(({english,chinese,type})=>({english,chinese,type}))
  }catch{return []}
}

function remoteTranslatePayload(text,direction,originalEnglish=''){
  return {
    text,
    direction,
    api_key:SERVER_KEY,
    model:currentRemoteModel(),
    mode:localStorage.getItem('paperpolish_mode_v1')||'paper',
    terms:activeTerms(),
    original_english:originalEnglish,
    style:localStorage.getItem('paperpolish_style_v2')||'CVPR/IEEE concise academic style',
    preferences:(localStorage.getItem('paperpolish_preferences_v1')||'Preserve technical meaning\nUse concise academic wording\nDo not expand claims').split('\n').map(v=>v.trim()).filter(Boolean),
    format_type:localStorage.getItem('paperpolish_format_v1')||'LaTeX',
    background_text:localStorage.getItem('paperpolish_background_v1')||'',
  }
}

function showRemoteToast(message,type='success'){
  const old=document.querySelector('.remote-engine-toast')
  old?.remove()
  const node=document.createElement('div')
  node.className=`toast ${type} remote-engine-toast`
  node.textContent=message
  document.body.appendChild(node)
  setTimeout(()=>node.remove(),2600)
}

async function refreshKeyStatus(){
  try{
    const response=await nativeFetch('/api/provider-keys/status')
    if(!response.ok) return
    const data=await response.json()
    keyStatus={generic:!!data.generic?.configured,tencent:!!data.tencent?.configured}
    const panel=document.querySelector('.settings-api-panel')
    if(panel) applyProvider(panel)
  }catch{}
}

async function saveProviderKey(panel){
  const input=panel.querySelector('.secret-input-wrap input')
  const current=provider()
  const value=input?.value?.trim()||''
  if(!value||value===SERVER_KEY){
    setText(panel.querySelector('.provider-key-status'),'请输入新的 API Key 后再保存。')
    return
  }
  const button=panel.querySelector('.provider-key-save')
  if(button){button.disabled=true;setText(button,'保存中…')}
  try{
    const response=await nativeFetch(`/api/provider-keys/${current}`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({api_key:value}),
    })
    const data=await response.json().catch(()=>({}))
    if(!response.ok) throw new Error(data.detail||'保存失败')
    keyStatus[current]=true
    localStorage.setItem(LEGACY_BROWSER_KEY,SERVER_KEY)
    setVueInput(input,SERVER_KEY)
    setText(panel.querySelector('.provider-key-status'),`${providerLabel(current)} API Key 已保存在服务器。`)
  }catch(error){
    setText(panel.querySelector('.provider-key-status'),error.message||'保存失败')
  }finally{
    if(button){button.disabled=false;setText(button,'保存 API Key')}
    applyProvider(panel)
  }
}

async function clearProviderKey(panel){
  const current=provider()
  try{
    const response=await nativeFetch(`/api/provider-keys/${current}`,{method:'DELETE'})
    if(!response.ok) throw new Error('删除失败')
    keyStatus[current]=false
    const input=panel.querySelector('.secret-input-wrap input')
    if(input?.value===SERVER_KEY) setVueInput(input,'')
    setText(panel.querySelector('.provider-key-status'),`${providerLabel(current)} API Key 已从服务器删除。`)
  }catch(error){
    setText(panel.querySelector('.provider-key-status'),error.message||'删除失败')
  }
  applyProvider(panel)
}

function applyProvider(panel){
  const current=provider()
  const host=panel.querySelector('.settings-api-host code')
  const modelInput=panel.querySelector('input[list="remote-model-options"]')
  const fetchButton=panel.querySelector('.settings-fetch-models')
  const apiInput=panel.querySelector('.secret-input-wrap input')
  const apiLabel=panel.querySelector('.secret-input-wrap')?.parentElement?.querySelector('.field-label')
  const buttons=panel.querySelectorAll('.maas-provider-button')
  const keyStatusText=panel.querySelector('.provider-key-status')
  const clearButton=panel.querySelector('.provider-key-clear')

  buttons.forEach(button=>button.classList.toggle('active',button.dataset.provider===current))
  if(apiLabel&&apiLabel.dataset.serverKeyLabel!=='1'){
    apiLabel.replaceChildren(document.createTextNode('API Key '),Object.assign(document.createElement('span'),{textContent:'分别保存在服务器'}))
    apiLabel.dataset.serverKeyLabel='1'
  }
  if(apiInput){
    if(keyStatus[current]&&!apiInput.value) setVueInput(apiInput,SERVER_KEY)
    if(!keyStatus[current]&&apiInput.value===SERVER_KEY) setVueInput(apiInput,'')
    const placeholder=keyStatus[current]?'已在服务器配置 · 输入新 Key 可覆盖':'请输入 API Key 并保存到服务器'
    if(apiInput.placeholder!==placeholder) apiInput.placeholder=placeholder
    if(apiInput.autocomplete!=='new-password') apiInput.autocomplete='new-password'
  }
  setText(keyStatusText,keyStatus[current]?`${providerLabel(current)}：服务器已配置 API Key`:`${providerLabel(current)}：尚未配置 API Key`)
  if(clearButton&&clearButton.hidden===keyStatus[current]) clearButton.hidden=!keyStatus[current]

  if(current==='tencent'){
    if(modelInput&&modelInput.value&&modelInput.value!==TENCENT_MODEL) localStorage.setItem(GENERIC_MODEL_KEY,modelInput.value)
    setText(host,'https://tokenhub.tencentmaas.com/v1')
    if(modelInput){
      setVueInput(modelInput,TENCENT_MODEL)
      if(!modelInput.readOnly) modelInput.readOnly=true
      if(modelInput.placeholder!==TENCENT_MODEL) modelInput.placeholder=TENCENT_MODEL
    }
    if(fetchButton&&!fetchButton.hidden) fetchButton.hidden=true
  }else{
    setText(host,'https://api.gpt.ge')
    if(modelInput){
      if(modelInput.readOnly) modelInput.readOnly=false
      if(modelInput.value===TENCENT_MODEL) setVueInput(modelInput,localStorage.getItem(GENERIC_MODEL_KEY)||'')
      if(modelInput.placeholder!=='填写或从 API 获取模型') modelInput.placeholder='填写或从 API 获取模型'
    }
    if(fetchButton&&fetchButton.hidden) fetchButton.hidden=false
  }

  const engineHead=document.querySelector('.settings-engine-section .settings-section-head h2')
  const engineDesc=document.querySelector('.settings-engine-section .settings-section-head p')
  setText(engineHead,'翻译引擎')
  setText(engineDesc,'控制英文 → 中文和中文 → 英文两个阶段统一使用本地模型或远程 API。')
}

function mountTencentProvider(){
  const panel=document.querySelector('.settings-api-panel')
  if(!panel) return

  if(!panel.querySelector('.maas-provider-switch')){
    const host=panel.querySelector('.settings-api-host')
    const row=document.createElement('div')
    row.className='maas-provider-switch'
    row.innerHTML=`
      <span class="maas-provider-label">API 提供商</span>
      <div class="maas-provider-options">
        <button type="button" class="maas-provider-button" data-provider="generic">通用 OpenAI API</button>
        <button type="button" class="maas-provider-button" data-provider="tencent">腾讯云 Hy-MT2 Pro</button>
      </div>
      <small class="maas-provider-note">两个提供商使用独立 API Key，并分别持久化到服务器。</small>
    `
    host?.insertAdjacentElement('afterend',row)
    row.querySelectorAll('.maas-provider-button').forEach(button=>{
      button.addEventListener('click',()=>{
        localStorage.setItem(PROVIDER_KEY,button.dataset.provider)
        const input=panel.querySelector('.secret-input-wrap input')
        setVueInput(input,keyStatus[button.dataset.provider]?SERVER_KEY:'')
        applyProvider(panel)
      })
    })
  }

  if(!panel.querySelector('.provider-key-actions')){
    const secretWrap=panel.querySelector('.secret-input-wrap')
    if(secretWrap){
      const actions=document.createElement('div')
      actions.className='provider-key-actions'
      actions.innerHTML=`
        <div class="provider-key-status"></div>
        <div class="provider-key-buttons">
          <button type="button" class="btn secondary provider-key-save">保存 API Key</button>
          <button type="button" class="btn ghost provider-key-clear">删除已保存 Key</button>
        </div>
      `
      secretWrap.parentElement?.appendChild(actions)
      actions.querySelector('.provider-key-save')?.addEventListener('click',()=>saveProviderKey(panel))
      actions.querySelector('.provider-key-clear')?.addEventListener('click',()=>clearProviderKey(panel))
    }
  }

  applyProvider(panel)
}

function queueMount(){
  if(mountQueued) return
  mountQueued=true
  requestAnimationFrame(()=>{
    mountQueued=false
    const panel=document.querySelector('.settings-api-panel')
    if(panel&&(!panel.querySelector('.maas-provider-switch')||!panel.querySelector('.provider-key-actions'))) mountTencentProvider()
  })
}

async function handleRemoteEnglishToChinese(event){
  if(localStorage.getItem(ENGINE_KEY)!=='remote') return
  const button=event.target?.closest?.('button')
  if(!button||!button.textContent?.includes('翻译为中文')) return
  const workspace=button.closest('.polish-workspace')
  if(!workspace) return

  event.preventDefault()
  event.stopPropagation()
  event.stopImmediatePropagation()

  if(button.dataset.remoteBusy==='1') return
  const cards=workspace.querySelectorAll('.editor-card')
  const sourceInput=cards[0]?.querySelector('textarea')
  const chineseInput=cards[1]?.querySelector('textarea')
  const text=sourceInput?.value?.trim()||''
  if(!text){showRemoteToast('先粘贴英文原文','warning');return}
  const model=currentRemoteModel()
  if(!model){showRemoteToast('请先在生成设置中选择 API 模型','warning');return}
  if(!keyStatus[provider()]){
    await refreshKeyStatus()
    if(!keyStatus[provider()]){showRemoteToast(`请先保存 ${providerLabel(provider())} API Key`,'warning');return}
  }

  button.dataset.remoteBusy='1'
  button.disabled=true
  const oldText=button.textContent
  button.textContent='翻译中…'
  try{
    const response=await nativeFetch('/api/remote/translate',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(remoteTranslatePayload(text,'en-zh',text)),
    })
    const data=await response.json().catch(()=>({}))
    if(!response.ok) throw new Error(data.detail||'远程翻译失败')
    setVueTextarea(chineseInput,data.result||'')
    workspace.querySelector('.mobile-stage-tabs button:nth-child(2)')?.click()
    showRemoteToast(`已通过 ${model} 翻译为中文`,'success')
  }catch(error){
    showRemoteToast(error.message||'远程翻译失败','error')
  }finally{
    delete button.dataset.remoteBusy
    button.disabled=false
    button.textContent=oldText
  }
}

window.fetch=async function(input,init={}){
  const url=typeof input==='string'?input:input?.url||''
  if((url==='/api/remote/polish'||url==='/api/remote/models'||url==='/api/remote/translate')&&init?.body){
    try{
      const body=JSON.parse(init.body)
      body.api_key=SERVER_KEY
      init={...init,body:JSON.stringify(body)}
    }catch{}
  }
  return nativeFetch(input,init)
}

document.addEventListener('click',handleRemoteEnglishToChinese,true)
const observer=new MutationObserver(queueMount)
observer.observe(document.documentElement,{childList:true,subtree:true})
queueMicrotask(()=>{mountTencentProvider();refreshKeyStatus()})
