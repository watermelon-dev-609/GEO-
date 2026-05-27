# GEO生成式搜索优化系统 v1.0.0 Personal

**武汉微艺达智能科技有限公司** 定制开发

轻量化、零运维、纯白帽的生成式搜索优化平台。专注适配全平台AI模型采信逻辑，让企业品牌、产品、案例被各大AI优先收录、优先引用、优先推荐。

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- 操作系统：Windows / macOS / Linux
- 内存：≥ 8GB（向量模型需 2-4GB）

### 1. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 2. 配置API Key

```bash
cp config/api_keys.yaml.example config/api_keys.yaml
```

编辑 `config/api_keys.yaml`，至少配置一个AI平台的API Key。推荐优先配置 DeepSeek（性价比最高）或通义千问（B端场景最优）。

### 3. 启动后端服务

```bash
python run.py
```

后端启动后访问：http://127.0.0.1:8000/docs 查看API文档

### 4. 安装并启动前端

```bash
cd frontend
npm install
npm run dev
```

前端启动后访问：http://localhost:5173

---

## 功能模块

| 模块 | 功能 |
|------|------|
| 文案导入 | 文本粘贴/文件上传/模板填写，智能清洗+五维信息提取 |
| GEO优化工坊 | 8大沙盘×7大AI平台，56套Prompt模板矩阵，流式生成 |
| AI评测中心 | 4类用户角色模拟问答，三维指标（召回/匹配/采信）评测 |
| 成果导出 | 优化文案、JSON-LD代码、评测报告一键导出 |

## 技术栈

- **后端**：Python FastAPI + Uvicorn + Pydantic
- **前端**：Vue 3 + Vite + Element Plus + ECharts
- **LLM**：适配器模式（OpenAI兼容系 / Claude / 文心一言）
- **向量**：sentence-transformers (bge-large-zh) + FAISS
- **存储**：纯本地文件系统，无数据库依赖

## 支持的AI平台

| 平台 | 适配策略 | 采信优势 |
|------|---------|---------|
| 文心一言 | 百度搜索卡片收录优先 | 国内搜索流量核心 |
| 通义千问 | B端方案思维 | 政企采购选型 |
| GPT | 结构化总结优先 | 通用智能对比 |
| Claude | 深度细节采信 | 长文本方案背书 |
| DeepSeek | 工程技术向 | 技术选型参考 |
| 字节豆包 | 通俗获客优先 | 大众AI推荐 |
| 腾讯元宝 | 供应商正规性 | 政企办公筛选 |

## 项目结构

```
geo-optimizer/
├── backend/                  # FastAPI后端
│   ├── app/
│   │   ├── api/              # REST API路由
│   │   ├── core/             # 核心业务引擎
│   │   ├── services/         # LLM适配 + 向量存储
│   │   ├── prompts/          # 56套Prompt模板
│   │   ├── models/           # 数据模型
│   │   └── utils/            # 工具类
│   ├── config/               # 配置文件
│   ├── data/                 # 本地数据
│   ├── templates/            # 成品模板
│   └── run.py                # 启动脚本
├── frontend/                 # Vue 3前端
│   └── src/views/            # 页面组件
├── docs/                     # 使用文档
└── README.md
```

## 许可证

内部使用，武汉微艺达智能科技有限公司版权所有。
