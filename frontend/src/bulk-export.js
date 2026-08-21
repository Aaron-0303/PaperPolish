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

function exportCurrentGlossary(){
  const target=document.querySelector('.bulk-import-target strong')
  const groupName=target?.textContent?.trim()
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

function mountBulkExportButton(){
  const actions=document.querySelector('.bulk-import-actions')
  if(!actions||actions.querySelector('.bulk-export-button')) return
  const button=document.createElement('button')
  button.type='button'
  button.className='btn secondary bulk-export-button'
  button.textContent='批量导出 CSV'
  button.addEventListener('click',exportCurrentGlossary)
  actions.prepend(button)
}

const observer=new MutationObserver(mountBulkExportButton)
observer.observe(document.documentElement,{childList:true,subtree:true})
queueMicrotask(mountBulkExportButton)
