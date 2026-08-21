function csvEscape(value){
  const text=String(value??'')
  return /[",\r\n]/.test(text)?`"${text.replace(/"/g,'""')}"`:text
}

function loadGlossaryData(){
  try{
    return {
      groups:JSON.parse(localStorage.getItem('paperpolish_glossary_groups_v3')||'[]'),
      terms:JSON.parse(localStorage.getItem('paperpolish_glossary_terms_v3')||'[]'),
    }
  }catch{
    return {groups:[],terms:[]}
  }
}

function safeFilename(name){
  return String(name||'glossary').replace(/[\\/:*?"<>|]/g,'_').trim()||'glossary'
}

function currentGlossaryName(){
  return document.querySelector('.group-card.active .group-copy strong')?.textContent?.trim()
    || document.querySelector('.title-input')?.value?.trim()
    || ''
}

function exportCurrentGlossary(){
  const groupName=currentGlossaryName()
  if(!groupName) return

  const {groups,terms}=loadGlossaryData()
  const group=groups.find(item=>item.name===groupName)
  if(!group) return

  const rows=terms.filter(term=>term.groupId===group.id)
  const csv=rows.map(term=>[
    csvEscape(term.english),
    csvEscape(term.chinese),
    csvEscape(term.type||'preferred'),
  ].join(',')).join('\r\n')

  const blob=new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'})
  const url=URL.createObjectURL(blob)
  const anchor=document.createElement('a')
  anchor.href=url
  anchor.download=`${safeFilename(group.name)}-terms.csv`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function mountGlossaryExportButton(){
  const groupActions=document.querySelector('.glossary-detail .group-actions')
  if(!groupActions||groupActions.querySelector('.bulk-export-button')) return
  const importButton=[...groupActions.querySelectorAll('button')].find(button=>button.textContent.trim()==='批量导入')
  if(!importButton) return

  const button=document.createElement('button')
  button.type='button'
  button.className='btn secondary bulk-export-button'
  button.textContent='批量导出'
  button.addEventListener('click',exportCurrentGlossary)
  importButton.insertAdjacentElement('afterend',button)
}

function tidyBulkImportPage(){
  document.querySelectorAll('.bulk-import-actions .bulk-export-button').forEach(button=>button.remove())
  document.querySelectorAll('.bulk-import-guide').forEach(guide=>guide.remove())
  const textarea=document.querySelector('.bulk-import-textarea')
  if(textarea){
    textarea.placeholder='在这里粘贴术语，每行一条···\nvisual odometry,视觉里程计,preferred\nDROID-SLAM,DROID-SLAM,locked\nactive mapping,主动建图'
  }
}

function refreshBulkControls(){
  mountGlossaryExportButton()
  tidyBulkImportPage()
}

const observer=new MutationObserver(refreshBulkControls)
observer.observe(document.documentElement,{childList:true,subtree:true})
queueMicrotask(refreshBulkControls)
