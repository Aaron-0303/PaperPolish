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
const mode = ref(localStorage.getItem('paperpolish_mode_v1') || 'paper')
const formatType = ref(localStorage.getItem('paperpolish_format_v1') || 'LaTeX')
const preferencesText = ref(localStorage.getItem('paperpolish_preferences_v1') || 'Preserve technical meaning\nUse concise academic wording\nDo not expand claims')
const backgroundText = ref(localStorage.getItem('paperpolish_background_v1') || '')
const toast = reactive({ show: false, message: '', type: 'info' })
let toastTimer

const modelStatus = reactive({ ready:false, model:'tencent/Hy-MT2-7B', status:'checking', downloaded:false, dtype:'bfloat16', lastLoadSeconds:null, lastError:'', gpu:null })
const terms = ref(JSON.parse(localStorage.getItem('paperpolish_terms_v2') || '[]'))
const history = ref(JSON.parse(localStorage.getItem('paperpolish_history_v2') || '[]'))
const style = ref(localStorage.getItem('paperpolish_style_v2') || 'CVPR/IEEE concise academic style')
const newTerm = reactive({ english:'', chinese:'', type:'locked' })

const sourceWords = computed(() => source.value.trim() ? source.value.trim().split(/\s+/).length : 0)
const finalWords = computed(() => finalEnglish.value.trim() ? finalEnglish.value.trim().split(/\s+/).length : 0)
const chineseChars = computed(() => chinese.value.replace(/\s/g,'').length)
const gpuPercent = computed(() => {
  const gpu = modelStatus.gpu
  if (!gpu?.available || !gpu.total_mb) return 0
  return Math.min(100, Math.max(0, gpu.used_mb / gpu.total_mb * 100))
})
const modelLabel = computed(() => {
  if (modelStatus.status === 'offline') return '后端离线'
  if (modelStatus.status === 'loading') return '模型加载中'
  return modelStatus.ready ? '模型已就绪' : '模型未加载'
})
const currentModeLabel = computed(() => ({
  paper:'论文模式', default:'默认翻译', terminology:'术语模式', style:'风格模式',
  personalization:'个性化', delimiters:'分隔符保护', 'structured-data-1':'结构化数据', 'structured-data-2':'背景增强',
}[mode.value] || '论文模式'))
const modeHelp = computed(() => ({
  paper:'术语、论文风格、背景信息和 LaTeX 保护同时生效，适合日常论文润色。',
  default:'仅执行标准翻译，不附加额外约束。',
  terminology:'重点使用术语库中的固定翻译。',
  style:'重点控制目标英文的写作风格。',
  personalization:'按自定义规则逐条约束翻译。',
  delimiters:'强化保护占位符和分隔符的位置与数量。',
  'structured-data-1':'适合 LaTeX、Markdown、JSON 等结构化文本。',
  'structured-data-2':'使用额外背景信息辅助当前段落翻译。',
}[mode.value]))

watch([source,chinese,finalEnglish],()=>localStorage.setItem('paperpolish_draft_v2',JSON.stringify({source:source.value,chinese:chinese.value,finalEnglish:finalEnglish.value})))
watch(terms,v=>localStorage.setItem('paperpolish_terms_v2',JSON.stringify(v)),{deep:true})
watch(history,v=>localStorage.setItem('paperpolish_history_v2',JSON.stringify(v)),{deep:true})
watch(style,v=>localStorage.setItem('paperpolish_style_v2',v))
watch(mode,v=>localStorage.setItem('paperpolish_mode_v1',v))
watch(formatType,v=>localStorage.setItem('paperpolish_format_v1',v))
watch(preferencesText,v=>localStorage.setItem('paperpolish_preferences_v1',v))
watch(backgroundText,v=>localStorage.setItem('paperpolish_background_v1',v))

function notify(message, type='info') {
  clearTimeout(toastTimer)
  toast.message = message
  toast.type = type
  toast.show = true
  toastTimer = setTimeout(() => { toast.show = false }, 2600)
}

function applyModelStatus(data){
  modelStatus.ready=!!data.model_ready
  modelStatus.model=data.model||'tencent/Hy-MT2-7B'
  modelStatus.status=data.status||'unknown'
  modelStatus.downloaded=!!data.downloaded
  modelStatus.dtype=data.dtype||'bfloat16'
  modelStatus.lastLoadSeconds=data.last_load_seconds??null
  modelStatus.lastError=data.last_error||''
  modelStatus.gpu=data.gpu||null
}

