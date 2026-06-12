# PROGRESS.md —— 项目进度与交接（阶段 0–3 完成）

> 给"新开对话无缝衔接"用：读完这份 + CLAUDE.md + PROJECT.md + SELECTION.md 即可接上。
> 规矩：**commit 由人手动做，agent 不要自动 commit**；偏离 CLAUDE.md 锁定栈前先问人；每阶段做完停下等确认；本项目对话用中文。

## 一句话
语音门岗 agent：来电者打进来，自然对话采集 **车牌/来访单位/手机号/来访事由**，结构化登记推送到企业微信群。接通到推送 < 25s。全栈国产（阿里云百炼），开源。

## 当前状态：阶段 0–3 完成，阶段 4 来电源已打通（微信音质受限，见下）
| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 脚手架 | uv/依赖/postgres/config/空跑 | ✅ 已 commit |
| 1 音频闭环 | 麦→Paraformer STT→Qwen→CosyVoice TTS→扬声器 | ✅ 已 commit |
| 2 数据通路 | submit_registration 工具→写库→推企微 + 计时埋点 | ✅ 已 commit |
| 3 对话质量 | 重构对话结构压时间、公司名单匹配、优雅收尾 | ✅ 待人工 commit |
| 4 来电源 | BlackHole 虚拟声卡 + 微信语音：端到端**全程跑通**（STT/对话/名单/复述/入库/推企微/优雅收尾都在线工作）。**唯一遗留：访客听到的门岗 TTS 被微信麦克风 DSP 弄糊**（详见「阶段4 音质坑」），属微信内部限制、非本系统问题。Continuity 真电话未做。 | 🟡 通路达成/音质受微信限制 |
| 5 计时+文档 | 多轮验证<25s、README/架构图、ASR鲁棒性调优 | ⬜ 下一步 |
| 6 加分项 | 查询agent/回访识别/多路并发 | ⬜ |

## 锁定技术栈（不要替换）
Python + uv｜编排 Pipecat **1.3.0**（自托管，内置 Silero VAD）｜STT 百炼 Paraformer 实时（自写 service）｜LLM Qwen 走 OpenAI 兼容端点（用 pipecat 自带 QwenLLMService）｜TTS 百炼 CosyVoice flash（自写 service，用 DashScope SDK）｜本地音频 LocalAudioTransport｜PostgreSQL(docker)｜企微 webhook｜FastAPI。三层语音/LLM 共用同一把 `DASHSCOPE_API_KEY`。

## 关键事实 / 踩过的坑（重要，省得重查）
- **TTS 音色**：`cosyvoice-v3-flash` 不认 v1 音色名；用 **`longxiaochun_v3`**（v3 专属音色：longanyang/longanhuan/longxiaochun_v3/longcheng_v3）。
- **STT 模型名**：`paraformer-realtime-16k-v2` **不存在**；本地麦 16k 用 **`paraformer-realtime-v2`**；电话 8k 用 `paraformer-realtime-8k-v2`。
- **采样率**：本地麦 STT 16k / TTS 输出 24k，全程不重采样；阶段 4 接电话切 8k。
- **Pipecat 1.3.0 API**（跨版本变化大）：运行用 `WorkerRunner`+`PipelineWorker`（`PipelineRunner` 已废弃别名）；上下文 `LLMContext`+`LLMContextAggregatorPair`；自写 STT 重写 `run_stt(audio)`、TTS 重写 `run_tts(text, context_id)`；工具 `FunctionSchema`/`ToolsSchema`+`llm.register_function`，handler 收 `FunctionCallParams`、`await params.result_callback(result)`；优雅结束向**上游** push `EndTaskFrame`。
- **DashScope 语音 SDK 是线程+同步回调**：STT/TTS 回调里用 `run_coroutine_threadsafe`/`call_soon_threadsafe` 投回 asyncio。Paraformer 实时会话静音/超时自停，`run_stt` 里检测到就重连。
- **回声**：本地外放会被麦克风收回（bot 听到自己）→ 真人测试**必须戴耳机**。
- **密钥**：`.env` 不进仓库（`.gitignore` 挡了 `.env`、`scripts/out_*.wav`、`.venv`）。
- **环境**：uv 装在 `~/.local/bin`（曾因 `~/.local/share` 被 root 占用、手动 chown 修过）；postgres 用 `docker compose up -d`。

