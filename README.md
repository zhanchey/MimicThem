# Mimic Them

**一键复刻爆款小红书小姐姐**

使用 AI 技术，自动下载小红书图片、反推提示词、生成变体图片和诗意文案。

![MimicThem Preview](https://img.shields.io/badge/MimicThem-AI%20Clone-purple)

## 功能特点

- **一键操作**：粘贴小红书链接，点击按钮即可开始复刻
- **智能分析**：自动反推图片提示词
- **批量生成**：生成 1 张文生图 + 5 张变体图片
- **诗意文案**：自动生成适合小红书风格的文案和标签
- **实时反馈**：SSE 实时推送处理进度，图片生成后立即展示
- **并行优化**：图片下载和变体生成采用并行处理，大幅提升效率

## 使用局限

- **仅支持图文**：只能处理小红书的图文笔记，不支持视频内容
- **生成结果**：生成的图片是基于 AI 模型创作的新图片，非原图复制
- **API 依赖**：需要配置火山引擎 ARK API Key

## 快速开始

### 1. 获取 API Key

访问 [火山引擎方舟平台](https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey) 获取 API Key。

需要开通以下模型的访问权限：
- **Seed 2.0 Pro** (doubao-seed-2-0-pro-260215) - 用于图片理解和文案生成
- **Seedream 4.5** (doubao-seedream-4-5-251128) - 用于图片生成

### 2. 配置后端

```bash
# 进入后端目录
cd backend

# 创建并激活 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
.\venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 复制配置文件并填写 API Key
cp config.ini.example config.ini
```

编辑 `backend/config.ini`，填入你的 API Key：

```ini
[api]
ARK_API_KEY = your_api_key_here

[generation]
variant_count = 5          # 变体图片数量
image_size = 3072x4096     # 生成图片尺寸
model_id = seedream-4.5    # 使用的模型
watermark = false          # 是否添加水印
```

### 3. 启动后端

```bash
cd backend
source venv/bin/activate  # 激活虚拟环境
python main.py
```

后端服务将在 `http://localhost:8000` 启动。

### 4. 配置前端

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install
```

### 5. 启动前端

```bash
cd frontend
npm run dev
```

前端服务将在 `http://localhost:3000` 启动。

### 6. 开始使用

1. 打开浏览器访问 `http://localhost:3000`
2. 复制一个小红书图文链接
3. 粘贴到输入框
4. 点击「一键复刻」
5. 等待处理完成，查看生成的图片和文案

## 项目结构

```
MimicThem/
├── backend/                # Python 后端
│   ├── api/               # API 路由
│   │   └── routes.py      # FastAPI 路由和 SSE
│   ├── services/          # 核心服务
│   │   ├── xhs_downloader.py  # 小红书下载器
│   │   ├── seed.py        # 大模型服务
│   │   └── seedream.py    # 图片生成服务
│   ├── data/              # 数据存储目录（自动创建）
│   ├── config.ini         # 配置文件（需自行创建）
│   ├── config.ini.example # 配置文件模板
│   ├── main.py            # 后端入口
│   └── requirements.txt   # Python 依赖
├── frontend/              # Next.js 前端
│   ├── src/
│   │   ├── app/          # 页面
│   │   └── components/   # UI 组件
│   └── package.json
├── README.md
└── .gitignore
```

## 工作流程

1. **解析 URL**：支持短链接和长链接
2. **下载图片**：并行下载原始图片
3. **反推提示词**：使用 Seed 2.0 Pro 分析图片生成提示词
4. **生成变体**：生成多个姿势/动作的变体提示词
5. **文生图**：根据提示词生成基础图片
6. **图文生图**：并行生成变体图片（保持人物一致）
7. **生成文案**：创作诗意文案和标签

## 数据存储

每个处理的链接会在 `backend/data/{note_id}/` 下创建独立目录：

```
{note_id}/
├── original/        # 原始图片
│   ├── 1.jpeg
│   └── 2.jpeg
├── generated/       # 生成图片
│   ├── base.png
│   ├── variant_1.png
│   └── ...
└── info.txt         # 文案信息
```

## 技术栈

**后端**
- Python 3.10+
- FastAPI + Uvicorn
- httpx (异步 HTTP)
- OpenAI SDK (火山引擎兼容)
- lxml (HTML 解析)

**前端**
- Next.js 14+
- TypeScript
- Tailwind CSS
- shadcn/ui
- SSE (Server-Sent Events)

## 常见问题

### Q: 后端启动失败？
A: 确保已正确安装依赖并激活虚拟环境。

### Q: 图片生成失败？
A: 检查 API Key 是否正确配置，以及是否有足够的 API 额度。

### Q: 提示"无法解析链接"？
A: 确保粘贴的是有效的小红书图文链接，支持格式：
- `https://www.xiaohongshu.com/explore/xxx`
- `https://www.xiaohongshu.com/discovery/item/xxx`
- `https://xhslink.com/xxx` (短链接)

### Q: 生成的图片和原图不像？
A: AI 生成的是基于提示词的新创作，不是直接复制。效果取决于提示词的准确性。

## 许可证

MIT License

## 免责声明

本项目仅供学习和研究使用。请尊重原创作者的版权，不要将生成的内容用于商业用途或侵权行为。
