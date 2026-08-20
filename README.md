# PaperPolish

PaperPolish 是一个面向英文科研论文逐段润色的双语工作台，适合“先翻译为中文理解和修改，再生成学术英文”的工作流。

## 第一版功能

- 英文原文 → 忠实中文翻译
- 直接编辑中文表达
- 中文 → 学术英文重写
- 原英文 / 最终英文并排 Diff 查看
- 术语库：支持 Locked / Preferred 规则
- LaTeX、公式、引用、变量和缩写保护提示词
- 段落历史记录与当前草稿自动保存
- 浅色桌面三栏布局
- 手机端自适应布局与隐藏侧边栏
- OpenAI-compatible API，可接 OpenAI、DeepSeek 或其他兼容服务

## 快速启动

### 1. 创建 Python 环境并安装依赖

```bash
python -m venv .venv
```

Windows：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Linux / macOS：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置模型

复制配置模板：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`：

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your_api_key
LLM_MODEL=gpt-5.6
```

如果使用其他 OpenAI-compatible 服务，只需要修改 `LLM_BASE_URL` 和 `LLM_MODEL`。

### 3. 启动

```bash
python app.py
```

浏览器打开：

```text
http://127.0.0.1:5000
```

## 当前目录结构

```text
PaperPolish/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── templates/
│   └── index.html
└── static/
    ├── app.js
    └── style.css
```

## 数据说明

当前术语库、历史记录、草稿和写作风格保存在浏览器 `localStorage` 中，不会上传到服务器。论文文本只有在点击“翻译为中文”或“生成学术英文”时才会发送到你配置的模型 API。

## 后续计划

下一阶段可以继续加入：

- 真正的词级 / 句级 Diff 高亮
- 上下文段落与摘要引用
- 多论文项目管理
- 术语导入 / 导出
- 更强的 LaTeX 内容分块与保护
- Docker 部署
