function simplifyTerminologyUi(){
  document.querySelectorAll('.quick-action-row select,.add-term-bar select').forEach(el=>el.hidden=true)

  document.querySelectorAll('.terms-table').forEach(table=>{
    table.querySelectorAll('tr').forEach(row=>{
      const cells=row.children
      if(cells.length>=4) cells[2].hidden=true
    })
  })

  document.querySelectorAll('.bulk-import-head p').forEach(node=>{
    const text='每行一个术语，使用英文逗号分隔：英文术语,中文对应。'
    if(node.textContent!==text) node.textContent=text
  })

  document.querySelectorAll('.bulk-import-guide').forEach(node=>node.remove())

  document.querySelectorAll('.bulk-import-textarea').forEach(textarea=>{
    const placeholder='在这里粘贴术语，每行一条···\nvisual odometry,视觉里程计\nDROID-SLAM,DROID-SLAM\nactive mapping,主动建图'
    if(textarea.placeholder!==placeholder) textarea.placeholder=placeholder
  })
}

let queued=false
function queueSimplify(){
  if(queued) return
  queued=true
  requestAnimationFrame(()=>{
    queued=false
    simplifyTerminologyUi()
  })
}

const observer=new MutationObserver(queueSimplify)
observer.observe(document.documentElement,{childList:true,subtree:true})
queueMicrotask(simplifyTerminologyUi)
