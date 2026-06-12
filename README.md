# 园区访客语音登记 Agent

语音门卫 agent：来电者打进来，在自然对话中采集 **车牌号 / 来访单位 / 手机号 / 来访事由**，
把结构化登记推送到企业微信群（代表保安）。从接通到推送 < 25 秒。全栈国产、实时音频不出境、开源。

> 架构图、完整部署步骤与环境变量说明在阶段 5 补全。本文件当前为脚手架占位。

## 快速开始（阶段 0）

```bash
# 1. 准备环境变量
cp .env.example .env
# 编辑 .env，至少填入 DASHSCOPE_API_KEY

# 2. 起数据库
docker compose up -d

# 3. 安装依赖
uv sync

# 4. 空跑脚手架
uv run python -m app.main
```

## 技术栈

| 层 | 选择 |
|---|---|
| 编排 | Pipecat（自托管，内置 Silero VAD / 打断） |
| STT | 百炼 Paraformer 实时 |
| LLM | Qwen（OpenAI 兼容端点） |
| TTS | 百炼 CosyVoice flash |
| 音频入口 | 本地音频 + 虚拟声卡（BlackHole） |
| 数据库 | 本地 PostgreSQL（docker-compose） |
| 推送 | 企业微信群机器人 webhook |
| 后端 | FastAPI |

选型与 trade-off 详见 [SELECTION.md](SELECTION.md)。构建顺序见 [PROJECT.md](PROJECT.md)。
