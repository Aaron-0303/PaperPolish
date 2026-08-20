<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

const source = ref('')
const chinese = ref('')
const finalEnglish = ref('')
const loading = ref('')
const modelAction = ref('')
const showModelManager = ref(false)
const showSidebar = ref(false)
const activeStage = ref('source')
const activeTool = ref('settings')
const activeView = ref('workspace')
const mode = ref(localStorage.getItem('paperpolish_mode_v1') || 'paper')
const formatType = ref(localStorage.getItem('paperpolish_format_v1') || 'LaTeX')
const preferencesText = ref(localStorage.getItem('paperpolish_preferences_v1') || 'Preserve technical meaning\nUse concise academic wording\nDo not expand claims')
const backgroundText = ref(localStorage.getItem('paperpolish_background_v1') || '')
const style = ref(localStorage.getItem('paperpolish_style_v2') || 'CVPR/IEEE concise academic style')
const history = ref(JSON.parse(localStorage.getItem('paperpolish_history_v2') || '[]'))
const toast = reactive({ show:false, message:'', type:'info' })
let toastTimer

const modelStatus = reactive({ ready:false, model:'tencent/Hy-MT2-7B', status:'checking', downloaded:false, dtype:'bfloat16', lastLoadSeconds:null, lastError:'', gpu:null })

const glossaryGroups = ref([])
const glossaryTerms = ref([])
const selectedGlossaryIds = ref([])
const selectedGroupId = ref('')
const quickTerm = reactive({ english:'', chinese:'', type:'locked', groupId:'' })
const managerTerm = reactive({ english:'', chinese:'', type:'locked' })
const newGroup = reactive({ name:'', description:'' })
const groupEditor = reactive({ name:'', description:'' })
const editingTermId = ref('')
const editingTerm = reactive({ english:'', chinese:'', type:'locked' })
const pendingDeleteGroupId = ref('')

const sourceWords = computed(() => source.value.trim() ? source.value.trim().split(/\s+/).length : 0)
const finalWords = computed(() => finalEnglish.value.trim() ? finalEnglish.value.trim().split(/\s+/).length : 0)
const chineseChars = computed(() => chinese.value.replace(/\s/g,'').length)
const gpuPercent = computed(() => {
  const gpu=modelStatus.gpu
  if (!gpu?.available || !gpu.total_mb) return 0
  return Math.min(100, Math.max(0, gpu.used_mb/gpu.total_mb*100))
})
const modelLabel = computed(() => {
  if(modelStatus.status==='offline') return '后端离线'
  if(modelStatus.status==='loading') return '模型加载中'
  return modelStatus.ready ? '模型已就绪' : '模型未加载'
})
const currentModeLabel = computed(() => ({paper:'论文模式',default:'默认翻译',terminology:'术语模式',style:'风格模式',personalization:'个性化',delimiters:'分隔符保护','structured-data-1':'结构化数据','structured-data-2':'背景增强'}[mode.value] || '论文模式'))
const modeHelp = computed(() => ({
  paper:'术语、论文风格、背景信息和 LaTeX 保护同时生效，适合日常论文润色。',
  default:'仅执行标准翻译，不附加额外约束。',
  terminology:'重点使用当前启用术语库中的固定译法。',
  style:'重点控制目标英文的写作风格。',
  personalization:'按自定义规则逐条约束翻译。',
  delimiters:'强化保护占位符和分隔符的位置与数量。',
  'structured-data-1':'适合 LaTeX、Markdown、JSON 等结构化文本。',
  'structured-data-2':'使用额外背景信息辅助当前段落翻译。',
}[mode.value]))
const activeTerms = computed(() => glossaryTerms.value.filter(t => selectedGlossaryIds.value.includes(t.groupId)))
const selectedTermCount = computed(() => activeTerms.value.length)
const selectedGroup = computed(() => glossaryGroups.value.find(g=>g.id===selectedGroupId.value) || null)
const selectedGroupTerms = computed(() => glossaryTerms.value.filter(t=>t.groupId===selectedGroupId.value))

