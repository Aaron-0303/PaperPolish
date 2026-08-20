<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

const activeView = ref(localStorage.getItem('paperpolish_active_view_v1') || 'polish')
const activeTool = ref('settings')
const showSidebar = ref(false)
const activeStage = ref('source')
const draftStage = ref('chinese')
const loading = ref('')
const modelAction = ref('')

const source = ref('')
const chinese = ref('')
const finalEnglish = ref('')
const draftChinese = ref('')
const draftEnglish = ref('')

const mode = ref(localStorage.getItem('paperpolish_mode_v1') || 'paper')
const formatType = ref(localStorage.getItem('paperpolish_format_v1') || 'LaTeX')
const preferencesText = ref(localStorage.getItem('paperpolish_preferences_v1') || 'Preserve technical meaning\nUse concise academic wording\nDo not expand claims')
const backgroundText = ref(localStorage.getItem('paperpolish_background_v1') || '')
const style = ref(localStorage.getItem('paperpolish_style_v2') || 'CVPR/IEEE concise academic style')
const history = ref(JSON.parse(localStorage.getItem('paperpolish_history_v3') || localStorage.getItem('paperpolish_history_v2') || '[]'))

const finalEngine = ref(localStorage.getItem('paperpolish_final_engine_v1') || 'local')
const remoteApiKey = ref(localStorage.getItem('paperpolish_remote_api_key_v1') || '')
const remoteModel = ref(localStorage.getItem('paperpolish_remote_model_v1') || '')
const remoteModels = ref([])
const remoteModelsLoading = ref(false)
const showApiKey = ref(false)

const toast = reactive({show:false,message:'',type:'info'})
let toastTimer
const modelStatus = reactive({ready:false,model:'tencent/Hy-MT2-7B',status:'checking',downloaded:false,dtype:'bfloat16',lastLoadSeconds:null,lastError:'',gpu:null})

const glossaryGroups = ref([])
const glossaryTerms = ref([])
const selectedGlossaryIds = ref([])
const selectedGroupId = ref('')
const quickTerm = reactive({english:'',chinese:'',type:'locked',groupId:''})
const managerTerm = reactive({english:'',chinese:'',type:'locked'})
const newGroup = reactive({name:'',description:''})
const groupEditor = reactive({name:'',description:''})
const editingTermId = ref('')
const editingTerm = reactive({english:'',chinese:'',type:'locked'})
const pendingDeleteGroupId = ref('')

const sourceWords = computed(()=>source.value.trim()?source.value.trim().split(/\s+/).length:0)
const finalWords = computed(()=>finalEnglish.value.trim()?finalEnglish.value.trim().split(/\s+/).length:0)
const chineseChars = computed(()=>chinese.value.replace(/\s/g,'').length)
const draftChineseChars = computed(()=>draftChinese.value.replace(/\s/g,'').length)
const draftEnglishWords = computed(()=>draftEnglish.value.trim()?draftEnglish.value.trim().split(/\s+/).length:0)
const activeTerms = computed(()=>glossaryTerms.value.filter(t=>selectedGlossaryIds.value.includes(t.groupId)))
const selectedTermCount = computed(()=>activeTerms.value.length)
const selectedGroup = computed(()=>glossaryGroups.value.find(g=>g.id===selectedGroupId.value)||null)
const selectedGroupTerms = computed(()=>glossaryTerms.value.filter(t=>t.groupId===selectedGroupId.value))
const finalEngineLabel = computed(()=>finalEngine.value==='remote'?(remoteModel.value||'API'):'Hy-MT2-7B')
const modelLabel = computed(()=>modelStatus.status==='offline'?'后端离线':modelStatus.status==='loading'?'模型加载中':modelStatus.ready?'模型已就绪':'模型未加载')
const gpuPercent = computed(()=>modelStatus.gpu?.available&&modelStatus.gpu.total_mb?Math.min(100,Math.max(0,modelStatus.gpu.used_mb/modelStatus.gpu.total_mb*100)):0)
const currentHistory = computed(()=>history.value.filter(item=>(item.workflow||'polish')===activeView.value))
const modeHelp = computed(()=>({paper:'术语、论文风格、背景信息和 LaTeX 保护同时生效。',default:'仅执行标准翻译。',terminology:'重点使用当前启用术语库中的固定译法。',style:'重点控制目标英文写作风格。',personalization:'按自定义规则约束翻译。',delimiters:'强化保护占位符和分隔符。','structured-data-1':'适合 LaTeX / Markdown / JSON。','structured-data-2':'使用背景信息辅助翻译。'}[mode.value]))