async function callApi(direction){
  const text = direction === 'en-zh' ? source.value.trim() : chinese.value.trim()
  if(!text){ notify(direction === 'en-zh' ? '先粘贴英文原文' : '先完成中文修改', 'warning'); return }
  if(!modelStatus.ready){
    notify('请先加载 Hy-MT2-7B 模型', 'warning')
    showModelManager.value = true
    showSidebar.value = true
    activeTool.value = 'model'
    return
  }
  loading.value=direction
  try{
    const response=await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      text,direction,mode:mode.value,terms:terms.value,original_english:source.value,style:style.value,
      preferences:preferencesText.value.split('\n').map(v=>v.trim()).filter(Boolean),format_type:formatType.value,
      background_text:backgroundText.value,
    })})
    const data=await response.json()
    if(!response.ok) throw new Error(data.detail||'请求失败')
    if(direction==='en-zh'){
      chinese.value=data.result
      activeStage.value='chinese'
      notify('中文初稿已生成', 'success')
    }else{
      finalEnglish.value=data.result
      activeStage.value='final'
      notify('学术英文已生成', 'success')
    }
    await checkHealth()
  }catch(error){
    notify(error.message, 'error')
  }finally{
    loading.value=''
  }
}

function saveParagraph(){
  if(!source.value&&!chinese.value&&!finalEnglish.value){ notify('当前没有可保存的内容', 'warning'); return }
  history.value.unshift({source:source.value,chinese:chinese.value,finalEnglish:finalEnglish.value,savedAt:new Date().toISOString()})
  history.value=history.value.slice(0,100)
  notify('段落已保存到历史记录', 'success')
}
function loadParagraph(item){
  source.value=item.source||''
  chinese.value=item.chinese||''
  finalEnglish.value=item.finalEnglish||''
  activeStage.value='source'
  showSidebar.value=false
  notify('已载入历史段落')
}
function newParagraph(){
  if(source.value||chinese.value||finalEnglish.value) saveParagraph()
  source.value=''; chinese.value=''; finalEnglish.value=''; activeStage.value='source'
}
function addTerm(){
  if(!newTerm.english.trim()&&!newTerm.chinese.trim()) return
  terms.value.push({...newTerm})
  newTerm.english=''; newTerm.chinese=''; newTerm.type='locked'
  notify('术语已添加', 'success')
}
async function copy(text){
  if(!text) return
  await navigator.clipboard.writeText(text)
  notify('已复制到剪贴板', 'success')
}
async function checkHealth(){
  try{
    const r=await fetch('/api/model/status')
    const d=await r.json()
    if(!r.ok)throw new Error()
    applyModelStatus(d)
  }catch{
    modelStatus.ready=false
    modelStatus.status='offline'
    modelStatus.lastError='无法连接后端服务'
  }
}
async function manageModel(action){
  modelAction.value=action
  try{
    const r=await fetch(`/api/model/${action}`,{method:'POST'})
    const d=await r.json()
    if(!r.ok)throw new Error(d.detail||'模型操作失败')
    applyModelStatus(d)
    notify(action==='load'?'模型加载完成':'模型已卸载', 'success')
  }catch(e){
    notify(e.message, 'error')
    await checkHealth()
  }finally{
    modelAction.value=''
  }
}
function formatMb(v){
  if(v==null)return'—'
  return v>=1024?`${(v/1024).toFixed(1)} GB`:`${Math.round(v)} MB`
}
function openTool(tool){
  activeTool.value=tool
  showSidebar.value=true
  if(tool==='model') showModelManager.value=true
}

