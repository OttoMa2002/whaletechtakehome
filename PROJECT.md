# PROJECT.md — 目录结构与构建顺序

## 目录结构

```
voice-gate/
  pyproject.toml            # uv 管理依赖
  docker-compose.yml        # postgres（以后可加 app 服务）
  .env.example              # 提交这个；真正的 .env 不提交
  README.md                 # 架构图 + 部署步骤 + 环境变量（一页内）
  CLAUDE.md                 # 给 coding agent 的操作规则
  docs/
    selection.md            # 选型说明（答辩打分用，见 SELECTION.md）
  src/
    app/
      __init__.py
      main.py               # 入口：组装并启动 pipeline
      config.py             # pydantic-settings 读 .env
      pipeline.py           # Pipecat 管线拼装
      services/
        dashscope_stt.py    # Paraformer 实时识别，包成 Pipecat STT service
        dashscope_tts.py    # CosyVoice 流式合成，包成 Pipecat TTS service
        # LLM 走 OpenAI 兼容端点，用 Pipecat 自带 service，不在这里
      agent/
        prompt.py           # 系统提示 / 对话策略
        tools.py            # submit_registration、lookup_visitor
        harness.py          # 字段校验 / 守话题（G，细节延后）
      db/
        schema.sql          # registrations 表
        repo.py             # 写入登记、按车牌查历史
      push/
        wecom.py            # 企微 webhook POST
      logging_utils.py      # 结构化延迟日志
  tests/
    test_extraction.py      # 文本喂抽取，断言四字段
    test_push.py            # 推送函数
    test_db.py              # 增查 + 回访查
  scripts/
    test_stt.py             # 音频文件 → 文本
    test_tts.py             # 文本 → 音频
```

模块边界保持清楚：管线只管音频流转，agent 管对话和工具，db / push 是纯函数式的副作用层。这样每块能单独测，并发时也不容易出共享状态的 bug。

## 构建顺序（一阶段一阶段，每阶段可测、可人工 commit）

### 阶段 0 — 脚手架
uv 起项目装依赖，docker-compose 起 postgres，写 .env.example，config.py 能读 env，程序能空跑起来。
完成判据：`docker compose up` 起库成功，程序启动不报错。

### 阶段 1 — 音频闭环（本地麦克风）
Pipecat LocalAudioTransport + 内置 VAD，串起 STT（Paraformer）+ LLM（Qwen，先做简单回应）+ TTS（CosyVoice）。
完成判据：对着 Mac 麦克风说话，agent 用语音回你，往返延迟能接受。

### 阶段 2 — 采集 + 推送 + 入库
给 LLM 系统提示和 `submit_registration` 工具。四字段采齐就触发，写 Postgres 并推企微群。
完成判据：一通本地麦克风对话采全信息，群里弹出结构化登记，接通到推送低于 25 秒。

### 阶段 3 — 对话质量 + harness（G）
批量抽取、车牌和手机号复述确认、自然话术；字段校验、守话题。
完成判据：3 轮左右、像真人、关键字段确认无误。

### 阶段 4 — 来电源
先做虚拟声卡（BlackHole）+ 微信语音接入；再做 iPhone Continuity 真电话。
完成判据：朋友或二号微信打进来能走通；Continuity 真电话 demo 能跑。

### 阶段 5 — 计时 + 文档
延迟日志 + 多轮验证稳定低于 25 秒；写 README（架构图 + 部署 + env）和选型说明。
完成判据：证据齐、文档齐。

### 阶段 6 — 加分项（有富余时间才做）
查询 agent、回访识别、多路并发。回访沿用同一张表，不改 schema。

每阶段结束人工 commit 一次，message 写清这阶段做了什么。
