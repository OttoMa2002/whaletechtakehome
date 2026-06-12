"""百炼 CosyVoice 流式合成 → 包成 Pipecat TTS service。

用 DashScope tts_v2 的 SpeechSynthesizer（已封好 WebSocket + 鉴权，不手搓 ws）。
streaming_call/streaming_complete 在线程里跑，音频通过回调 on_data 增量返回；
回调在 SDK 后台线程，用 call_soon_threadsafe 把 PCM 块投进 asyncio.Queue，再 yield 成帧。
"""

import asyncio
import time
from collections.abc import AsyncGenerator

import dashscope
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer
from loguru import logger
from pipecat.frames.frames import Frame, TTSAudioRawFrame
from pipecat.services.tts_service import TTSService

# 采样率 → CosyVoice PCM 输出格式
_PCM_FORMAT_BY_RATE: dict[int, AudioFormat] = {
    8000: AudioFormat.PCM_8000HZ_MONO_16BIT,
    16000: AudioFormat.PCM_16000HZ_MONO_16BIT,
    22050: AudioFormat.PCM_22050HZ_MONO_16BIT,
    24000: AudioFormat.PCM_24000HZ_MONO_16BIT,
    44100: AudioFormat.PCM_44100HZ_MONO_16BIT,
    48000: AudioFormat.PCM_48000HZ_MONO_16BIT,
}


class CosyVoiceTTSService(TTSService):
    """百炼 CosyVoice flash 的 Pipecat TTS service（流式）。"""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "cosyvoice-v3-flash",
        voice: str = "longxiaochun",
        sample_rate: int = 24000,
        **kwargs,
    ):
        # push_start_frame/push_stop_frames=True：让基类自动包裹 TTSStarted/StoppedFrame
        super().__init__(
            sample_rate=sample_rate,
            push_start_frame=True,
            push_stop_frames=True,
            **kwargs,
        )
        self._api_key = api_key
        self._voice = voice
        self._model = model
        if sample_rate not in _PCM_FORMAT_BY_RATE:
            raise ValueError(f"CosyVoice 不支持的采样率: {sample_rate}")
        self._audio_format = _PCM_FORMAT_BY_RATE[sample_rate]

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        logger.info(f"[TTS] 合成: {text}")
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        class _Callback(ResultCallback):
            def on_data(self, data: bytes) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, data)

            def on_complete(self) -> None:
                loop.call_soon_threadsafe(queue.put_nowait, None)

            def on_error(self, message) -> None:
                logger.warning(f"[TTS] 合成错误: {message}")
                loop.call_soon_threadsafe(queue.put_nowait, None)

        dashscope.api_key = self._api_key
        synthesizer = SpeechSynthesizer(
            model=self._model,
            voice=self._voice,
            format=self._audio_format,
            callback=_Callback(),
        )

        def _drive() -> None:
            synthesizer.streaming_call(text)
            synthesizer.streaming_complete()

        t0 = time.monotonic()
        future = loop.run_in_executor(None, _drive)
        first_chunk = True
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                if first_chunk:
                    logger.info(f"[TTS] 首包延迟 {int((time.monotonic() - t0) * 1000)}ms")
                    first_chunk = False
                yield TTSAudioRawFrame(
                    audio=chunk,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                )
        finally:
            await future
