"""Pipecat 管线拼装：LocalAudioTransport + Silero VAD + STT + Qwen + TTS。

阶段 3：对话结构重构。预合成开场白一句批量问；挂 submit_registration / lookup_company 工具；
登记成功后由 EndAfterRegistration 在道别播完时推 EndTaskFrame 优雅收尾。
"""

import numpy as np
from loguru import logger
from pipecat.frames.frames import (
    EndTaskFrame,
    Frame,
    InputAudioRawFrame,
    TTSSpeakFrame,
    TTSStoppedFrame,
)
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.qwen.llm import QwenLLMService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from app import logging_utils
from app.agent.prompt import GREETING, SYSTEM_PROMPT
from app.agent.tools import build_tools_schema, register_tools
from app.config import Settings
from app.services.dashscope_stt import ParaformerSTTService
from app.services.dashscope_tts import CosyVoiceTTSService, synthesize_to_pcm


# 首声触发阈值：人声 RMS 远高于静音(实测人声 550–990、线路静音≈0)，200 区分度足够
_FIRST_SOUND_RMS = 200.0
_FIRST_SOUND_SUSTAIN_MS = 150.0


class ConnectionDetector(FrameProcessor):
    """首声触发（电话/微信用）：来电者一出声（输入 RMS 越过人声阈值并持续）即触发一次
    "门岗问候+计时起点"，之后自我关闭。让接通方听到引导语、把计时起点对齐到真实交互开始。

    为何不嗅底噪：标定发现微信/电话 DTX 使"接通但静音"时 RMS=0（与未接通无异），只能嗅人声。
    生产形态有电信信令(SIP 200 OK 等)可在静音中拿接通事件、门岗对静音先开口——消费级 App 的固有限制。
    """

    def __init__(self, *, rms_threshold: float, sustain_ms: float) -> None:
        super().__init__()
        self._threshold = rms_threshold
        self._sustain_ms = sustain_ms
        self._on_connect = None
        self._triggered = False
        self._active_ms = 0.0

    def set_on_connect(self, cb) -> None:
        self._on_connect = cb

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if self._on_connect and not self._triggered and isinstance(frame, InputAudioRawFrame):
            samples = np.frombuffer(frame.audio, dtype=np.int16)
            if samples.size:
                rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
                frame_ms = samples.size / max(1, frame.num_channels) / frame.sample_rate * 1000
                if rms >= self._threshold:
                    self._active_ms += frame_ms
                    if self._active_ms >= self._sustain_ms:
                        self._triggered = True
                        logger.info(f"[首声触发] 来电者出声(RMS≈{rms:.0f}) → 门岗问候+计时")
                        await self._on_connect()
                else:
                    self._active_ms = 0.0  # 低于阈值即重置，要求"持续出声"而非偶发噪点
        await self.push_frame(frame, direction)


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


def _resolve_device_index(name: str, *, want_input: bool) -> int | None:
    """按设备名子串匹配 PyAudio 设备 index；留空或找不到返回 None（系统默认）。

    阶段4：输入锁 BlackHole 2ch（访客声音）、输出锁 BlackHole 16ch（回程给微信麦克风），
    避免走系统默认导致 TTS 自听成环。
    """
    if not name:
        return None
    import pyaudio

    pa = pyaudio.PyAudio()
    try:
        ch_key = "maxInputChannels" if want_input else "maxOutputChannels"
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            if name.lower() in d["name"].lower() and d[ch_key] > 0:
                logger.info(f"音频设备解析：{'输入' if want_input else '输出'} '{name}' → [{i}] {d['name']}")
                return i
    finally:
        pa.terminate()
    logger.warning(f"未找到匹配 '{name}' 的{'输入' if want_input else '输出'}设备，回退系统默认")
    return None


def build_worker(settings: Settings) -> PipelineWorker:
    """组装管线并返回 PipelineWorker（须在 asyncio 上下文中创建 runner 后运行）。"""
    stt_rate = settings.stt_sample_rate
    tts_rate = settings.tts_sample_rate

    in_idx = _resolve_device_index(settings.audio_input_device, want_input=True)
    out_idx = _resolve_device_index(settings.audio_output_device, want_input=False)

    # —— 本地音频入口 + Silero VAD（输入采样率必须 8k/16k）——
    # 阶段4：可锁定虚拟声卡（BlackHole）走微信语音；留空则系统默认（本地麦）。
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_in_sample_rate=stt_rate,
            audio_in_channels=1,
            audio_out_enabled=True,
            audio_out_sample_rate=tts_rate,
            audio_out_channels=1,
            input_device_index=in_idx,
            output_device_index=out_idx,
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

    # —— 轮次检测：把 Smart Turn 的最大静音等待从默认 3s 压到 turn_stop_secs(默认0.8)，每轮更跟手 ——
    user_params = LLMUserAggregatorParams(
        user_turn_strategies=UserTurnStrategies(
            stop=[
                TurnAnalyzerUserTurnStopStrategy(
                    turn_analyzer=LocalSmartTurnAnalyzerV3(
                        params=SmartTurnParams(stop_secs=settings.turn_stop_secs)
                    )
                )
            ]
        )
    )
    aggregators = LLMContextAggregatorPair(context, user_params=user_params)
    end_after = EndAfterRegistration(session)

    # 问候时机：电话/微信用首声触发(嗅到来电者出声再问候)；本地启动即问候。
    detector = (
        ConnectionDetector(rms_threshold=_FIRST_SOUND_RMS, sustain_ms=_FIRST_SOUND_SUSTAIN_MS)
        if settings.greet_on_first_sound
        else None
    )

    processors = [transport.input()]            # 麦克风/线路音频帧
    if detector is not None:
        processors.append(detector)             # → 嗅首声(触发问候+计时)
    processors += [
        stt,                     # → 识别文本
        aggregators.user(),      # → 写入用户上下文
        llm,                     # → Qwen 流式回复（含工具调用）
        tts,                     # → 合成音频帧
        transport.output(),      # → 扬声器
        aggregators.assistant(), # → 写入助手上下文
        end_after,               # → 登记完道别后优雅结束
    ]
    pipeline = Pipeline(processors)

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=stt_rate,
            audio_out_sample_rate=tts_rate,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    async def _greet_and_time() -> None:
        """问候 + 计时起点（接通=门岗开口）。"""
        logging_utils.start_call()
        await worker.queue_frames([TTSSpeakFrame(GREETING)])

    if detector is not None:
        detector.set_on_connect(_greet_and_time)

        @worker.event_handler("on_pipeline_started")
        async def _ready(worker, frame):  # noqa: ANN001
            logger.info("管线启动，等待来电者首声（首声触发问候+计时）……")
    else:

        @worker.event_handler("on_pipeline_started")
        async def _greet(worker, frame):  # noqa: ANN001
            logger.info("管线启动，门岗主动问候（预合成开场白）")
            await _greet_and_time()

    return worker