## 阶段 3 的对话设计（已确认并实现）
- **开场白**（预合成缓存、接通直接播、跳过首句 LLM+TTS）：「您好，园区门岗。请问您车牌号多少，找哪家公司、办什么事儿？」开场白语速单独提到 1.45 → 实测 **4.1s**；对话语速 1.15。
- **复述+秒确认**（**守 CLAUDE.md，不"边说边触发"**）：四字段齐 → 一次简洁复述（数字自然分组念）以"对吧？"收尾 → 来访者"对"后才 `submit_registration`。确认前绝不入库/推送。
- **公司名核对**：`lookup_company` 工具 → `agent/roster.py` 拼音模糊匹配（pypinyin+difflib）→ high 折进复述 / fuzzy 单独快确认 / none 按原样记。租户名单：蓝色鲸鱼科技、远峰物流、恒达机械、普瑞医疗器械、星河电子。
- **手机号必填**、**中途纠错只补单字段**。
- **优雅收尾**：登记成功后道别，`EndAfterRegistration` 处理器在道别播完(TTSStoppedFrame)推 `EndTaskFrame` 自动结束会话（真挂电话等阶段 4）。
- **校验门（第二道网）**：`submit_registration` 内手机号硬校验(`^1\d{10}$`)、车牌宽松（仅非空+极短才驳，避免误杀新能源/使领馆等格式）、四字段齐全。

## 性能（实测，每轮 agent 延迟很好）
- Qwen TTFB 0.36–1.2s；CosyVoice TTS 首包 ~460–530ms；STT 终稿 ~1.4s。
- "接通→推送"总耗时打在 `logging_utils`：`[计时] 接通→推送 总耗时 X.XXs`。
- **25s 口径（已定死）**：接通(agent开口)到企微发出、去振铃的整段**墙钟，含来访者说话**。达标证据 = 一通配合的来访者、干净对话压进 25s（录像）+ 每轮延迟日志辅助。结构已支持；真人测试若有 ASR 误识重报会超，标准语音一轮可进。

## 目录 / 关键文件
```
src/app/
  main.py            入口：asyncio 起 WorkerRunner
  config.py          pydantic-settings 读 .env（含 database_url / asyncpg_dsn）
  pipeline.py        管线拼装 + 预合成开场白 + EndAfterRegistration 优雅结束
  logging_utils.py   结构化日志 + 接通→推送计时(start_call/mark_pushed)
  services/
    dashscope_stt.py Paraformer 实时 → Pipecat STT（线程回调+自动重连）
    dashscope_tts.py CosyVoice 流式 → Pipecat TTS（开场白缓存 + speech_rate + synthesize_to_pcm）
  agent/
    prompt.py        GREETING + SYSTEM_PROMPT（阶段3版）
    tools.py         submit_registration / lookup_company + 注册
    roster.py        租户名单 + 拼音模糊匹配
  db/
    schema.sql       registrations 表
    repo.py          asyncpg 写入/按车牌查
  push/wecom.py      企微 webhook(markdown 卡片)
tests/   test_db.py(增查) test_push.py(格式+真实推送,默认skip)
scripts/ test_stt.py test_tts.py（独立验证两层语音）
docker-compose.yml  postgres16（挂 schema.sql 初始化）
```

## 怎么跑
```bash
docker compose up -d                 # 起库
uv sync                              # 装依赖
cp .env.example .env                 # 填 DASHSCOPE_API_KEY + WECOM_WEBHOOK_URL
uv run python -m app.main            # 戴耳机，对麦说话走一通登记
uv run pytest -q                     # 测试（test_push 真实推送需 RUN_WECOM_PUSH=1）
uv run python scripts/test_tts.py    # 单独验 TTS
uv run python scripts/test_stt.py    # 单独验 STT（自洽往返）
```

