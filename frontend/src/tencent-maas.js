const PROVIDER_KEY='paperpolish_remote_provider_v1'
const GENERIC_MODEL_KEY='paperpolish_generic_remote_model_v1'
const TENCENT_MODEL='hy-mt2-pro'

function setVueInput(input,value){
  if(!input) return
  const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')?.set
  if(setter) setter.call(input,value)
  else input.value=value
  input.dispatchEvent(new Event('input',{bubbles:true}))
  input.dispatchEvent(new Event('change',{bubbles:true}))
}

function provider(){
  return localStorage.getItem(PROVIDER_KEY)==='tencent'?'tencent':'generic'
}

function applyProvider(panel){
  const current=provider()
  const host=panel.querySelector('.settings-api-host code')
  const modelInput=panel.querySelector('input[list="remote-model-options"]')
  const fetchButton=panel.querySelector('.settings-fetch-models')
  const buttons=panel.querySelectorAll('.maas-provider-button')

  buttons.forEach(button=>button.classList.toggle('active',button.dataset.provider===current))

  if(current==='tencent'){
    if(modelInput&&modelInput.value&&modelInput.value!==TENCENT_MODEL) localStorage.setItem(GENERIC_MODEL_KEY,modelInput.value)
    if(host) host.textContent='https://tokenhub.tencentmaas.com/v1'
    if(modelInput){
      setVueInput(modelInput,TENCENT_MODEL)
      modelInput.readOnly=true
      modelInput.placeholder=TENCENT_MODEL
    }
    if(fetchButton) fetchButton.hidden=true
  }else{
    if(host) host.textContent='https://api.gpt.ge'
    if(modelInput){
      modelInput.readOnly=false
      if(modelInput.value===TENCENT_MODEL){
        setVueInput(modelInput,localStorage.getItem(GENERIC_MODEL_KEY)||'')
      }
      modelInput.placeholder='填写或从 API 获取模型'
    }
    if(fetchButton) fetchButton.hidden=false
  }
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
      <small class="maas-provider-note">腾讯云使用 tokenhub.tencentmaas.com/v1，模型固定为 hy-mt2-pro。</small>
    `
    host?.insertAdjacentElement('afterend',row)
    row.querySelectorAll('.maas-provider-button').forEach(button=>{
      button.addEventListener('click',()=>{
        localStorage.setItem(PROVIDER_KEY,button.dataset.provider)
        applyProvider(panel)
      })
    })
  }

  applyProvider(panel)
}

const observer=new MutationObserver(mountTencentProvider)
observer.observe(document.documentElement,{childList:true,subtree:true})
queueMicrotask(mountTencentProvider)