onMounted(()=>{
  const d=JSON.parse(localStorage.getItem('paperpolish_draft_v2')||'{}')
  source.value=d.source||''
  chinese.value=d.chinese||''
  finalEnglish.value=d.finalEnglish||''
  checkHealth()
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-left">
        <button class="mobile-menu" @click="showSidebar=!showSidebar" aria-label="打开菜单">☰</button>
        <div class="brand-mark">P</div>
        <div class="brand-lockup">
          <strong>PaperPolish</strong>
          <span>Academic bilingual editor</span>
        </div>
      </div>

      <div class="topbar-center">
        <button class="model-pill" @click="openTool('model')">
          <span :class="['status-dot', modelStatus.ready ? 'ready' : modelStatus.status==='loading' ? 'busy' : 'idle']"></span>
          <span>{{ modelLabel }}</span>
          <span class="pill-meta" v-if="modelStatus.gpu?.available">GPU {{ modelStatus.gpu.host_device ?? 3 }}</span>
        </button>
        <div class="mode-pill">{{ currentModeLabel }}</div>
      </div>

      <div class="topbar-actions">
        <button class="btn ghost" @click="newParagraph">新段落</button>
        <button class="btn primary" @click="saveParagraph">保存</button>
      </div>
    </header>

    <div class="body-shell">
      <aside :class="['sidebar', { open: showSidebar }]">
        <div class="sidebar-nav">
          <button :class="['nav-item',{active:activeTool==='settings'}]" @click="openTool('settings')"><span>⚙</span><b>翻译设置</b></button>
          <button :class="['nav-item',{active:activeTool==='terms'}]" @click="openTool('terms')"><span>⌘</span><b>术语库</b><em>{{ terms.length }}</em></button>
          <button :class="['nav-item',{active:activeTool==='history'}]" @click="openTool('history')"><span>↺</span><b>历史记录</b><em>{{ history.length }}</em></button>
          <button :class="['nav-item',{active:activeTool==='model'}]" @click="openTool('model')"><span>◉</span><b>模型管理</b></button>
        </div>

        <div class="sidebar-content">
          <section v-if="activeTool==='settings'" class="tool-panel">
            <div class="tool-heading"><div><span class="eyebrow">TRANSLATION</span><h2>翻译设置</h2></div><button class="close-mobile" @click="showSidebar=false">×</button></div>

            <label class="field-label">模式</label>
            <select v-model="mode" class="control">
              <option value="paper">PaperPolish 论文模式（推荐）</option>
              <option value="default">Default Translation</option>
              <option value="terminology">Terminology</option>
              <option value="style">Style</option>
              <option value="personalization">Personalization</option>
              <option value="delimiters">Delimiters</option>
              <option value="structured-data-1">Structured Data 1</option>
              <option value="structured-data-2">Structured Data 2</option>
            </select>
            <p class="helper">{{ modeHelp }}</p>

            <template v-if="mode==='style'||mode==='paper'">
              <label class="field-label">目标英文风格</label>
              <textarea v-model="style" class="control compact-area" />
            </template>
            <template v-if="mode==='personalization'">
              <label class="field-label">个性化规则</label>
              <textarea v-model="preferencesText" class="control compact-area" />
            </template>
            <template v-if="mode==='structured-data-1'">
              <label class="field-label">结构类型</label>
              <input v-model="formatType" class="control" placeholder="LaTeX / Markdown / JSON" />
            </template>
            <template v-if="mode==='structured-data-2'||mode==='paper'">
              <label class="field-label">额外背景 <span>可选</span></label>
              <textarea v-model="backgroundText" class="control compact-area" placeholder="留空时，中译英自动使用英文原文。" />
            </template>
          </section>

          <section v-if="activeTool==='terms'" class="tool-panel">
            <div class="tool-heading"><div><span class="eyebrow">GLOSSARY</span><h2>术语库</h2></div><button class="close-mobile" @click="showSidebar=false">×</button></div>
            <p class="helper">Locked 会程序级锁定；Preferred 作为推荐译法提供给模型。</p>
            <div class="term-form">
              <input v-model="newTerm.english" class="control" placeholder="English term" />
              <input v-model="newTerm.chinese" class="control" placeholder="中文对应" />
              <div class="inline-fields"><select v-model="newTerm.type" class="control"><option value="locked">Locked</option><option value="preferred">Preferred</option></select><button class="btn primary" @click="addTerm">添加</button></div>
            </div>
            <div class="item-list">
              <div v-for="(term,i) in terms" :key="i" class="list-card">
                <div class="list-card-main"><strong>{{ term.english||'—' }}</strong><span>{{ term.chinese||'—' }}</span></div>
                <div class="list-card-side"><em :class="['tag',term.type]">{{ term.type }}</em><button @click="terms.splice(i,1)">×</button></div>
              </div>
              <div v-if="!terms.length" class="empty-state">还没有术语。把论文里容易被改写的专有名词先锁定。</div>
            </div>
          </section>

          <section v-if="activeTool==='history'" class="tool-panel">
            <div class="tool-heading"><div><span class="eyebrow">HISTORY</span><h2>历史记录</h2></div><button class="close-mobile" @click="showSidebar=false">×</button></div>
            <div class="item-list history-list">
              <button v-for="(item,i) in history" :key="i" class="history-card" @click="loadParagraph(item)">
                <span>{{ (item.source||item.chinese||'空段落').slice(0,100) }}</span>
                <small>{{ new Date(item.savedAt).toLocaleString() }}</small>
              </button>
              <div v-if="!history.length" class="empty-state">保存过的段落会出现在这里。</div>
            </div>
          </section>

          <section v-if="activeTool==='model'" class="tool-panel">
            <div class="tool-heading"><div><span class="eyebrow">RUNTIME</span><h2>模型管理</h2></div><button class="close-mobile" @click="showSidebar=false">×</button></div>
            <div class="model-hero">
              <div class="model-hero-row"><div class="model-icon">H</div><div><strong>Hy-MT2-7B</strong><span>{{ modelStatus.downloaded?'本地权重已就绪':'本地权重未下载' }}</span></div></div>
              <div :class="['runtime-badge', modelStatus.ready ? 'ready' : 'idle']">{{ modelLabel }}</div>
            </div>
            <template v-if="modelStatus.gpu?.available">
              <div class="gpu-card">
                <div class="gpu-title"><div><span>GPU {{ modelStatus.gpu.host_device ?? 3 }}</span><strong>{{ modelStatus.gpu.name }}</strong></div><b>{{ Math.round(gpuPercent) }}%</b></div>
                <div class="memory-track"><div class="memory-fill" :style="{width:`${gpuPercent}%`}"></div></div>
                <div class="gpu-stats"><span>已用 {{ formatMb(modelStatus.gpu.used_mb) }}</span><span>总计 {{ formatMb(modelStatus.gpu.total_mb) }}</span></div>
              </div>
            </template>
            <div v-else class="notice warning">未检测到 CUDA GPU。</div>
            <div v-if="modelStatus.lastError" class="notice error">{{ modelStatus.lastError }}</div>
            <div class="stack-actions">
              <button class="btn primary wide" :disabled="modelStatus.ready||modelAction" @click="manageModel('load')">{{ modelAction==='load'?'加载中…':modelStatus.downloaded?'加载模型':'下载并加载' }}</button>
              <button class="btn secondary wide" :disabled="!modelStatus.ready||modelAction||loading" @click="manageModel('unload')">{{ modelAction==='unload'?'卸载中…':'卸载模型' }}</button>
              <button class="btn ghost wide" :disabled="modelAction" @click="checkHealth">刷新状态</button>
            </div>
          </section>
        </div>
      </aside>

      <div v-if="showSidebar" class="sidebar-backdrop" @click="showSidebar=false"></div>

      <main class="workspace-page">
        <section class="workspace-intro">
          <div>
            <span class="eyebrow">PARAGRAPH WORKSPACE</span>
            <h1>把中文改对，英文自然会更好。</h1>
            <p>原文负责语境，中文负责意图，Hy-MT2 负责把你的意思写成学术英文。</p>
          </div>
          <div class="workflow-status">
            <span :class="{done:source.length}">1 原文</span><i></i><span :class="{done:chinese.length}">2 中文</span><i></i><span :class="{done:finalEnglish.length}">3 英文</span>
          </div>
        </section>

        <div class="mobile-stage-tabs">
          <button :class="{active:activeStage==='source'}" @click="activeStage='source'">英文原文</button>
          <button :class="{active:activeStage==='chinese'}" @click="activeStage='chinese'">中文修改</button>
          <button :class="{active:activeStage==='final'}" @click="activeStage='final'">最终英文</button>
        </div>

        <section class="editor-grid">
          <article :class="['editor-card','source-card',{mobileActive:activeStage==='source'}]">
            <div class="editor-topline">
              <div><span class="stage-number">01</span><div><strong>英文原文</strong><small>Source</small></div></div>
              <button class="text-action" @click="copy(source)">复制</button>
            </div>
            <textarea v-model="source" spellcheck="false" placeholder="Paste the original English paragraph here…" />
            <div class="editor-bottom">
              <span>{{ sourceWords }} words</span>
              <button class="btn primary action-button" :disabled="loading||modelAction" @click="callApi('en-zh')">{{ loading==='en-zh'?'正在翻译…':'翻译为中文' }} <b>→</b></button>
            </div>
          </article>

          <article :class="['editor-card','chinese-card',{mobileActive:activeStage==='chinese'}]">
            <div class="editor-topline">
              <div><span class="stage-number">02</span><div><strong>中文修改</strong><small>Your intent</small></div></div>
              <button class="text-action" @click="copy(chinese)">复制</button>
            </div>
            <textarea v-model="chinese" placeholder="这里不是直译终点。把中文改成你真正想表达的意思…" />
            <div class="editor-bottom">
              <span>{{ chineseChars }} 字</span>
              <button class="btn primary action-button" :disabled="loading||modelAction" @click="callApi('zh-en')">{{ loading==='zh-en'?'正在生成…':'生成学术英文' }} <b>→</b></button>
            </div>
          </article>

          <article :class="['editor-card','final-card',{mobileActive:activeStage==='final'}]">
            <div class="editor-topline">
              <div><span class="stage-number">03</span><div><strong>最终英文</strong><small>Academic output</small></div></div>
              <button class="text-action" @click="copy(finalEnglish)">复制</button>
            </div>
            <textarea v-model="finalEnglish" spellcheck="false" placeholder="Academic English will appear here…" />
            <div class="editor-bottom">
              <span>{{ finalWords }} words</span>
              <button class="btn secondary action-button" :disabled="loading||modelAction||!chinese" @click="callApi('zh-en')">重新生成</button>
            </div>
          </article>
        </section>

        <div class="workspace-hint"><span>⌘</span><p><strong>工作方式：</strong>不要直接修最终英文。先把中间的中文改成你真正想说的内容，再重新生成，稳定性更高。</p></div>
      </main>
    </div>

    <transition name="toast">
      <div v-if="toast.show" :class="['toast',toast.type]">{{ toast.message }}</div>
    </transition>
  </div>
</template>
