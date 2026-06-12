"""百炼 Paraformer 实时语音识别 → 包成 Pipecat STT service。

DashScope 的 Recognition 走 WebSocket、用后台线程 + 同步回调。Pipecat 这边是 asyncio，
所以回调里用 run_coroutine_threadsafe 把识别结果作为帧投回事件循环。
Paraformer 实时会话在静音/超时后会自行结束，这里检测到结束就在下一帧音频时重连。
"""

import asyncio
from collections.abc import AsyncGenerator

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
)
from pipecat.services.stt_service import STTService
from pipecat.utils.time import time_now_iso8601


class _RecognitionHandler(RecognitionCallback):
    """DashScope 识别回调（运行在 SDK 后台线程）。"""

    def __init__(self, service: "ParaformerSTTService", loop: asyncio.AbstractEventLoop):
        self._service = service
        self._loop = loop

    def on_open(self) -> None:
        logger.debug("Paraformer 会话已建立")

    def on_event(self, result: RecognitionResult) -> None:
        sentence = result.get_sentence()
        if not sentence:
            return
        text = sentence.get("text", "") if isinstance(sentence, dict) else ""
        if not text:
            return
        is_final = RecognitionResult.is_sentence_end(sentence)
        if is_final:
            frame: Frame = TranscriptionFrame(text, "", time_now_iso8601())
            logger.info(f"[STT] 终稿: {text}")
        else:
            frame = InterimTranscriptionFrame(text, "", time_now_iso8601())
        # 从后台线程把帧投回 asyncio 事件循环
        asyncio.run_coroutine_threadsafe(self._service.push_frame(frame), self._loop)

    def on_complete(self) -> None:
        logger.debug("Paraformer 会话完成（静音/超时），将按需重连")
        self._service._mark_session_closed()

    def on_error(self, result: RecognitionResult) -> None:
        logger.warning(f"[STT] 识别错误: {getattr(result, 'message', result)}")
        self._service._mark_session_closed()

    def on_close(self) -> None:
        logger.debug("Paraformer 会话关闭")
        self._service._mark_session_closed()


class ParaformerSTTService(STTService):
    """百炼 Paraformer 实时识别的 Pipecat STT service。"""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "paraformer-realtime-v2",
        sample_rate: int = 16000,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._api_key = api_key
        self._model = model
        self._recognition: Recognition | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session_open = False

    def _mark_session_closed(self) -> None:
        self._session_open = False

    def _start_recognition(self) -> None:
        dashscope.api_key = self._api_key
        handler = _RecognitionHandler(self, self._loop)
        self._recognition = Recognition(
            model=self._model,
            callback=handler,
            format="pcm",
            sample_rate=self.sample_rate,
        )
        self._recognition.start()
        self._session_open = True
        logger.debug(f"启动 Paraformer 识别 model={self._model} sr={self.sample_rate}")

    async def start(self, frame: StartFrame):
        await super().start(frame)
        self._loop = asyncio.get_running_loop()
        self._start_recognition()

    async def stop(self, frame):
        await super().stop(frame)
        self._close_recognition()

    async def cancel(self, frame):
        await super().cancel(frame)
        self._close_recognition()

    def _close_recognition(self) -> None:
        if self._recognition is not None and self._session_open:
            try:
                self._recognition.stop()
            except Exception as e:  # noqa: BLE001
                logger.debug(f"停止 Paraformer 出错（可忽略）: {e}")
        self._recognition = None
        self._session_open = False

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        # 会话已结束（静音/超时）则重连
        if self._recognition is None or not self._session_open:
            self._start_recognition()
        try:
            self._recognition.send_audio_frame(audio)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[STT] 送音频失败，重连: {e}")
            self._session_open = False
        yield None