watch(activeView,v=>{ if(v!=='glossary') localStorage.setItem('paperpolish_active_view_v1',v) })
watch([source,chinese,finalEnglish],()=>localStorage.setItem('paperpolish_polish_draft_v1',JSON.stringify({source:source.value,chinese:chinese.value,finalEnglish:finalEnglish.value})))
watch([draftChinese,draftEnglish],()=>localStorage.setItem('paperpolish_writing_draft_v1',JSON.stringify({chinese:draftChinese.value,english:draftEnglish.value})))
watch(history,v=>localStorage.setItem('paperpolish_history_v3',JSON.stringify(v)),{deep:true})
watch(style,v=>localStorage.setItem('paperpolish_style_v2',v))
watch(mode,v=>localStorage.setItem('paperpolish_mode_v1',v))
watch(formatType,v=>localStorage.setItem('paperpolish_format_v1',v))
watch(preferencesText,v=>localStorage.setItem('paperpolish_preferences_v1',v))
watch(backgroundText,v=>localStorage.setItem('paperpolish_background_v1',v))
watch(finalEngine,v=>localStorage.setItem('paperpolish_final_engine_v1',v))
watch(remoteApiKey,v=>localStorage.setItem('paperpolish_remote_api_key_v1',v))
watch(remoteModel,v=>localStorage.setItem('paperpolish_remote_model_v1',v))
watch(glossaryGroups,v=>localStorage.setItem('paperpolish_glossary_groups_v3',JSON.stringify(v)),{deep:true})
watch(glossaryTerms,v=>localStorage.setItem('paperpolish_glossary_terms_v3',JSON.stringify(v)),{deep:true})
watch(selectedGlossaryIds,v=>localStorage.setItem('paperpolish_selected_glossaries_v3',JSON.stringify(v)),{deep:true})

