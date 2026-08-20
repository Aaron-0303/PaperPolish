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
- 模型按需加载 / 卸载，不用时不占显存
- 模型管理面板：模型状态、权重状态、GPU、显存、加载耗时
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
HF_ENDPOINT=https://hf-mirror.com
```

### 3. 启动

```bash
docker compose up -d --build
```

访问：

```text
http://127.0.0.1:30430
```

后端调试接口：

```text
http://127.0.0.1:30480/api/health
```

PaperPolish 使用独立端口，避免与 DeepSeek OCR 的 `30330 / 30380` 冲突：

```text
PaperPolish frontend: 30430
PaperPolish backend:  30480
```

## 模型管理

容器启动后，Hy-MT2-7B **不会自动加载到显存**。网页可以正常打开，GPU 显存保持空闲。

在左侧“模型管理”面板中可以看到：

- 模型是否已经下载
- 模型是否已经加载
- GPU 型号和设备编号
- 总显存、已用显存、剩余显存
- PyTorch 当前分配显存
- 模型 dtype
- 上一次模型加载耗时
- 最近一次加载错误

操作按钮：

```text
加载模型 / 下载并加载
卸载模型
刷新状态
```

如果模型权重已经存在，点击“加载模型”会直接从本地目录加载。

如果模型权重不存在，第一次点击“下载并加载”时会从 Hugging Face 镜像下载到：

```text
./models/Hy-MT2-7B/
```

卸载模型时，后端会删除模型与 tokenizer 对象，并执行 Python GC 和 CUDA cache 清理，尽可能释放 GPU 显存。模型权重文件不会删除，因此下一次加载无需重新下载。

如果模型没有加载，点击“翻译为中文”或“生成学术英文”会提示先加载模型，不会自动占用显存。

## 模型下载与持久化

模型最终保存在宿主机：

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

PaperPolish 使用 Hy-MT2 的翻译提示方式和当前项目配置的推理参数：

```text
temperature = 0.7
top_p = 0.6
top_k = 20
repetition_penalty = 1.05
max_new_tokens = 4096
```

中译英时会把原始英文段落作为 Background Information 提供给模型，帮助模型保持原论文中的专业表达和上下文。

术语规则会使用 terminology instruction，同时 Locked 术语和 LaTeX 内容还会在程序侧替换为占位符，模型输出后再原样恢复。

## 模型管理 API

```text
GET  /api/model/status
POST /api/model/load
POST /api/model/unload
```

状态接口也会返回 GPU 显存信息，方便后续继续扩展成更完整的 DeepSeek OCR 风格模型控制面板。

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