## 阶段 4 实现与音质坑（已做）
**怎么接的**：BlackHole 装两块（2ch + 16ch，brew cask；驱动加载后 `sudo killall coreaudiod` 即出现，免重启）。微信只认系统默认设备、无法 App 内选设备，所以靠虚拟声卡两条总线做全双工：
- 系统输出 = 多输出设备「门岗监听」(= BlackHole 16ch + MacBook扬声器做监听) → 微信播放的**访客声音**进 16ch；Pipecat 输入读 16ch。
- 系统输入 = BlackHole 2ch → Pipecat 输出(TTS)写 2ch，微信当**麦克风**读 2ch 发给访客。
- 代码侧：`config.py` 加 `AUDIO_INPUT_DEVICE`/`AUDIO_OUTPUT_DEVICE`（按设备名子串匹配 PyAudio index，留空=系统默认=本地麦，保住阶段1-3）；`pipeline.py` 的 `_resolve_device_index` 解析后锁进 `LocalAudioTransportParams.input_device_index/output_device_index`。当前 `.env`：输入 16ch / 输出 2ch。
- 采样率：`TTS_SAMPLE_RATE` 从 24000 改 **48000**（CosyVoice 原生支持），对齐声卡名义率 48k，输出路径零重采样。STT 仍 16k（`paraformer-realtime-v2`）；微信非真 PSTN、是数字音频经声卡，**不需要切 8k**（8k 那条留给真 PSTN）。

**端到端结果**：5 通微信语音全部跑通——STT 完美、批量抽取、`lookup_company` 名单匹配（连"蓝色金鱼→蓝色鲸鱼科技"误识都纠回）、复述确认、`submit_registration` 入库、推企微、优雅收尾自动挂断。每轮 Qwen TTFB 0.4–0.8s、TTS 首包 460–640ms，延迟很好。

**音质坑（未解决，判定为微信内部限制，非本系统问题）**：访客听到的门岗 TTS **稀烂/串道/嘈杂**。排查结论：
- BlackHole 环回测试（自播自录算互相关）：2ch 与 16ch **都 1.000 完美无损** → 我们的管线和声卡链路干净。
- 换设备（2ch↔16ch）、换采样率（24k↔48k）四种组合都烂 → 变量都在我方动过，无效。
- 访客**上行**语音（同样过微信编码）STT 识别完美 → 微信语音编码本身不毁音质。
- 结论：毁音质的是**微信「语音通话」对麦克风输入的 DSP**（降噪/AGC/AEC/窄带语音编码，为真人真麦调的），把从虚拟麦灌进去的合成语音当噪声/回声处理。**微信内部，关不掉**。

**计时口径错位（待修，若继续做阶段4才需要）**：开场白+`start_call()` 挂在 app 启动那刻（`on_pipeline_started`），但微信是 app 起好后才拨入接通，中间空档被计进总耗时 → 实测 98–118s 虚高超标（真实"接通→推送"约 16s，达标）。修法：方案B 手动触发——app 启动不自动问候，Mac 接起后按回车才问候+计时同起。**未实施**。

**下一步若重启阶段4**：(1) Continuity 真电话可能音质更好（走真实蜂窝、不经微信 DSP，窄带但通常干净；但 TTS 仍经虚拟麦灌 iPhone、运营商侧也可能有 DSP，且 Continuity 需两台苹果设备同网、不稳）。(2) 修计时口径（方案B）。(3) 真挂电话/会话生命周期完善。

## 已知待办 / 推迟项
- **ASR 鲁棒性**（阶段 5）：车牌"沪A→互微"、快速报手机号"→我不知道"等误识。**热词偏置已调研：可行但不划算**（车牌开放集合、偏置易帮倒忙；公司名已被 roster 覆盖），并入阶段 5 整体调优。复述确认门已能接住这些误识、不产生错误数据。
- README/架构图/选型文档归档（阶段 5）。
- 回访识别/查询 agent/多路并发（阶段 6，回访沿用同一张表不改 schema）。

## 提醒
- 测试会往企微群发真实消息、往库写数据。开新一通前可清表：`docker compose exec postgres psql -U voicegate -d voicegate -c "TRUNCATE registrations RESTART IDENTITY;"`（只清数据，schema 不动）。
