<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'

const source = ref('')
const chinese = ref('')
const finalEnglish = ref('')
const loading = ref('')
const modelStatus = reactive({ ready: false, model: 'Hy-MT2-7B', status: 'checking' })
const terms = ref(JSON.parse(localStorage.getItem('paperpolish_terms_v2') || '[]'))
const history = ref(JSON.parse(localStorage.getItem('paperpolish_history_v2') || '[]'))
const style = ref(localStorage.getItem('paperpolish_style_v2') || 'CVPR/IEEE concise academic style')
const showTerms = ref(false)
const showHistory = ref(false)
const newTerm = reactive({ english: '', chinese: '', type: 'locked' })

const sourceWords = computed(() => source.value.trim() ? source.value.trim().split(/\s+/).length : 0)
const finalWords = computed(() => finalEnglish.value.trim() ? finalEnglish.value.trim().split(/\s+/).length : 0)
const chineseChars = computed(() => chinese.value.replace(/\s/g, '').length)

watch([source, chinese, finalEnglish], () => {
  localStorage.setItem('paperpolish_draft_v2', JSON.stringify({ source: source.value, chinese: chinese.value, finalEnglish: finalEnglish.value }))
})
watch(terms, value => localStorage.setItem('paperpolish_terms_v2', JSON.stringify(value)), { deep: true })
watch(history, value => localStorage.setItem('paperpolish_history_v2', JSON.stringify(value)), { deep: true })
watch(style, value => localStorage.setItem('paperpolish_style_v2', value))

async function callApi(direction) {
  const text = direction === 'en-zh' ? source.value.trim() : chinese.value.trim()
  if (!text) return
  loading.value = direction
  try {
    const response = await fetch('/api/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        direction,
        terms: terms.value,
        original_english: source.value,
        style: style.value,
      }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || '请求失败')
    if (direction === 'en-zh') chinese.value = data.result
    else finalEnglish.value = data.result
  } catch (error) {
    alert(error.message)
  } finally {
    loading.value = ''
  }
}

function saveParagraph() {
  if (!source.value && !chinese.value && !finalEnglish.value) return
  history.value.unshift({
    source: source.value,
    chinese: chinese.value,
    finalEnglish: finalEnglish.value,
    savedAt: new Date().toISOString(),
  })
  history.value = history.value.slice(0, 100)
}

function loadParagraph(item) {
  source.value = item.source || ''
  chinese.value = item.chinese || ''
  finalEnglish.value = item.finalEnglish || ''
  showHistory.value = false
}

function newParagraph() {
  if (source.value || chinese.value || finalEnglish.value) saveParagraph()
  source.value = ''
  chinese.value = ''
  finalEnglish.value = ''
}

function addTerm() {
  if (!newTerm.english.trim() && !newTerm.chinese.trim()) return
  terms.value.push({ ...newTerm })
  newTerm.english = ''
  newTerm.chinese = ''
  newTerm.type = 'locked'
}

async function copy(text) {
  if (!text) return
  await navigator.clipboard.writeText(text)
}

async function checkHealth() {
  try {
    const response = await fetch('/api/health')
    const data = await response.json()
    modelStatus.ready = !!data.model_ready
    modelStatus.model = data.model || 'Hy-MT2-7B'
    modelStatus.status = data.model_status || 'unknown'
  } catch {
    modelStatus.ready = false
    modelStatus.status = 'offline'
  }
}

onMounted(() => {
  const draft = JSON.parse(localStorage.getItem('paperpolish_draft_v2') || '{}')
  source.value = draft.source || ''
  chinese.value = draft.chinese || ''
  finalEnglish.value = draft.finalEnglish || ''
  checkHealth()
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">PaperPolish</div>
      <div class="subtitle">论文双语润色工作台</div>

      <div class="status-card">
        <div class="status-row">
          <span :class="['dot', modelStatus.ready ? 'ok' : 'bad']"></span>
          <strong>{{ modelStatus.ready ? '模型已就绪' : '模型未就绪' }}</strong>
        </div>
        <small>{{ modelStatus.model }}</small>
      </div>

      <button class="side-button" @click="showTerms = !showTerms">术语库 <span>{{ terms.length }}</span></button>
      <button class="side-button" @click="showHistory = !showHistory">历史记录 <span>{{ history.length }}</span></button>

      <div v-if="showTerms" class="panel">
        <div class="panel-title">术语库</div>
        <input v-model="newTerm.english" placeholder="英文术语" />
        <input v-model="newTerm.chinese" placeholder="中文对应" />
        <select v-model="newTerm.type">
          <option value="locked">Locked</option>
          <option value="preferred">Preferred</option>
        </select>
        <button class="secondary" @click="addTerm">添加术语</button>
        <div v-for="(term, i) in terms" :key="i" class="term-item">
          <div><strong>{{ term.english || '—' }}</strong><span>{{ term.type }}</span></div>
          <small>{{ term.chinese || '—' }}</small>
          <button @click="terms.splice(i, 1)">删除</button>
        </div>
      </div>

      <div v-if="showHistory" class="panel">
        <div class="panel-title">历史记录</div>
        <div v-for="(item, i) in history" :key="i" class="history-item" @click="loadParagraph(item)">
          {{ (item.source || item.chinese || '空段落').slice(0, 80) }}
        </div>
      </div>

      <div class="panel">
        <div class="panel-title">英文风格</div>
        <textarea v-model="style" class="style-input"></textarea>
      </div>
    </aside>

    <main>
      <header>
        <div>
          <h1>段落工作台</h1>
          <p>英文原文 → 中文修改 → 学术英文</p>
        </div>
        <div class="actions">
          <button class="secondary" @click="newParagraph">新段落</button>
          <button class="primary" @click="saveParagraph">保存段落</button>
        </div>
      </header>

      <section class="workspace">
        <article class="editor-card">
          <div class="editor-head"><strong>01 英文原文</strong><button @click="copy(source)">复制</button></div>
          <textarea v-model="source" placeholder="粘贴需要润色的英文论文段落…"></textarea>
          <div class="editor-foot"><span>{{ sourceWords }} words</span><button class="primary" :disabled="loading" @click="callApi('en-zh')">{{ loading === 'en-zh' ? '翻译中…' : '翻译为中文 →' }}</button></div>
        </article>

        <article class="editor-card focus">
          <div class="editor-head"><strong>02 中文修改</strong><button @click="copy(chinese)">复制</button></div>
          <textarea v-model="chinese" placeholder="翻译结果会出现在这里，你只需要修改中文表达。"></textarea>
          <div class="editor-foot"><span>{{ chineseChars }} 字</span><button class="primary" :disabled="loading" @click="callApi('zh-en')">{{ loading === 'zh-en' ? '生成中…' : '生成学术英文 →' }}</button></div>
        </article>

        <article class="editor-card">
          <div class="editor-head"><strong>03 最终英文</strong><button @click="copy(finalEnglish)">复制</button></div>
          <textarea v-model="finalEnglish" placeholder="最终英文会出现在这里…"></textarea>
          <div class="editor-foot"><span>{{ finalWords }} words</span><button class="secondary" :disabled="loading" @click="callApi('zh-en')">重新生成</button></div>
        </article>
      </section>
    </main>
  </div>
</template>
