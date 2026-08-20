# PaperPolish

PaperPolish 是一个面向英文科研论文逐段润色的双语工作台，适合下面这条固定工作流：

**英文原文 → Hy-MT2 翻译为中文 → 修改中文 → Hy-MT2 翻译为学术英文**

当前版本采用类似 DeepSeek OCR Web 项目的前后端分离思路：

```text
Browser
  ↓
Vue 3 + Nginx frontend
  ↓ /api
FastAPI GPU backend
  ↓
Hy-MT2-7B (local model)
```

不使用 Flask，也不依赖外部商业 API。

## 当前功能

- 英文 → 中文忠实翻译
- 中文编辑 → 学术英文翻译
- Hy-MT2-7B 本地推理
- Locked / Preferred 术语库
- LaTeX、公式、引用、变量占位符保护
- 原始英文作为中译英背景信息
- CVPR / IEEE 风格约束
- 浏览器本地草稿与历史记录
- 浅色三栏工作台
- Vue 3 前端
- FastAPI 后端
- Docker Compose 一键部署
- 模型文件独立保存在 `./models/Hy-MT2-7B`
- 代码更新或重新构建 Docker 时不会重复下载模型

## 项目结构

```text
PaperPolish/
├── backend/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.vue
│       ├── main.js
│       └── style.css
├── models/                 # 本地模型目录，不提交 Git
├── tests/
├── docker-compose.yml
├── .env.example
└── README.md
```

## Docker 部署

### 1. 前提

宿主机需要：

- NVIDIA GPU
- NVIDIA Driver
- Docker
- Docker Compose
- NVIDIA Container Toolkit

确认 Docker 能看到 GPU：

```bash
docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi
```

### 2. 配置

```bash
cp .env.example .env
```

默认配置：

```env
MODEL_ID=tencent/Hy-MT2-7B
MODEL_DTYPE=bfloat16
MAX_NEW_TOKENS=4096
HF_ENDPOINT=https://huggingface.co
```

### 3. 启动

```bash
docker compose up -d --build
```

访问：

```text
http://127.0.0.1:30330
```

后端调试接口：

```text
http://127.0.0.1:8000/api/health
```

## 模型下载与持久化

后端启动时检查：

```text
./models/Hy-MT2-7B/config.json
```

如果存在，则直接从本地加载模型。

如果不存在，则自动从 Hugging Face 下载：

```text
tencent/Hy-MT2-7B
```

模型最终保存到宿主机：

```text
./models/Hy-MT2-7B/
```

Docker 中映射为：

```text
/models/Hy-MT2-7B/
```

因此以后更新代码、重新构建 frontend/backend 镜像，都不会重新下载模型。

如果你已经手动下载好 Hy-MT2-7B，只需要把完整模型目录放到：

```text
PaperPolish/models/Hy-MT2-7B/
```

然后直接启动 Docker 即可。

## Hy-MT2 使用方式

PaperPolish 使用 Hy-MT2 官方推荐的翻译提示方式和 7B 推理参数：

```text
temperature = 0.7
top_p = 0.6
top_k = 20
repetition_penalty = 1.05
max_new_tokens = 4096
```

中译英时会把原始英文段落作为 Background Information 提供给模型，帮助模型保持原论文中的专业表达和上下文。

术语规则会使用 Hy-MT2 的 terminology instruction，同时 Locked 术语和 LaTeX 内容还会在程序侧替换为占位符，模型输出后再原样恢复。

## 开发模式

前端：

```bash
cd frontend
npm install
npm run dev
```

后端需要 CUDA / PyTorch / Transformers 环境：

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

开发环境下 Vite 会将 `/api` 代理到 `http://localhost:8000`。

## 数据

术语库、历史记录、当前草稿和英文风格设置暂时保存在浏览器 `localStorage` 中。

论文文本只会发送到本机 FastAPI 后端和本地 Hy-MT2-7B，不会发送到外部 LLM API。
