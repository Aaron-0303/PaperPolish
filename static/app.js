const $ = (id) => document.getElementById(id);

const sourceText = $("sourceText");
const chineseText = $("chineseText");
const finalText = $("finalText");
const sourceCount = $("sourceCount");
const chineseCount = $("chineseCount");
const finalCount = $("finalCount");
const translateButton = $("translateButton");
const rewriteButton = $("rewriteButton");
const rewriteAgain = $("rewriteAgain");
const toast = $("toast");
const termList = $("termList");
const historyList = $("historyList");
const termModal = $("termModal");
const sidebar = $("sidebar");

const STORAGE_KEYS = {
  terms: "paperpolish_terms_v1",
  history: "paperpolish_history_v1",
  draft: "paperpolish_draft_v1",
  style: "paperpolish_style_v1",
};

let toastTimer = null;

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
}

function getJSON(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function setJSON(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function getTerms() {
  return getJSON(STORAGE_KEYS.terms, []);
}

function getHistory() {
  return getJSON(STORAGE_KEYS.history, []);
}

function updateCounts() {
  const countWords = (value) => value.trim() ? value.trim().split(/\s+/).length : 0;
  sourceCount.textContent = `${countWords(sourceText.value)} words`;
  chineseCount.textContent = `${chineseText.value.replace(/\s/g, "").length} 字`;
  finalCount.textContent = `${countWords(finalText.value)} words`;
}

function updateDiff() {
  $("diffOriginal").textContent = sourceText.value.trim() || "暂无内容";
  $("diffFinal").textContent = finalText.value.trim() || "暂无内容";
}

function saveDraft() {
  setJSON(STORAGE_KEYS.draft, {
    source: sourceText.value,
    chinese: chineseText.value,
    final: finalText.value,
  });
}

function loadDraft() {
  const draft = getJSON(STORAGE_KEYS.draft, {});
  sourceText.value = draft.source || "";
  chineseText.value = draft.chinese || "";
  finalText.value = draft.final || "";
  const savedStyle = localStorage.getItem(STORAGE_KEYS.style);
  if (savedStyle) $("styleProfile").value = savedStyle;
  updateCounts();
  updateDiff();
}

function escapeHTML(value) {
  return value.replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  }[char]));
}

function renderTerms() {
  const terms = getTerms();
  if (!terms.length) {
    termList.innerHTML = '<div class="muted">暂无术语。建议先加入论文中的固定方法名和缩写。</div>';
    return;
  }
  termList.innerHTML = terms.map((term, index) => `
    <div class="term-item">
      <div class="term-item-top">
        <div class="term-en">${escapeHTML(term.english || "—")}</div>
        <span class="badge">${term.type === "locked" ? "Locked" : "Preferred"}</span>
      </div>
      <div class="term-zh">${escapeHTML(term.chinese || "未设置中文对应")}</div>
      <button class="remove-button" data-remove-term="${index}">删除</button>
    </div>
  `).join("");
}

function renderHistory() {
  const history = getHistory();
  if (!history.length) {
    historyList.innerHTML = '<div class="muted">还没有保存过段落。</div>';
    return;
  }
  historyList.innerHTML = history.map((item, index) => `
    <div class="history-item">
      <div class="history-item-top">
        <button class="text-button" data-load-history="${index}">恢复</button>
        <button class="remove-button" data-remove-history="${index}">删除</button>
      </div>
      <div class="history-preview">${escapeHTML((item.source || item.chinese || "空段落").slice(0, 120))}</div>
    </div>
  `).join("");
}