function makeId(prefix='id'){return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,8)}`}
function notify(message,type='info'){clearTimeout(toastTimer);toast.message=message;toast.type=type;toast.show=true;toastTimer=setTimeout(()=>toast.show=false,2600)}
function switchView(view){activeView.value=view;showSidebar.value=false;if(view==='polish')activeStage.value='source';if(view==='draft')draftStage.value='chinese'}
function openTool(tool){activeTool.value=tool;showSidebar.value=true}
function formatMb(v){if(v==null)return'—';return v>=1024?`${(v/1024).toFixed(1)} GB`:`${Math.round(v)} MB`}

function initializeGlossaries(){
  const groups=JSON.parse(localStorage.getItem('paperpolish_glossary_groups_v3')||'[]')
  const terms=JSON.parse(localStorage.getItem('paperpolish_glossary_terms_v3')||'[]')
  if(groups.length){glossaryGroups.value=groups;glossaryTerms.value=terms}else{
    const legacy=JSON.parse(localStorage.getItem('paperpolish_terms_v2')||'[]');const id='glossary_default'
    glossaryGroups.value=[{id,name:'默认术语库',description:'从旧版术语自动迁移，可继续分类。'}]
    glossaryTerms.value=legacy.map(t=>({id:makeId('term'),groupId:id,english:t.english||'',chinese:t.chinese||'',type:t.type||'preferred'}))
  }
  const validIds=glossaryGroups.value.map(g=>g.id)
  const stored=JSON.parse(localStorage.getItem('paperpolish_selected_glossaries_v3')||'[]')
  selectedGlossaryIds.value=stored.length?stored.filter(id=>validIds.includes(id)):[...validIds]
  selectedGroupId.value=validIds[0]||'';quickTerm.groupId=validIds[0]||'';syncGroupEditor()
}
function syncGroupEditor(){const g=selectedGroup.value;groupEditor.name=g?.name||'';groupEditor.description=g?.description||'';editingTermId.value='';pendingDeleteGroupId.value=''}
function selectGroup(id){selectedGroupId.value=id;syncGroupEditor()}
function toggleGlossary(id){selectedGlossaryIds.value=selectedGlossaryIds.value.includes(id)?selectedGlossaryIds.value.filter(v=>v!==id):[...selectedGlossaryIds.value,id]}
function createGroup(){const name=newGroup.name.trim();if(!name)return notify('请输入术语库名称','warning');const id=makeId('glossary');glossaryGroups.value.push({id,name,description:newGroup.description.trim()});selectedGlossaryIds.value.push(id);selectedGroupId.value=id;quickTerm.groupId=id;newGroup.name='';newGroup.description='';syncGroupEditor();notify('术语库已创建','success')}
function saveGroup(){const g=selectedGroup.value;if(!g)return;const name=groupEditor.name.trim();if(!name)return notify('术语库名称不能为空','warning');g.name=name;g.description=groupEditor.description.trim();notify('术语库信息已更新','success')}
function confirmDeleteGroup(){const id=pendingDeleteGroupId.value;if(!id)return;glossaryGroups.value=glossaryGroups.value.filter(g=>g.id!==id);glossaryTerms.value=glossaryTerms.value.filter(t=>t.groupId!==id);selectedGlossaryIds.value=selectedGlossaryIds.value.filter(v=>v!==id);selectedGroupId.value=glossaryGroups.value[0]?.id||'';quickTerm.groupId=selectedGroupId.value;syncGroupEditor();notify('术语库已删除','success')}
function addQuickTerm(){if(!quickTerm.groupId)return notify('请先创建术语库','warning');if(!quickTerm.english.trim()&&!quickTerm.chinese.trim())return notify('请输入术语内容','warning');glossaryTerms.value.push({id:makeId('term'),groupId:quickTerm.groupId,english:quickTerm.english.trim(),chinese:quickTerm.chinese.trim(),type:quickTerm.type});quickTerm.english='';quickTerm.chinese='';notify('术语已添加','success')}
function addManagerTerm(){if(!selectedGroupId.value)return;if(!managerTerm.english.trim()&&!managerTerm.chinese.trim())return notify('请输入术语内容','warning');glossaryTerms.value.push({id:makeId('term'),groupId:selectedGroupId.value,english:managerTerm.english.trim(),chinese:managerTerm.chinese.trim(),type:managerTerm.type});managerTerm.english='';managerTerm.chinese='';notify('术语已添加','success')}
function startEditTerm(term){editingTermId.value=term.id;editingTerm.english=term.english;editingTerm.chinese=term.chinese;editingTerm.type=term.type}
function saveTermEdit(term){term.english=editingTerm.english.trim();term.chinese=editingTerm.chinese.trim();term.type=editingTerm.type;editingTermId.value='';notify('术语已更新','success')}
function deleteTerm(id){glossaryTerms.value=glossaryTerms.value.filter(t=>t.id!==id);notify('术语已删除','success')}

async function checkHealth(){try{const r=await fetch('/api/model/status');const d=await r.json();if(!r.ok)throw new Error();Object.assign(modelStatus,{ready:!!d.model_ready,model:d.model||'tencent/Hy-MT2-7B',status:d.status||'unknown',downloaded:!!d.downloaded,dtype:d.dtype||'bfloat16',lastLoadSeconds:d.last_load_seconds??null,lastError:d.last_error||'',gpu:d.gpu||null})}catch{modelStatus.ready=false;modelStatus.status='offline';modelStatus.lastError='无法连接后端服务'}}
async function manageModel(action){modelAction.value=action;try{const r=await fetch(`/api/model/${action}`,{method:'POST'});const d=await r.json();if(!r.ok)throw new Error(d.detail||'模型操作失败');await checkHealth();notify(action==='load'?'模型加载完成':'模型已卸载','success')}catch(e){notify(e.message,'error');await checkHealth()}finally{modelAction.value=''}}
async function fetchRemoteModels(){if(!remoteApiKey.value.trim())return notify('请先填写 API Key','warning');remoteModelsLoading.value=true;try{const r=await fetch('/api/remote/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({api_key:remoteApiKey.value.trim()})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'获取模型失败');remoteModels.value=d.models||[];if(!remoteModel.value&&remoteModels.value.length)remoteModel.value=remoteModels.value[0];notify(`已获取 ${remoteModels.value.length} 个可用模型`,'success')}catch(e){notify(e.message,'error')}finally{remoteModelsLoading.value=false}}

async function generateEnglish(text,originalEnglish=''){
  const useRemote=finalEngine.value==='remote'
  if(useRemote){if(!remoteApiKey.value.trim()){openTool('settings');throw new Error('请先填写 API Key')}if(!remoteModel.value.trim()){openTool('settings');throw new Error('请选择或填写 API 模型')}
    return fetch('/api/remote/polish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,api_key:remoteApiKey.value.trim(),model:remoteModel.value.trim(),original_english:originalEnglish,style:style.value,terms:activeTerms.value.map(({english,chinese,type})=>({english,chinese,type}))})})
  }
  if(!modelStatus.ready){openTool('model');throw new Error('请先加载 Hy-MT2-7B 模型')}
  return fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,direction:'zh-en',mode:mode.value,terms:activeTerms.value.map(({english,chinese,type})=>({english,chinese,type})),original_english:originalEnglish,style:style.value,preferences:preferencesText.value.split('\n').map(v=>v.trim()).filter(Boolean),format_type:formatType.value,background_text:backgroundText.value})})
}
async function translateToChinese(){if(!source.value.trim())return notify('先粘贴英文原文','warning');if(!modelStatus.ready){openTool('model');return notify('请先加载 Hy-MT2-7B 模型','warning')}loading.value='en-zh';try{const r=await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:source.value.trim(),direction:'en-zh',mode:mode.value,terms:activeTerms.value.map(({english,chinese,type})=>({english,chinese,type})),original_english:source.value,style:style.value,preferences:preferencesText.value.split('\n').map(v=>v.trim()).filter(Boolean),format_type:formatType.value,background_text:backgroundText.value})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'请求失败');chinese.value=d.result;activeStage.value='chinese';notify('中文初稿已生成','success')}catch(e){notify(e.message,'error')}finally{loading.value=''}}
async function generatePolishedEnglish(){if(!chinese.value.trim())return notify('先完成中文修改','warning');loading.value='zh-en';try{const r=await generateEnglish(chinese.value.trim(),source.value);const d=await r.json();if(!r.ok)throw new Error(d.detail||'请求失败');finalEnglish.value=d.result;activeStage.value='final';notify(`已通过 ${finalEngineLabel.value} 生成学术英文`,'success')}catch(e){notify(e.message,'error')}finally{loading.value=''}}
async function generateDraftEnglish(){if(!draftChinese.value.trim())return notify('先输入中文初稿','warning');loading.value='draft-en';try{const r=await generateEnglish(draftChinese.value.trim(),'');const d=await r.json();if(!r.ok)throw new Error(d.detail||'请求失败');draftEnglish.value=d.result;draftStage.value='english';notify(`已通过 ${finalEngineLabel.value} 生成英文初稿`,'success')}catch(e){notify(e.message,'error')}finally{loading.value=''}}

function saveCurrent(){if(activeView.value==='polish'){if(!source.value&&!chinese.value&&!finalEnglish.value)return notify('当前没有可保存内容','warning');history.value.unshift({workflow:'polish',source:source.value,chinese:chinese.value,finalEnglish:finalEnglish.value,savedAt:new Date().toISOString()})}else if(activeView.value==='draft'){if(!draftChinese.value&&!draftEnglish.value)return notify('当前没有可保存内容','warning');history.value.unshift({workflow:'draft',chinese:draftChinese.value,finalEnglish:draftEnglish.value,savedAt:new Date().toISOString()})}history.value=history.value.slice(0,100);notify('已保存到历史记录','success')}
function newCurrent(){if(activeView.value==='polish'){source.value='';chinese.value='';finalEnglish.value='';activeStage.value='source'}else{draftChinese.value='';draftEnglish.value='';draftStage.value='chinese'}}
function loadHistory(item){if((item.workflow||'polish')==='draft'){switchView('draft');draftChinese.value=item.chinese||'';draftEnglish.value=item.finalEnglish||''}else{switchView('polish');source.value=item.source||'';chinese.value=item.chinese||'';finalEnglish.value=item.finalEnglish||''}notify('已载入历史内容')}
async function copy(text){if(!text)return;await navigator.clipboard.writeText(text);notify('已复制到剪贴板','success')}

onMounted(()=>{
  const old=JSON.parse(localStorage.getItem('paperpolish_draft_v2')||'{}')
  const polish=JSON.parse(localStorage.getItem('paperpolish_polish_draft_v1')||'{}')
  const writing=JSON.parse(localStorage.getItem('paperpolish_writing_draft_v1')||'{}')
  source.value=polish.source??old.source??'';chinese.value=polish.chinese??old.chinese??'';finalEnglish.value=polish.finalEnglish??old.finalEnglish??''
  draftChinese.value=writing.chinese||'';draftEnglish.value=writing.english||''
  initializeGlossaries();checkHealth()
})
</script>

<template>
<div class="app-shell">
  <header class="topbar">
    <div class="topbar-left"><button class="mobile-menu" @click="showSidebar=!showSidebar">☰</button><button class="brand-button" @click="switchView('polish')"><span class="brand-mark">P</span><span class="brand-lockup"><strong>PaperPolish</strong><span>Academic bilingual editor</span></span></button></div>
    <nav class="topbar-center workflow-nav">
      <button :class="['view-switch',{active:activeView==='polish'}]" @click="switchView('polish')"><span>论文润色</span><small>EN · 中 · EN</small></button>
      <button :class="['view-switch',{active:activeView==='draft'}]" @click="switchView('draft')"><span>英文初稿</span><small>中 · EN</small></button>
      <button :class="['view-switch',{active:activeView==='glossary'}]" @click="switchView('glossary')"><span>术语库</span></button>
      <button class="model-pill" @click="openTool('model')"><span :class="['status-dot',modelStatus.ready?'ready':modelStatus.status==='loading'?'busy':'idle']"></span><span>{{ modelLabel }}</span><span v-if="modelStatus.gpu?.available" class="pill-meta">GPU {{ modelStatus.gpu.host_device ?? 3 }}</span></button>
    </nav>
    <div class="topbar-actions"><template v-if="activeView!=='glossary'"><button class="btn ghost" @click="newCurrent">新建</button><button class="btn primary" @click="saveCurrent">保存</button></template><button v-else class="btn secondary" @click="switchView('polish')">返回润色</button></div>
  </header>

  <div v-if="activeView!=='glossary'" class="body-shell">
    <aside :class="['sidebar',{open:showSidebar}]">
      <div class="sidebar-nav">
        <button :class="['nav-item',{active:activeTool==='settings'}]" @click="openTool('settings')"><span>⚙</span><b>生成设置</b></button>
        <button :class="['nav-item',{active:activeTool==='terms'}]" @click="openTool('terms')"><span>⌘</span><b>术语库</b><em>{{ selectedTermCount }}</em></button>
        <button :class="['nav-item',{active:activeTool==='history'}]" @click="openTool('history')"><span>↺</span><b>历史记录</b><em>{{ currentHistory.length }}</em></button>
        <button :class="['nav-item',{active:activeTool==='model'}]" @click="openTool('model')"><span>◉</span><b>模型管理</b></button>
      </div>
      <div class="sidebar-content">
        <section v-if="activeTool==='settings'" class="tool-panel">
          <div class="tool-heading"><div><span class="eyebrow">GENERATION</span><h2>生成设置</h2></div><button class="close-mobile" @click="showSidebar=false">×</button></div>
          <div class="engine-settings-card"><div class="engine-settings-head"><div><span class="field-kicker">ENGLISH ENGINE</span><strong>英文生成引擎</strong></div><span class="engine-current">{{ finalEngineLabel }}</span></div><div class="engine-switch"><button :class="{active:finalEngine==='local'}" @click="finalEngine='local'"><b>本地</b><small>Hy-MT2-7B</small></button><button :class="{active:finalEngine==='remote'}" @click="finalEngine='remote'"><b>API</b><small>api.gpt.ge</small></button></div>
            <div v-if="finalEngine==='remote'" class="remote-settings"><label class="field-label">API Key <span>当前浏览器</span></label><div class="secret-input-wrap"><input v-model="remoteApiKey" :type="showApiKey?'text':'password'" class="control" autocomplete="off" placeholder="sk-..."/><button @click="showApiKey=!showApiKey">{{ showApiKey?'隐藏':'显示' }}</button></div><label class="field-label">模型</label><input v-model="remoteModel" list="remote-model-options" class="control" placeholder="填写或获取模型"/><datalist id="remote-model-options"><option v-for="item in remoteModels" :key="item" :value="item"/></datalist><button class="btn secondary wide fetch-models-btn" :disabled="remoteModelsLoading" @click="fetchRemoteModels">{{ remoteModelsLoading?'读取中…':'从 API Key 获取模型' }}</button></div>
          </div>
          <label class="field-label">Hy-MT2 翻译模式</label><select v-model="mode" class="control"><option value="paper">PaperPolish 论文模式（推荐）</option><option value="default">Default Translation</option><option value="terminology">Terminology</option><option value="style">Style</option><option value="personalization">Personalization</option><option value="delimiters">Delimiters</option><option value="structured-data-1">Structured Data 1</option><option value="structured-data-2">Structured Data 2</option></select><p class="helper">{{ modeHelp }}</p>
          <div class="glossary-picker-block"><div class="field-label"><span>使用术语库</span><b>{{ selectedGlossaryIds.length }}/{{ glossaryGroups.length }}</b></div><div class="glossary-check-list"><label v-for="group in glossaryGroups" :key="group.id" class="glossary-check"><input type="checkbox" :checked="selectedGlossaryIds.includes(group.id)" @change="toggleGlossary(group.id)"/><span><strong>{{ group.name }}</strong><small>{{ glossaryTerms.filter(t=>t.groupId===group.id).length }} 个</small></span></label></div></div>
          <template v-if="mode==='style'||mode==='paper'"><label class="field-label">目标英文风格</label><textarea v-model="style" class="control compact-area"/></template><template v-if="mode==='personalization'"><label class="field-label">个性化规则</label><textarea v-model="preferencesText" class="control compact-area"/></template><template v-if="mode==='structured-data-1'"><label class="field-label">结构类型</label><input v-model="formatType" class="control"/></template><template v-if="mode==='structured-data-2'||mode==='paper'"><label class="field-label">额外背景</label><textarea v-model="backgroundText" class="control compact-area"/></template>
        </section>

        <section v-if="activeTool==='terms'" class="tool-panel quick-add-panel"><div class="quick-add-heading"><div><span class="eyebrow">QUICK ADD</span><h2>快速添加术语</h2><p>快速录入到已有术语库。</p></div></div><div class="quick-add-card"><label>目标术语库</label><select v-model="quickTerm.groupId" class="control"><option disabled value="">请选择术语库</option><option v-for="group in glossaryGroups" :key="group.id" :value="group.id">{{ group.name }}</option></select><div class="quick-language-row"><input v-model="quickTerm.english" class="control" placeholder="English term"/><input v-model="quickTerm.chinese" class="control" placeholder="中文对应"/></div><div class="quick-action-row"><select v-model="quickTerm.type" class="control"><option value="locked">Locked</option><option value="preferred">Preferred</option></select><button class="btn primary" @click="addQuickTerm">添加</button></div></div><button class="quick-manage-link" @click="switchView('glossary')"><span>管理全部术语库</span><b>→</b></button></section>

        <section v-if="activeTool==='history'" class="tool-panel"><div class="tool-heading"><div><span class="eyebrow">HISTORY</span><h2>{{ activeView==='polish'?'润色历史':'初稿历史' }}</h2></div></div><div class="item-list history-list"><button v-for="(item,i) in currentHistory" :key="i" class="history-card" @click="loadHistory(item)"><span>{{ (item.source||item.chinese||'空内容').slice(0,100) }}</span><small>{{ new Date(item.savedAt).toLocaleString() }}</small></button><div v-if="!currentHistory.length" class="empty-state">还没有保存记录。</div></div></section>

        <section v-if="activeTool==='model'" class="tool-panel"><div class="tool-heading"><div><span class="eyebrow">RUNTIME</span><h2>模型管理</h2></div></div><div class="model-hero"><div class="model-hero-row"><div class="model-icon">H</div><div><strong>{{ modelStatus.model }}</strong><span>{{ modelStatus.downloaded?'本地权重已就绪':'本地尚无权重' }}</span></div></div><span :class="['runtime-badge',{ready:modelStatus.ready}]">{{ modelStatus.ready?'READY':'IDLE' }}</span></div><div v-if="modelStatus.gpu?.available" class="gpu-card"><div class="gpu-title"><div><span>GPU {{ modelStatus.gpu.host_device ?? 3 }}</span><strong>{{ modelStatus.gpu.name }}</strong></div><b>{{ gpuPercent.toFixed(0) }}%</b></div><div class="memory-track"><div class="memory-fill" :style="{width:`${gpuPercent}%`}"></div></div><div class="gpu-stats"><span>{{ formatMb(modelStatus.gpu.used_mb) }} 已用</span><span>{{ formatMb(modelStatus.gpu.total_mb) }} 总计</span></div></div><div v-if="modelStatus.lastError" class="notice error">{{ modelStatus.lastError }}</div><div class="stack-actions"><button class="btn primary wide" :disabled="modelStatus.ready||modelAction" @click="manageModel('load')">{{ modelAction==='load'?'加载中…':modelStatus.downloaded?'加载模型':'下载并加载' }}</button><button class="btn secondary wide" :disabled="!modelStatus.ready||modelAction" @click="manageModel('unload')">卸载模型</button><button class="btn ghost wide" @click="checkHealth">刷新状态</button></div></section>
      </div>
    </aside>

    <main v-if="activeView==='polish'" class="workspace-page polish-workspace">
      <div class="workspace-intro"><div><span class="eyebrow">POLISH WORKSPACE</span><h1>论文润色</h1><p>保留原始英文作为语义锚点，先把中文意思改准确，再生成更好的学术英文。</p></div><div class="workflow-status"><span :class="{done:source}">原文</span><i></i><span :class="{done:chinese}">中文</span><i></i><span :class="{done:finalEnglish}">英文</span></div></div>
      <div class="mobile-stage-tabs"><button :class="{active:activeStage==='source'}" @click="activeStage='source'">英文原文</button><button :class="{active:activeStage==='chinese'}" @click="activeStage='chinese'">中文修改</button><button :class="{active:activeStage==='final'}" @click="activeStage='final'">最终英文</button></div>
      <section class="editor-grid"><article :class="['editor-card',{mobileHidden:activeStage!=='source'}]"><div class="editor-topline"><div><span class="stage-number">01</span><span><strong>英文原文</strong><small>Meaning anchor</small></span></div><button class="text-action" @click="copy(source)">复制</button></div><textarea v-model="source" placeholder="粘贴需要润色的英文论文段落…"></textarea><div class="editor-bottom"><span>{{ sourceWords }} words</span><button class="btn primary action-button" :disabled="loading||modelAction" @click="translateToChinese">{{ loading==='en-zh'?'翻译中…':'翻译为中文' }} <b>→</b></button></div></article><article :class="['editor-card','chinese-card',{mobileHidden:activeStage!=='chinese'}]"><div class="editor-topline"><div><span class="stage-number">02</span><span><strong>中文修改</strong><small>Your intended meaning</small></span></div><button class="text-action" @click="copy(chinese)">复制</button></div><textarea v-model="chinese" placeholder="修改中文，确保准确表达你真正想说的内容。"></textarea><div class="editor-bottom"><span>{{ chineseChars }} 字</span><button class="btn primary action-button" :disabled="loading||modelAction" @click="generatePolishedEnglish">{{ loading==='zh-en'?'生成中…':'生成学术英文' }} <b>→</b></button></div></article><article :class="['editor-card',{mobileHidden:activeStage!=='final'}]"><div class="editor-topline"><div><span class="stage-number">03</span><span><strong>最终英文</strong><small>{{ finalEngineLabel }}</small></span></div><button class="text-action" @click="copy(finalEnglish)">复制</button></div><textarea v-model="finalEnglish" placeholder="最终学术英文会出现在这里…"></textarea><div class="editor-bottom"><span>{{ finalWords }} words</span><button class="btn secondary action-button" :disabled="loading" @click="generatePolishedEnglish">重新生成</button></div></article></section>
      <div class="workspace-hint"><span>◆</span><p>已启用 <strong>{{ selectedGlossaryIds.length }}</strong> 个术语库、<strong>{{ selectedTermCount }}</strong> 个术语；英文生成使用 <strong>{{ finalEngineLabel }}</strong>。</p></div>
    </main>

    <main v-else class="workspace-page draft-workspace">
      <div class="workspace-intro"><div><span class="eyebrow">DRAFT WORKSPACE</span><h1>英文初稿</h1><p>直接用中文写你的方法、实验或讨论，再转换成规范的学术英文。适合从零起草论文段落。</p></div><div class="workflow-status"><span :class="{done:draftChinese}">中文构思</span><i></i><span :class="{done:draftEnglish}">英文初稿</span></div></div>
      <div class="mobile-stage-tabs two-tabs"><button :class="{active:draftStage==='chinese'}" @click="draftStage='chinese'">中文初稿</button><button :class="{active:draftStage==='english'}" @click="draftStage='english'">学术英文</button></div>
      <section class="editor-grid draft-grid"><article :class="['editor-card','draft-source-card',{mobileHidden:draftStage!=='chinese'}]"><div class="editor-topline"><div><span class="stage-number">01</span><span><strong>中文初稿</strong><small>Write what you mean</small></span></div><button class="text-action" @click="copy(draftChinese)">复制</button></div><textarea v-model="draftChinese" placeholder="直接用中文写论文内容，不需要先组织英文表达…"></textarea><div class="editor-bottom"><span>{{ draftChineseChars }} 字</span><button class="btn primary action-button" :disabled="loading||modelAction" @click="generateDraftEnglish">{{ loading==='draft-en'?'生成中…':'生成英文初稿' }} <b>→</b></button></div></article><article :class="['editor-card','draft-output-card',{mobileHidden:draftStage!=='english'}]"><div class="editor-topline"><div><span class="stage-number">02</span><span><strong>学术英文初稿</strong><small>{{ finalEngineLabel }}</small></span></div><button class="text-action" @click="copy(draftEnglish)">复制</button></div><textarea v-model="draftEnglish" placeholder="根据中文构思生成的学术英文会出现在这里…"></textarea><div class="editor-bottom"><span>{{ draftEnglishWords }} words</span><button class="btn secondary action-button" :disabled="loading" @click="generateDraftEnglish">重新生成</button></div></article></section>
      <div class="workspace-hint"><span>◆</span><p>英文初稿同样使用当前术语库和 <strong>{{ finalEngineLabel }}</strong>；不需要提供英文原文。</p></div>
    </main>
  </div>

  <main v-else class="glossary-page"><div class="glossary-page-head"><div><span class="eyebrow">GLOSSARY LIBRARY</span><h1>术语库</h1><p>按论文、项目或研究方向组织术语。润色和初稿工作区共享这些术语库。</p></div><div class="glossary-page-stats"><div><strong>{{ glossaryGroups.length }}</strong><span>术语库</span></div><div><strong>{{ glossaryTerms.length }}</strong><span>术语</span></div><div><strong>{{ selectedGlossaryIds.length }}</strong><span>当前启用</span></div></div></div><div class="glossary-layout"><aside class="glossary-groups-panel"><div class="panel-section-title"><strong>所有术语库</strong><span>{{ glossaryGroups.length }}</span></div><div class="group-list"><button v-for="group in glossaryGroups" :key="group.id" :class="['group-card',{active:selectedGroupId===group.id}]" @click="selectGroup(group.id)"><span class="group-icon">Aa</span><span class="group-copy"><strong>{{ group.name }}</strong><small>{{ glossaryTerms.filter(t=>t.groupId===group.id).length }} 个术语</small></span><span v-if="selectedGlossaryIds.includes(group.id)" class="enabled-dot"></span></button></div><div class="new-group-card"><label class="field-label">新建术语库</label><input v-model="newGroup.name" class="control" placeholder="例如：3DGS / Active Mapping"/><textarea v-model="newGroup.description" class="control mini-area" placeholder="可选说明"></textarea><button class="btn primary wide" @click="createGroup">创建术语库</button></div></aside><section v-if="selectedGroup" class="glossary-detail"><div class="glossary-detail-head"><div class="group-title-block"><div class="large-group-icon">Aa</div><div><input v-model="groupEditor.name" class="title-input"/><input v-model="groupEditor.description" class="description-input" placeholder="添加说明…"/></div></div><div class="group-actions"><label class="enable-switch"><input type="checkbox" :checked="selectedGlossaryIds.includes(selectedGroup.id)" @change="toggleGlossary(selectedGroup.id)"/><span></span><b>{{ selectedGlossaryIds.includes(selectedGroup.id)?'参与生成':'不参与生成' }}</b></label><button class="btn secondary" @click="saveGroup">保存信息</button><button class="btn danger-ghost" @click="pendingDeleteGroupId=selectedGroup.id">删除术语库</button></div></div><div v-if="pendingDeleteGroupId===selectedGroup.id" class="delete-confirm"><span>该组内 {{ selectedGroupTerms.length }} 个术语也会一起删除。</span><div><button class="btn ghost" @click="pendingDeleteGroupId=''">取消</button><button class="btn danger" @click="confirmDeleteGroup">确认删除</button></div></div><div class="add-term-bar"><input v-model="managerTerm.english" class="control" placeholder="English term"/><input v-model="managerTerm.chinese" class="control" placeholder="中文对应"/><select v-model="managerTerm.type" class="control"><option value="locked">Locked</option><option value="preferred">Preferred</option></select><button class="btn primary" @click="addManagerTerm">添加术语</button></div><div class="terms-table-wrap"><table class="terms-table"><thead><tr><th>英文术语</th><th>中文对应</th><th>类型</th><th class="actions-col">操作</th></tr></thead><tbody><tr v-for="term in selectedGroupTerms" :key="term.id"><template v-if="editingTermId===term.id"><td><input v-model="editingTerm.english" class="table-input"/></td><td><input v-model="editingTerm.chinese" class="table-input"/></td><td><select v-model="editingTerm.type" class="table-input"><option value="locked">Locked</option><option value="preferred">Preferred</option></select></td><td class="row-actions"><button class="mini-action primary-text" @click="saveTermEdit(term)">保存</button><button class="mini-action" @click="editingTermId=''">取消</button></td></template><template v-else><td><strong>{{ term.english||'—' }}</strong></td><td>{{ term.chinese||'—' }}</td><td><span :class="['term-type-badge',term.type]">{{ term.type }}</span></td><td class="row-actions"><button class="mini-action" @click="startEditTerm(term)">编辑</button><button class="mini-action danger-text" @click="deleteTerm(term.id)">删除</button></td></template></tr><tr v-if="!selectedGroupTerms.length"><td colspan="4"><div class="table-empty">这个术语库还是空的。</div></td></tr></tbody></table></div></section><section v-else class="no-group-selected"><div class="large-group-icon">Aa</div><h2>创建第一个术语库</h2></section></div></main>

  <div v-if="showSidebar&&activeView!=='glossary'" class="sidebar-backdrop" @click="showSidebar=false"></div>
  <transition name="toast"><div v-if="toast.show" :class="['toast',toast.type]">{{ toast.message }}</div></transition>
</div>
</template>
