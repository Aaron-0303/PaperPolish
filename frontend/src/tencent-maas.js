const PROVIDER_KEY='paperpolish_remote_provider_v1'
const GENERIC_MODEL_KEY='paperpolish_generic_remote_model_v1'
const LEGACY_BROWSER_KEY='paperpolish_remote_api_key_v1'
const TENCENT_MODEL='hy-mt2-pro'
const SERVER_KEY='__SERVER__'

let keyStatus={generic:false,tencent:false}
let nativeFetch=window.fetch.bind(window)

function setVueInput(input,value){
  if(!input||input.value===value) return
  const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set
  if(setter) setter.call(input,value)
  else input.value=value
  input.dispatchEvent(new Event('input',{bubbles:true}))
  input.dispatchEvent(new Event('change',{bubbles:true}))
}

function provider(){
  return localStorage.getItem(PROVIDER_KEY)==='tencent'?'tencent':'generic'
}

function providerLabel(value){
  return value==='tencent'?'腾讯云 Hy-MT2 Pro':'通用 OpenAI API'
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
    const status=panel.querySelector('.provider-key-status')
    if(status) status.textContent='请输入新的 API Key 后再保存。'
    return
  }
  const button=panel.querySelector('.provider-key-save')
  if(button){button.disabled=true;button.textContent='保存中…'}
  try{
    const response=await nativeFetch(`/api/provider-keys/${current}`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({api_key:value}),
    })
    const data=await response.json().catch(()=>({}))
    if(!response.ok) throw new Error(data.detail||'保存失败')
    keyStatus[current]=true
    setVueInput(input,'')
    localStorage.removeItem(LEGACY_BROWSER_KEY)
    const status=panel.querySelector('.provider-key-status')
    if(status) status.textContent=`${providerLabel(current)} API Key 已保存在服务器。`
  }catch(error){
    const status=panel.querySelector('.provider-key-status')
    if(status) status.textContent=error.message||'保存失败'
  }finally{
    if(button){button.disabled=false;button.textContent='保存 API Key'}
    applyProvider(panel)
  }
}

async function clearProviderKey(panel){
  const current=provider()
  try{
    const response=await nativeFetch(`/api/provider-keys/${current}`,{method:'DELETE'})
    if(!response.ok) throw new Error('删除失败')
    keyStatus[current]=false
    const status=panel.querySelector('.provider-key-status')
    if(status) status.textContent=`${providerLabel(current)} API Key 已从服务器删除。`
  }catch(error){
    const status=panel.querySelector('.provider-key-status')
    if(status) status.textContent=error.message||'删除失败'
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
  if(apiLabel) apiLabel.innerHTML=`API Key <span>分别保存在服务器</span>`
  if(apiInput){
    if(apiInput.value===SERVER_KEY) setVueInput(apiInput,'')
    apiInput.placeholder=keyStatus[current]?'已在服务器配置 · 输入新 Key 可覆盖':'请输入 API Key 并保存到服务器'
    apiInput.autocomplete='new-password'
  }
  if(keyStatusText) keyStatusText.textContent=keyStatus[current]?`${providerLabel(current)}：服务器已配置 API Key`:`${providerLabel(current)}：尚未配置 API Key`
  if(clearButton) clearButton.hidden=!keyStatus[current]

  if(current==='tencent'){
    if(modelInput&&modelInput.value&&modelInput.value!==TENCENT_MODEL) localStorage.setItem(GENERIC_MODEL_KEY,modelInput.value)
    if(host&&host.textContent!=='https://tokenhub.tencentmaas.com/v1') host.textContent='https://tokenhub.tencentmaas.com/v1'
    if(modelInput){
      setVueInput(modelInput,TENCENT_MODEL)
      modelInput.readOnly=true
      modelInput.placeholder=TENCENT_MODEL
    }
    if(fetchButton) fetchButton.hidden=true
  }else{
    if(host&&host.textContent!=='https://api.gpt.ge') host.textContent='https://api.gpt.ge'
    if(modelInput){
      modelInput.readOnly=false
      if(modelInput.value===TENCENT_MODEL) setVueInput(modelInput,localStorage.getItem(GENERIC_MODEL_KEY)||'')
      modelInput.placeholder='填写或从 API 获取模型'
    }
    if(fetchButton) fetchButton.hidden=false
  }
}

function mountTencentProvider(){
  const panel=document.querySelector('.settings-api-panel')
  if(!panel) return

  localStorage.removeItem(LEGACY_BROWSER_KEY)

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
        setVueInput(input,'')
        applyProvider(panel)
      })
    })
  }

  if(!panel.querySelector('.provider-key-actions')){
    const secretWrap=panel.querySelector('.secret-input-wrap')
    const actions=document.createElement('div')
    actions.className='provider-key-actions'
    actions.innerHTML=`
      <div class="provider-key-status"></div>
      <div class="provider-key-buttons">
        <button type="button" class="btn secondary provider-key-save">保存 API Key</button>
        <button type="button" class="btn ghost provider-key-clear">删除已保存 Key</button>
      </div>
    `
    secretWrap?.parentElement?.appendChild(actions)
    actions.querySelector('.provider-key-save')?.addEventListener('click',()=>saveProviderKey(panel))
    actions.querySelector('.provider-key-clear')?.addEventListener('click',()=>clearProviderKey(panel))
  }

  applyProvider(panel)
}

window.fetch=async function(input,init={}){
  const url=typeof input==='string'?input:input?.url||''
  if((url==='/api/remote/polish'||url==='/api/remote/models')&&init?.body){
    try{
      const body=JSON.parse(init.body)
      body.api_key=SERVER_KEY
      init={...init,body:JSON.stringify(body)}
    }catch{}
  }
  return nativeFetch(input,init)
}

const observer=new MutationObserver(mountTencentProvider)
observer.observe(document.documentElement,{childList:true,subtree:true})
queueMicrotask(()=>{mountTencentProvider();refreshKeyStatus()})
