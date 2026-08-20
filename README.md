# PaperPolish

PaperPolish 是一个面向英文科研论文逐段润色的双语工作台，适合“先翻译为中文理解和修改，再生成学术英文”的工作流。

## 当前功能

- 英文原文 → 忠实中文翻译
- 直接编辑中文表达
- 中文 → 学术英文重写
- 原英文 / 最终英文词级 Diff 高亮
- 术语库：支持 Locked / Preferred 规则
- Locked 术语程序级占位符保护，不只依赖 Prompt
- LaTeX、数学公式、引用与引用命令程序级保护
- 模型破坏保护占位符时拒绝返回，避免静默改坏公式或术语
- 段落历史记录、保存时间与当前草稿自动保存
- Ctrl / Cmd + S 快速保存当前段落
- 新建段落前自动保存现有内容
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

## 术语规则

### Locked

用于方法名、模块名、数据集名、固定缩写等不能被模型自由改写的内容。

- 英文 → 中文时：Locked 英文术语保持原样，不交给模型翻译。
- 中文 → 英文时：如果同时配置了中文和英文对应关系，中文术语会被恢复为指定的标准英文写法。

### Preferred

用于希望模型优先采用、但不需要强制占位符锁定的常用学术表达。

## 测试

程序级保护逻辑可以在不调用任何模型 API 的情况下测试：

```bash
python -m unittest discover -s tests
```

测试覆盖：

- LaTeX / 数学表达式原样恢复
- Locked 英文术语保护
- Locked 中文术语映射到标准英文
- 模型遗漏保护占位符时主动报错

## 当前目录结构

```text
PaperPolish/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── tests/
│   └── test_protection.py
├── templates/
│   └── index.html
└── static/
    ├── app.js
    └── style.css
```

## 数据说明

当前术语库、历史记录、草稿和写作风格保存在浏览器 `localStorage` 中，不会主动上传到服务器。论文文本只有在点击“翻译为中文”或“生成学术英文”时才会发送到你配置的模型 API。

## 后续计划

下一阶段可以继续加入：

- 上下文段落与摘要引用
- 多论文项目管理
- 术语导入 / 导出
- 更完善的 LaTeX 分块处理
- Docker 部署