watch([source,chinese,finalEnglish],()=>localStorage.setItem('paperpolish_draft_v2',JSON.stringify({source:source.value,chinese:chinese.value,finalEnglish:finalEnglish.value})))
watch(history,v=>localStorage.setItem('paperpolish_history_v2',JSON.stringify(v)),{deep:true})
watch(style,v=>localStorage.setItem('paperpolish_style_v2',v))
watch(mode,v=>localStorage.setItem('paperpolish_mode_v1',v))
watch(formatType,v=>localStorage.setItem('paperpolish_format_v1',v))
watch(preferencesText,v=>localStorage.setItem('paperpolish_preferences_v1',v))
watch(backgroundText,v=>localStorage.setItem('paperpolish_background_v1',v))
watch(glossaryGroups,v=>localStorage.setItem('paperpolish_glossary_groups_v3',JSON.stringify(v)),{deep:true})
watch(glossaryTerms,v=>localStorage.setItem('paperpolish_glossary_terms_v3',JSON.stringify(v)),{deep:true})
watch(selectedGlossaryIds,v=>localStorage.setItem('paperpolish_selected_glossaries_v3',JSON.stringify(v)),{deep:true})

function makeId(prefix='id'){ return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,8)}` }
function notify(message,type='info'){
  clearTimeout(toastTimer); toast.message=message; toast.type=type; toast.show=true
  toastTimer=setTimeout(()=>{toast.show=false},2600)
}
function applyModelStatus(data){
  modelStatus.ready=!!data.model_ready; modelStatus.model=data.model||'tencent/Hy-MT2-7B'; modelStatus.status=data.status||'unknown'; modelStatus.downloaded=!!data.downloaded; modelStatus.dtype=data.dtype||'bfloat16'; modelStatus.lastLoadSeconds=data.last_load_seconds??null; modelStatus.lastError=data.last_error||''; modelStatus.gpu=data.gpu||null
}
function initializeGlossaries(){
  const storedGroups=JSON.parse(localStorage.getItem('paperpolish_glossary_groups_v3')||'[]')
  const storedTerms=JSON.parse(localStorage.getItem('paperpolish_glossary_terms_v3')||'[]')
  if(storedGroups.length){
    glossaryGroups.value=storedGroups; glossaryTerms.value=storedTerms
  }else{
    const legacy=JSON.parse(localStorage.getItem('paperpolish_terms_v2')||'[]')
    const id='glossary_default'
    glossaryGroups.value=[{id,name:'默认术语库',description:'从旧版术语自动迁移，可重命名或继续分类。'}]
    glossaryTerms.value=legacy.map(t=>({id:makeId('term'),groupId:id,english:t.english||'',chinese:t.chinese||'',type:t.type||'preferred'}))
  }
  const storedSelected=JSON.parse(localStorage.getItem('paperpolish_selected_glossaries_v3')||'[]')
  const validIds=glossaryGroups.value.map(g=>g.id)
  selectedGlossaryIds.value=storedSelected.filter(id=>validIds.includes(id))
  if(!storedSelected.length && validIds.length) selectedGlossaryIds.value=[...validIds]
  selectedGroupId.value=validIds[0]||''
  quickTerm.groupId=validIds[0]||''
  syncGroupEditor()
}
function syncGroupEditor(){
  const g=selectedGroup.value
  groupEditor.name=g?.name||''; groupEditor.description=g?.description||''
  editingTermId.value=''; pendingDeleteGroupId.value=''
}
function selectGroup(id){ selectedGroupId.value=id; syncGroupEditor() }
function toggleGlossary(id){
  selectedGlossaryIds.value=selectedGlossaryIds.value.includes(id) ? selectedGlossaryIds.value.filter(v=>v!==id) : [...selectedGlossaryIds.value,id]
}
function createGroup(){
  const name=newGroup.name.trim(); if(!name){notify('请输入术语库名称','warning');return}
  const id=makeId('glossary'); glossaryGroups.value.push({id,name,description:newGroup.description.trim()}); selectedGlossaryIds.value.push(id)
  selectedGroupId.value=id; quickTerm.groupId=id; newGroup.name=''; newGroup.description=''; syncGroupEditor(); notify('术语库已创建','success')
}
function saveGroup(){
  const g=selectedGroup.value; if(!g)return
  const name=groupEditor.name.trim(); if(!name){notify('术语库名称不能为空','warning');return}
  g.name=name; g.description=groupEditor.description.trim(); notify('术语库信息已更新','success')
}
function requestDeleteGroup(){ pendingDeleteGroupId.value=selectedGroupId.value }
function cancelDeleteGroup(){ pendingDeleteGroupId.value='' }
function confirmDeleteGroup(){
  const id=pendingDeleteGroupId.value; if(!id)return
  glossaryGroups.value=glossaryGroups.value.filter(g=>g.id!==id); glossaryTerms.value=glossaryTerms.value.filter(t=>t.groupId!==id); selectedGlossaryIds.value=selectedGlossaryIds.value.filter(v=>v!==id)
  selectedGroupId.value=glossaryGroups.value[0]?.id||''; quickTerm.groupId=selectedGroupId.value; syncGroupEditor(); notify('术语库及其术语已删除','success')
}
function addQuickTerm(){
  if(!quickTerm.groupId){notify('请先创建术语库','warning');return}
  if(!quickTerm.english.trim()&&!quickTerm.chinese.trim()){notify('请输入术语内容','warning');return}
  glossaryTerms.value.push({id:makeId('term'),groupId:quickTerm.groupId,english:quickTerm.english.trim(),chinese:quickTerm.chinese.trim(),type:quickTerm.type})
  quickTerm.english=''; quickTerm.chinese=''; quickTerm.type='locked'; notify('术语已添加','success')
}
function addManagerTerm(){
  if(!selectedGroupId.value)return
  if(!managerTerm.english.trim()&&!managerTerm.chinese.trim()){notify('请输入术语内容','warning');return}
  glossaryTerms.value.push({id:makeId('term'),groupId:selectedGroupId.value,english:managerTerm.english.trim(),chinese:managerTerm.chinese.trim(),type:managerTerm.type})
  managerTerm.english=''; managerTerm.chinese=''; managerTerm.type='locked'; notify('术语已添加','success')
}
function startEditTerm(term){ editingTermId.value=term.id; editingTerm.english=term.english; editingTerm.chinese=term.chinese; editingTerm.type=term.type }
function cancelEditTerm(){ editingTermId.value='' }
function saveTermEdit(term){
  term.english=editingTerm.english.trim(); term.chinese=editingTerm.chinese.trim(); term.type=editingTerm.type; editingTermId.value=''; notify('术语已更新','success')
}
function deleteTerm(id){ glossaryTerms.value=glossaryTerms.value.filter(t=>t.id!==id); notify('术语已删除','success') }
function openGlossaryManager(groupId=''){
  if(groupId) selectGroup(groupId); else if(!selectedGroupId.value && glossaryGroups.value[0]) selectGroup(glossaryGroups.value[0].id)
  activeView.value='glossary'; showSidebar.value=false
}
function backToWorkspace(){ activeView.value='workspace' }

async function callApi(direction){
  const text=direction==='en-zh'?source.value.trim():chinese.value.trim()
  if(!text){notify(direction==='en-zh'?'先粘贴英文原文':'先完成中文修改','warning');return}
  if(!modelStatus.ready){notify('请先加载 Hy-MT2-7B 模型','warning');showModelManager.value=true;showSidebar.value=true;activeTool.value='model';return}
  loading.value=direction
  try{
    const response=await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      text,direction,mode:mode.value,terms:activeTerms.value.map(({english,chinese,type})=>({english,chinese,type})),original_english:source.value,style:style.value,
      preferences:preferencesText.value.split('\n').map(v=>v.trim()).filter(Boolean),format_type:formatType.value,background_text:backgroundText.value,
    })})
    const data=await response.json(); if(!response.ok)throw new Error(data.detail||'请求失败')
    if(direction==='en-zh'){chinese.value=data.result;activeStage.value='chinese';notify('中文初稿已生成','success')}
    else{finalEnglish.value=data.result;activeStage.value='final';notify('学术英文已生成','success')}
    await checkHealth()
  }catch(error){notify(error.message,'error')}finally{loading.value=''}
}
function saveParagraph(){
  if(!source.value&&!chinese.value&&!finalEnglish.value){notify('当前没有可保存的内容','warning');return}
  history.value.unshift({source:source.value,chinese:chinese.value,finalEnglish:finalEnglish.value,savedAt:new Date().toISOString()}); history.value=history.value.slice(0,100); notify('段落已保存到历史记录','success')
}
function loadParagraph(item){source.value=item.source||'';chinese.value=item.chinese||'';finalEnglish.value=item.finalEnglish||'';activeStage.value='source';showSidebar.value=false;activeView.value='workspace';notify('已载入历史段落')}
function newParagraph(){if(source.value||chinese.value||finalEnglish.value)saveParagraph();source.value='';chinese.value='';finalEnglish.value='';activeStage.value='source';activeView.value='workspace'}
async function copy(text){if(!text)return;await navigator.clipboard.writeText(text);notify('已复制到剪贴板','success')}
async function checkHealth(){try{const r=await fetch('/api/model/status');const d=await r.json();if(!r.ok)throw new Error();applyModelStatus(d)}catch{modelStatus.ready=false;modelStatus.status='offline';modelStatus.lastError='无法连接后端服务'}}
async function manageModel(action){modelAction.value=action;try{const r=await fetch(`/api/model/${action}`,{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.detail||'模型操作失败');applyModelStatus(d);notify(action==='load'?'模型加载完成':'模型已卸载','success')}catch(e){notify(e.message,'error');await checkHealth()}finally{modelAction.value=''}}
function formatMb(v){if(v==null)return'—';return v>=1024?`${(v/1024).toFixed(1)} GB`:`${Math.round(v)} MB`}
function openTool(tool){activeTool.value=tool;showSidebar.value=true;if(tool==='model')showModelManager.value=true}

onMounted(()=>{
  const d=JSON.parse(localStorage.getItem('paperpolish_draft_v2')||'{}');source.value=d.source||'';chinese.value=d.chinese||'';finalEnglish.value=d.finalEnglish||''
  initializeGlossaries();checkHealth()
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-left">
        <button class="mobile-menu" @click="showSidebar=!showSidebar" aria-label="打开菜单">☰</button>
        <button class="brand-button" @click="backToWorkspace"><span class="brand-mark">P</span><span class="brand-lockup"><strong>PaperPolish</strong><span>Academic bilingual editor</span></span></button>
      </div>
      <div class="topbar-center">
        <button :class="['view-switch',{active:activeView==='workspace'}]" @click="backToWorkspace">工作台</button>
        <button :class="['view-switch',{active:activeView==='glossary'}]" @click="openGlossaryManager()">术语库</button>
        <button class="model-pill" @click="openTool('model')"><span :class="['status-dot',modelStatus.ready?'ready':modelStatus.status==='loading'?'busy':'idle']"></span><span>{{ modelLabel }}</span><span v-if="modelStatus.gpu?.available" class="pill-meta">GPU {{ modelStatus.gpu.host_device ?? 3 }}</span></button>
      </div>
      <div class="topbar-actions">
        <template v-if="activeView==='workspace'"><button class="btn ghost" @click="newParagraph">新段落</button><button class="btn primary" @click="saveParagraph">保存</button></template>
        <button v-else class="btn secondary" @click="backToWorkspace">返回工作台</button>
      </div>
    </header>

    <div v-if="activeView==='workspace'" class="body-shell">
      <aside :class="['sidebar',{open:showSidebar}]">
        <div class="sidebar-nav">
          <button :class="['nav-item',{active:activeTool==='settings'}]" @click="openTool('settings')"><span>⚙</span><b>翻译设置</b></button>
          <button :class="['nav-item',{active:activeTool==='terms'}]" @click="openTool('terms')"><span>⌘</span><b>术语库</b><em>{{ selectedTermCount }}</em></button>
          <button :class="['nav-item',{active:activeTool==='history'}]" @click="openTool('history')"><span>↺</span><b>历史记录</b><em>{{ history.length }}</em></button>
          <button :class="['nav-item',{active:activeTool==='model'}]" @click="openTool('model')"><span>◉</span><b>模型管理</b></button>
        </div>

        <div class="sidebar-content">
          <section v-if="activeTool==='settings'" class="tool-panel">
            <div class="tool-heading"><div><span class="eyebrow">TRANSLATION</span><h2>翻译设置</h2></div><button class="close-mobile" @click="showSidebar=false">×</button></div>
            <label class="field-label">模式</label>
            <select v-model="mode" class="control"><option value="paper">PaperPolish 论文模式（推荐）</option><option value="default">Default Translation</option><option value="terminology">Terminology</option><option value="style">Style</option><option value="personalization">Personalization</option><option value="delimiters">Delimiters</option><option value="structured-data-1">Structured Data 1</option><option value="structured-data-2">Structured Data 2</option></select>
            <p class="helper">{{ modeHelp }}</p>

            <div class="glossary-picker-block">
              <div class="field-label"><span>本次翻译使用术语库</span><b>{{ selectedGlossaryIds.length }}/{{ glossaryGroups.length }}</b></div>
              <div class="glossary-check-list">
                <label v-for="group in glossaryGroups" :key="group.id" class="glossary-check"><input type="checkbox" :checked="selectedGlossaryIds.includes(group.id)" @change="toggleGlossary(group.id)"/><span><strong>{{ group.name }}</strong><small>{{ glossaryTerms.filter(t=>t.groupId===group.id).length }} 个术语</small></span></label>
                <div v-if="!glossaryGroups.length" class="mini-empty">还没有术语库</div>
              </div>
              <button class="text-link" @click="openGlossaryManager()">管理术语库 →</button>
              <p class="helper">当前会向模型提供 {{ selectedTermCount }} 个术语。未勾选的术语库不会参与翻译。</p>
            </div>

            <template v-if="mode==='style'||mode==='paper'"><label class="field-label">目标英文风格</label><textarea v-model="style" class="control compact-area" /></template>
            <template v-if="mode==='personalization'"><label class="field-label">个性化规则</label><textarea v-model="preferencesText" class="control compact-area" /></template>
            <template v-if="mode==='structured-data-1'"><label class="field-label">结构类型</label><input v-model="formatType" class="control" placeholder="LaTeX / Markdown / JSON" /></template>
            <template v-if="mode==='structured-data-2'||mode==='paper'"><label class="field-label">额外背景 <span>可选</span></label><textarea v-model="backgroundText" class="control compact-area" placeholder="留空时，中译英自动使用英文原文。" /></template>
          </section>

          <section v-if="activeTool==='terms'" class="tool-panel">
            <div class="tool-heading"><div><span class="eyebrow">QUICK ADD</span><h2>快速添加术语</h2></div><button class="close-mobile" @click="showSidebar=false">×</button></div>
            <p class="helper">侧边栏只用于快速录入。完整的分组、编辑和删除请进入术语库界面。</p>
            <label class="field-label">添加到术语库</label>
            <select v-model="quickTerm.groupId" class="control"><option disabled value="">请选择术语库</option><option v-for="group in glossaryGroups" :key="group.id" :value="group.id">{{ group.name }}</option></select>
            <div class="term-form"><input v-model="quickTerm.english" class="control" placeholder="English term"/><input v-model="quickTerm.chinese" class="control" placeholder="中文对应"/><div class="inline-fields"><select v-model="quickTerm.type" class="control"><option value="locked">Locked</option><option value="preferred">Preferred</option></select><button class="btn primary" @click="addQuickTerm">添加</button></div></div>
            <button class="btn secondary wide manage-glossary-btn" @click="openGlossaryManager(quickTerm.groupId)">打开术语库管理</button>
            <div class="quick-summary"><span>术语库</span><strong>{{ glossaryGroups.length }}</strong><span>总术语</span><strong>{{ glossaryTerms.length }}</strong><span>本次启用</span><strong>{{ selectedTermCount }}</strong></div>
          </section>

          <section v-if="activeTool==='history'" class="tool-panel">
            <div class="tool-heading"><div><span class="eyebrow">HISTORY</span><h2>历史记录</h2></div><button class="close-mobile" @click="showSidebar=false">×</button></div>
            <div class="item-list history-list"><button v-for="(item,i) in history" :key="i" class="history-card" @click="loadParagraph(item)"><span>{{ (item.source||item.chinese||'空段落').slice(0,100) }}</span><small>{{ new Date(item.savedAt).toLocaleString() }}</small></button><div v-if="!history.length" class="empty-state">保存过的段落会出现在这里。</div></div>
          </section>

          <section v-if="activeTool==='model'" class="tool-panel">
            <div class="tool-heading"><div><span class="eyebrow">RUNTIME</span><h2>模型管理</h2></div><button class="close-mobile" @click="showSidebar=false">×</button></div>
            <div class="model-hero"><div class="model-hero-row"><div class="model-icon">H</div><div><strong>{{ modelStatus.model }}</strong><span>{{ modelStatus.downloaded?'本地权重已就绪':'本地尚无权重' }}</span></div></div><span :class="['runtime-badge',{ready:modelStatus.ready}]">{{ modelStatus.ready?'READY':'IDLE' }}</span></div>
            <div v-if="modelStatus.gpu?.available" class="gpu-card"><div class="gpu-title"><div><span>GPU {{ modelStatus.gpu.host_device ?? 3 }}</span><strong>{{ modelStatus.gpu.name }}</strong></div><b>{{ gpuPercent.toFixed(0) }}%</b></div><div class="memory-track"><div class="memory-fill" :style="{width:`${gpuPercent}%`}"></div></div><div class="gpu-stats"><span>已用 {{ formatMb(modelStatus.gpu.used_mb) }}</span><span>总计 {{ formatMb(modelStatus.gpu.total_mb) }}</span></div></div>
            <div v-if="modelStatus.lastError" class="notice error">{{ modelStatus.lastError }}</div><div v-if="!modelStatus.gpu?.available" class="notice warning">未检测到可用 CUDA GPU。</div>
            <div class="stack-actions"><button class="btn primary wide" :disabled="modelStatus.ready||modelAction" @click="manageModel('load')">{{ modelAction==='load'?(modelStatus.downloaded?'加载中…':'下载并加载中…'):(modelStatus.downloaded?'加载模型':'下载并加载') }}</button><button class="btn secondary wide" :disabled="!modelStatus.ready||modelAction||loading" @click="manageModel('unload')">{{ modelAction==='unload'?'卸载中…':'卸载模型' }}</button><button class="btn ghost wide" :disabled="modelAction" @click="checkHealth">刷新状态</button></div>
          </section>
        </div>
      </aside>

      <main class="workspace-page">
        <div class="workspace-intro"><div><span class="eyebrow">PARAGRAPH WORKSPACE</span><h1>把意思改对，再让英文变好。</h1><p>原文负责语义锚定，中文负责表达你的真实意图，最终英文负责学术写作质量。</p></div><div class="workflow-status"><span :class="{done:source}">原文</span><i></i><span :class="{done:chinese}">中文</span><i></i><span :class="{done:finalEnglish}">英文</span></div></div>
        <div class="mobile-stage-tabs"><button :class="{active:activeStage==='source'}" @click="activeStage='source'">英文原文</button><button :class="{active:activeStage==='chinese'}" @click="activeStage='chinese'">中文修改</button><button :class="{active:activeStage==='final'}" @click="activeStage='final'">最终英文</button></div>
        <section class="editor-grid">
          <article :class="['editor-card',{mobileHidden:activeStage!=='source'}]"><div class="editor-topline"><div><span class="stage-number">01</span><span><strong>英文原文</strong><small>Meaning anchor</small></span></div><button class="text-action" @click="copy(source)">复制</button></div><textarea v-model="source" placeholder="粘贴需要润色的英文论文段落…"></textarea><div class="editor-bottom"><span>{{ sourceWords }} words</span><button class="btn primary action-button" :disabled="loading||modelAction" @click="callApi('en-zh')">{{ loading==='en-zh'?'翻译中…':'翻译为中文' }} <b>→</b></button></div></article>
          <article :class="['editor-card','chinese-card',{mobileHidden:activeStage!=='chinese'}]"><div class="editor-topline"><div><span class="stage-number">02</span><span><strong>中文修改</strong><small>Your intended meaning</small></span></div><button class="text-action" @click="copy(chinese)">复制</button></div><textarea v-model="chinese" placeholder="先确保中文准确表达你的真实意图，再生成最终英文。"></textarea><div class="editor-bottom"><span>{{ chineseChars }} 字</span><button class="btn primary action-button" :disabled="loading||modelAction" @click="callApi('zh-en')">{{ loading==='zh-en'?'生成中…':'生成学术英文' }} <b>→</b></button></div></article>
          <article :class="['editor-card',{mobileHidden:activeStage!=='final'}]"><div class="editor-topline"><div><span class="stage-number">03</span><span><strong>最终英文</strong><small>Academic output</small></span></div><button class="text-action" @click="copy(finalEnglish)">复制</button></div><textarea v-model="finalEnglish" placeholder="最终学术英文会出现在这里…"></textarea><div class="editor-bottom"><span>{{ finalWords }} words</span><button class="btn secondary action-button" :disabled="loading||modelAction" @click="callApi('zh-en')">重新生成</button></div></article>
        </section>
        <div class="workspace-hint"><span>◆</span><p>本次翻译已启用 <strong>{{ selectedGlossaryIds.length }}</strong> 个术语库，共 <strong>{{ selectedTermCount }}</strong> 个术语。<button class="inline-link" @click="openTool('settings')">修改选择</button></p></div>
      </main>
    </div>

    <main v-else class="glossary-page">
      <div class="glossary-page-head"><div><span class="eyebrow">GLOSSARY LIBRARY</span><h1>术语库</h1><p>按论文、项目或研究方向组织术语。翻译时可以自由组合启用多个术语库。</p></div><div class="glossary-page-stats"><div><strong>{{ glossaryGroups.length }}</strong><span>术语库</span></div><div><strong>{{ glossaryTerms.length }}</strong><span>术语</span></div><div><strong>{{ selectedGlossaryIds.length }}</strong><span>当前启用</span></div></div></div>
      <div class="glossary-layout">
        <aside class="glossary-groups-panel">
          <div class="panel-section-title"><strong>所有术语库</strong><span>{{ glossaryGroups.length }}</span></div>
          <div class="group-list"><button v-for="group in glossaryGroups" :key="group.id" :class="['group-card',{active:selectedGroupId===group.id}]" @click="selectGroup(group.id)"><span class="group-icon">Aa</span><span class="group-copy"><strong>{{ group.name }}</strong><small>{{ glossaryTerms.filter(t=>t.groupId===group.id).length }} 个术语</small></span><span v-if="selectedGlossaryIds.includes(group.id)" class="enabled-dot"></span></button></div>
          <div class="new-group-card"><label class="field-label">新建术语库</label><input v-model="newGroup.name" class="control" placeholder="例如：3DGS / Active Mapping"/><textarea v-model="newGroup.description" class="control mini-area" placeholder="可选说明"></textarea><button class="btn primary wide" @click="createGroup">创建术语库</button></div>
        </aside>

        <section v-if="selectedGroup" class="glossary-detail">
          <div class="glossary-detail-head">
            <div class="group-title-block"><div class="large-group-icon">Aa</div><div><input v-model="groupEditor.name" class="title-input"/><input v-model="groupEditor.description" class="description-input" placeholder="添加这个术语库的说明…"/></div></div>
            <div class="group-actions"><label class="enable-switch"><input type="checkbox" :checked="selectedGlossaryIds.includes(selectedGroup.id)" @change="toggleGlossary(selectedGroup.id)"/><span></span><b>{{ selectedGlossaryIds.includes(selectedGroup.id)?'参与翻译':'不参与翻译' }}</b></label><button class="btn secondary" @click="saveGroup">保存信息</button><button class="btn danger-ghost" @click="requestDeleteGroup">删除术语库</button></div>
          </div>
          <div v-if="pendingDeleteGroupId===selectedGroup.id" class="delete-confirm"><span>删除后，该组内 {{ selectedGroupTerms.length }} 个术语也会一起删除。</span><div><button class="btn ghost" @click="cancelDeleteGroup">取消</button><button class="btn danger" @click="confirmDeleteGroup">确认删除</button></div></div>

          <div class="add-term-bar"><input v-model="managerTerm.english" class="control" placeholder="English term"/><input v-model="managerTerm.chinese" class="control" placeholder="中文对应"/><select v-model="managerTerm.type" class="control"><option value="locked">Locked</option><option value="preferred">Preferred</option></select><button class="btn primary" @click="addManagerTerm">添加术语</button></div>

          <div class="terms-table-wrap">
            <table class="terms-table"><thead><tr><th>英文术语</th><th>中文对应</th><th>类型</th><th class="actions-col">操作</th></tr></thead><tbody>
              <tr v-for="term in selectedGroupTerms" :key="term.id">
                <template v-if="editingTermId===term.id"><td><input v-model="editingTerm.english" class="table-input"/></td><td><input v-model="editingTerm.chinese" class="table-input"/></td><td><select v-model="editingTerm.type" class="table-input"><option value="locked">Locked</option><option value="preferred">Preferred</option></select></td><td class="row-actions"><button class="mini-action primary-text" @click="saveTermEdit(term)">保存</button><button class="mini-action" @click="cancelEditTerm">取消</button></td></template>
                <template v-else><td><strong>{{ term.english||'—' }}</strong></td><td>{{ term.chinese||'—' }}</td><td><span :class="['term-type-badge',term.type]">{{ term.type }}</span></td><td class="row-actions"><button class="mini-action" @click="startEditTerm(term)">编辑</button><button class="mini-action danger-text" @click="deleteTerm(term.id)">删除</button></td></template>
              </tr>
              <tr v-if="!selectedGroupTerms.length"><td colspan="4"><div class="table-empty">这个术语库还是空的。可以从上方添加第一条术语。</div></td></tr>
            </tbody></table>
          </div>
        </section>
        <section v-else class="no-group-selected"><div class="large-group-icon">Aa</div><h2>创建第一个术语库</h2><p>术语必须归属某个术语库。可以按论文、项目、领域或数据集来分组。</p></section>
      </div>
    </main>

    <div v-if="showSidebar&&activeView==='workspace'" class="sidebar-backdrop" @click="showSidebar=false"></div>
    <transition name="toast"><div v-if="toast.show" :class="['toast',toast.type]">{{ toast.message }}</div></transition>
  </div>
</template>
