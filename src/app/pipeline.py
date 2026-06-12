"""Pipecat 管线拼装：LocalAudioTransport + Silero VAD + STT + Qwen + TTS。

阶段 3：对话结构重构。预合成开场白一句批量问；挂 submit_registration / lookup_company 工具；
登记成功后由 EndAfterRegistration 在道别播完时推 EndTaskFrame 优雅收尾。
"""

from loguru import logger
from pipecat.frames.frames import EndTaskFrame, Frame, TTSSpeakFrame, TTSStoppedFrame
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.qwen.llm import QwenLLMService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

from app import logging_utils
from app.agent.prompt import GREETING, SYSTEM_PROMPT
from app.agent.tools import build_tools_schema, register_tools
from app.config import Settings
from app.services.dashscope_stt import ParaformerSTTService
from app.services.dashscope_tts import CosyVoiceTTSService, synthesize_to_pcm


class EndAfterRegistration(FrameProcessor):
    """登记成功后，在门岗道别那句播完（TTSStoppedFrame）时优雅结束会话。"""

    def __init__(self, state: dict) -> None:
        super().__init__()
        self._state = state

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if self._state.get("registered") and isinstance(frame, TTSStoppedFrame):
            self._state["registered"] = False
            logger.info("登记完成且道别播完，优雅结束会话")
            await self.push_frame(EndTaskFrame(), FrameDirection.UPSTREAM)


def build_worker(settings: Settings) -> PipelineWorker:
    """组装管线并返回 PipelineWorker（须在 asyncio 上下文中创建 runner 后运行）。"""
    stt_rate = settings.stt_sample_rate
    tts_rate = settings.tts_sample_rate

    # —— 本地音频入口 + Silero VAD（输入采样率必须 8k/16k）——
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_in_sample_rate=stt_rate,
            audio_in_channels=1,
            audio_out_enabled=True,
            audio_out_sample_rate=tts_rate,
            audio_out_channels=1,
            vad_analyzer=SileroVADAnalyzer(sample_rate=stt_rate),
        )
    )

    # —— STT：百炼 Paraformer 实时（自写封装）——
    stt = ParaformerSTTService(
        api_key=settings.dashscope_api_key,
        model=settings.stt_model,
        sample_rate=stt_rate,
    )

    # —— LLM：Qwen，走 OpenAI 兼容端点（用 pipecat 自带 service，开 streaming）——
    llm = QwenLLMService(
        api_key=settings.dashscope_api_key,
        base_url=settings.llm_base_url,
        settings=QwenLLMService.Settings(model=settings.llm_model),
    )

    # —— 预合成固定开场白（启动时合成一次，接通直接播，省首句 TTS 网络合成）——
    logger.info("预合成开场白……")
    greeting_pcm = synthesize_to_pcm(
        api_key=settings.dashscope_api_key,
        model=settings.tts_model,
        voice=settings.tts_voice,
        sample_rate=tts_rate,
        text=GREETING,
        speech_rate=settings.tts_greeting_speech_rate,
    )
    greeting_secs = len(greeting_pcm) / 2 / tts_rate
    logger.info(
        f"开场白预合成完成（{len(greeting_pcm)} 字节，约 {greeting_secs:.1f}s "
        f"@语速{settings.tts_greeting_speech_rate}）"
    )

    # —— TTS：百炼 CosyVoice flash（自写封装，带开场白缓存）——
    tts = CosyVoiceTTSService(
        api_key=settings.dashscope_api_key,
        model=settings.tts_model,
        voice=settings.tts_voice,
        sample_rate=tts_rate,
        speech_rate=settings.tts_speech_rate,
        greeting_text=GREETING,
        greeting_pcm=greeting_pcm,
    )

    # —— 对话上下文（挂工具）+ 用户/助手聚合器 ——
    context = LLMContext(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}],
        tools=build_tools_schema(),
    )

    # 会话状态：登记成功置位，供优雅收尾用
    session = {"registered": False}
    register_tools(llm, on_registered=lambda: session.__setitem__("registered", True))
    aggregators = LLMContextAggregatorPair(context)
    end_after = EndAfterRegistration(session)

    pipeline = Pipeline(
        [
            transport.input(),       # 麦克风音频帧
            stt,                     # → 识别文本
            aggregators.user(),      # → 写入用户上下文
            llm,                     # → Qwen 流式回复（含工具调用）
            tts,                     # → 合成音频帧
            transport.output(),      # → 扬声器
            aggregators.assistant(), # → 写入助手上下文
            end_after,               # → 登记完道别后优雅结束
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=stt_rate,
            audio_out_sample_rate=tts_rate,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @worker.event_handler("on_pipeline_started")
    async def _greet(worker, frame):  # noqa: ANN001
        logger.info("管线启动，门岗主动问候（预合成开场白）")
        logging_utils.start_call()  # 接通=门岗开始说话，计时起点
        await worker.queue_frames([TTSSpeakFrame(GREETING)])

    return worker