async function apiPost(url, payload, button) {
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = "处理中…";
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`);
    return data.result || "";
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}

async function translate() {
  if (!sourceText.value.trim()) {
    showToast("请先粘贴英文原文");
    sourceText.focus();
    return;
  }
  try {
    chineseText.value = await apiPost("/api/translate", {
      text: sourceText.value,
      terms: getTerms(),
    }, translateButton);
    updateCounts();
    saveDraft();
    showToast("已翻译为中文");
  } catch (error) {
    showToast(error.message);
  }
}

async function rewrite(button = rewriteButton) {
  if (!chineseText.value.trim()) {
    showToast("请先填写或修改中文内容");
    chineseText.focus();
    return;
  }
  try {
    finalText.value = await apiPost("/api/rewrite", {
      chinese: chineseText.value,
      original: sourceText.value,
      terms: getTerms(),
      style: $("styleProfile").value,
    }, button);
    updateCounts();
    updateDiff();
    saveDraft();
    showToast("已生成学术英文");
  } catch (error) {
    showToast(error.message);
  }
}

function saveParagraph() {
  if (![sourceText.value, chineseText.value, finalText.value].some((v) => v.trim())) {
    showToast("当前段落为空");
    return;
  }
  const history = getHistory();
  history.unshift({
    source: sourceText.value,
    chinese: chineseText.value,
    final: finalText.value,
    savedAt: new Date().toISOString(),
  });
  setJSON(STORAGE_KEYS.history, history.slice(0, 100));
  renderHistory();
  showToast("段落已保存到本地历史");
}

function clearWorkspace() {
  sourceText.value = "";
  chineseText.value = "";
  finalText.value = "";
  updateCounts();
  updateDiff();
  saveDraft();
  sourceText.focus();
}

function openTermModal() {
  $("termEnglish").value = "";
  $("termChinese").value = "";
  $("termType").value = "locked";
  termModal.hidden = false;
  $("termEnglish").focus();
}

function closeTermModal() {
  termModal.hidden = true;
}

function saveTerm() {
  const english = $("termEnglish").value.trim();
  const chinese = $("termChinese").value.trim();
  const type = $("termType").value;
  if (!english && !chinese) {
    showToast("至少填写一个术语字段");
    return;
  }
  const terms = getTerms();
  terms.push({ english, chinese, type });
  setJSON(STORAGE_KEYS.terms, terms);
  renderTerms();
  closeTermModal();
  showToast("术语已保存");
}

function switchSidePanel(name) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.panel === name);
  });
  document.querySelectorAll("[data-side-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.sidePanel !== name;
  });
}

async function loadConfigStatus() {
  try {
    const response = await fetch("/api/config");
    const data = await response.json();
    $("configStatus").textContent = data.configured
      ? `模型已配置：${data.model}\n${data.base_url}`
      : "模型尚未配置。请在 .env 中设置 LLM_API_KEY。";
  } catch {
    $("configStatus").textContent = "无法读取模型配置。";
  }
}

[sourceText, chineseText, finalText].forEach((area) => {
  area.addEventListener("input", () => {
    updateCounts();
    updateDiff();
    saveDraft();
  });
});

translateButton.addEventListener("click", translate);
rewriteButton.addEventListener("click", () => rewrite(rewriteButton));
rewriteAgain.addEventListener("click", () => rewrite(rewriteAgain));
$("saveParagraph").addEventListener("click", saveParagraph);
$("newParagraph").addEventListener("click", clearWorkspace);
$("addTerm").addEventListener("click", openTermModal);
$("closeTermModal").addEventListener("click", closeTermModal);
$("saveTerm").addEventListener("click", saveTerm);
$("openSidebar").addEventListener("click", () => sidebar.classList.add("open"));
$("closeSidebar").addEventListener("click", () => sidebar.classList.remove("open"));

$("styleProfile").addEventListener("input", (event) => {
  localStorage.setItem(STORAGE_KEYS.style, event.target.value);
});

$("diffToggle").addEventListener("click", () => {
  const content = $("diffContent");
  content.hidden = !content.hidden;
  $("diffToggle").setAttribute("aria-expanded", String(!content.hidden));
  $("diffChevron").textContent = content.hidden ? "⌄" : "⌃";
});

termModal.addEventListener("click", (event) => {
  if (event.target === termModal) closeTermModal();
});

document.addEventListener("click", async (event) => {
  const navItem = event.target.closest(".nav-item");
  if (navItem) {
    switchSidePanel(navItem.dataset.panel);
    if (window.innerWidth <= 760 && navItem.dataset.panel !== "workspace") sidebar.classList.add("open");
  }

  const copyButton = event.target.closest("[data-copy]");
  if (copyButton) {
    const target = $(copyButton.dataset.copy);
    try {
      await navigator.clipboard.writeText(target.value);
      showToast("已复制");
    } catch {
      target.select();
      document.execCommand("copy");
      showToast("已复制");
    }
  }

  const removeTerm = event.target.closest("[data-remove-term]");
  if (removeTerm) {
    const terms = getTerms();
    terms.splice(Number(removeTerm.dataset.removeTerm), 1);
    setJSON(STORAGE_KEYS.terms, terms);
    renderTerms();
  }

  const loadHistory = event.target.closest("[data-load-history]");
  if (loadHistory) {
    const item = getHistory()[Number(loadHistory.dataset.loadHistory)];
    if (item) {
      sourceText.value = item.source || "";
      chineseText.value = item.chinese || "";
      finalText.value = item.final || "";
      updateCounts();
      updateDiff();
      saveDraft();
      sidebar.classList.remove("open");
      showToast("已恢复历史段落");
    }
  }

  const removeHistory = event.target.closest("[data-remove-history]");
  if (removeHistory) {
    const history = getHistory();
    history.splice(Number(removeHistory.dataset.removeHistory), 1);
    setJSON(STORAGE_KEYS.history, history);
    renderHistory();
  }
});

loadDraft();
renderTerms();
renderHistory();
loadConfigStatus();
