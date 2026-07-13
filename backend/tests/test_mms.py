from __future__ import annotations

import asyncio
from contextlib import nullcontext
import io
from types import SimpleNamespace
import threading
import wave

import pytest

from taigi_news_reader_backend.app import build_service
from taigi_news_reader_backend.config import Settings
from taigi_news_reader_backend.providers import MmsTtsSynthesizer, ProviderError
from taigi_news_reader_backend.providers.mms import (
    TransformersMmsRuntime,
    float_waveform_to_wav,
)


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []
        self.max_samples: list[int] = []

    def synthesize(self, text: str, rate: float, max_samples: int):
        self.calls.append((text, rate))
        self.max_samples.append(max_samples)
        return ([0.0, 0.5, -0.5, 2.0, -2.0], 16_000)


async def test_backend_max_audio_setting_is_wired_into_local_mms():
    service = build_service(Settings(max_audio_bytes=2_048))

    assert isinstance(service.synthesizer, MmsTtsSynthesizer)
    assert service.synthesizer.max_audio_bytes == 2_048
    assert service.synthesizer._max_pcm_samples == 1_002
    await service.aclose()


async def test_mms_runtime_loads_lazily_once_and_forwards_speaking_rate():
    runtime = FakeRuntime()
    loads: list[tuple[str, str]] = []

    def load(model: str, device: str) -> FakeRuntime:
        loads.append((model, device))
        return runtime

    provider = MmsTtsSynthesizer(
        model_name="facebook/mms-tts-nan",
        device="cpu",
        timeout_seconds=1,
        max_audio_bytes=1_024,
        runtime_loader=load,
    )
    assert loads == []

    first = await provider.synthesize("Tsit", 0.75)
    second = await provider.synthesize("Hit", 1.25)

    assert loads == [("facebook/mms-tts-nan", "cpu")]
    assert runtime.calls == [("Tsit", 0.75), ("Hit", 1.25)]
    assert runtime.max_samples == [490, 490]
    assert first.audio.startswith(b"RIFF")
    assert second.audio.startswith(b"RIFF")
    with wave.open(io.BytesIO(first.audio), "rb") as wav:
        assert wav.getframerate() == 16_000
        assert wav.getnframes() == 5


@pytest.mark.parametrize(
    ("samples", "sample_rate"),
    [([], 16_000), ([float("nan")], 16_000), ([0.0], 1_000)],
)
def test_wav_encoder_rejects_invalid_model_output(samples, sample_rate):
    with pytest.raises(ProviderError):
        float_waveform_to_wav(samples, sample_rate)


def test_wav_encoder_enforces_byte_limit_for_sized_and_streaming_samples():
    assert len(
        float_waveform_to_wav(
            [0.0],
            16_000,
            max_audio_bytes=46,
        )
    ) == 46

    with pytest.raises(ProviderError, match="size limit"):
        float_waveform_to_wav(
            [0.0, 0.0],
            16_000,
            max_audio_bytes=46,
        )

    def unbounded_samples():
        while True:
            yield 0.0

    with pytest.raises(ProviderError, match="size limit"):
        float_waveform_to_wav(
            unbounded_samples(),
            16_000,
            max_audio_bytes=48,
        )


def test_transformers_runtime_rejects_tensor_before_tolist_allocation():
    class Waveform:
        tolist_called = False

        def detach(self):
            return self

        def cpu(self):
            return self

        def flatten(self):
            return self

        def numel(self):
            return 100

        def tolist(self):
            self.tolist_called = True
            return [0.0] * 100

    class Encoded:
        def to(self, device):
            return self

    waveform = Waveform()
    parameter = SimpleNamespace(device="cpu")

    class Model:
        config = SimpleNamespace(sampling_rate=16_000)

        def parameters(self):
            return iter((parameter,))

        def __call__(self, **kwargs):
            return SimpleNamespace(waveform=waveform)

    runtime = TransformersMmsRuntime(
        tokenizer=lambda **kwargs: {"input_ids": Encoded()},
        model=Model(),
        torch=SimpleNamespace(inference_mode=nullcontext),
    )

    with pytest.raises(ProviderError, match="size limit"):
        runtime.synthesize("Tsit", 1.0, max_samples=10)

    assert waveform.tolist_called is False


class BlockingRuntime:
    def __init__(self) -> None:
        self.entered = (threading.Event(), threading.Event())
        self.release = (threading.Event(), threading.Event())
        self._calls = 0
        self._calls_lock = threading.Lock()

    def synthesize(self, text: str, rate: float, max_samples: int):
        with self._calls_lock:
            index = self._calls
            self._calls += 1
        if index >= len(self.entered):
            raise AssertionError("unexpected concurrent MMS call")
        self.entered[index].set()
        if not self.release[index].wait(timeout=2):
            raise AssertionError("test did not release MMS runtime")
        return ([0.0], 16_000)


def blocking_provider(runtime: BlockingRuntime, timeout: float) -> MmsTtsSynthesizer:
    return MmsTtsSynthesizer(
        model_name="test/mms",
        device="cpu",
        timeout_seconds=timeout,
        max_audio_bytes=1_024,
        runtime_loader=lambda model, device: runtime,
    )


async def wait_thread_event(event: threading.Event) -> None:
    assert await asyncio.to_thread(event.wait, 1)


async def test_cancelled_call_keeps_single_flight_until_real_worker_exits():
    runtime = BlockingRuntime()
    provider = blocking_provider(runtime, timeout=1)
    first = asyncio.create_task(provider.synthesize("first", 1.0))
    second: asyncio.Task | None = None
    try:
        await wait_thread_event(runtime.entered[0])
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

        second = asyncio.create_task(provider.synthesize("second", 1.0))
        await asyncio.sleep(0.05)
        assert runtime.entered[1].is_set() is False

        runtime.release[0].set()
        await wait_thread_event(runtime.entered[1])
        runtime.release[1].set()
        assert (await second).audio.startswith(b"RIFF")
    finally:
        runtime.release[0].set()
        runtime.release[1].set()
        if second is not None and not second.done():
            second.cancel()
        await asyncio.gather(first, *(tuple((second,)) if second else ()), return_exceptions=True)
        await provider.aclose()


async def test_timed_out_call_keeps_single_flight_until_real_worker_exits():
    runtime = BlockingRuntime()
    provider = blocking_provider(runtime, timeout=0.2)
    first = asyncio.create_task(provider.synthesize("first", 1.0))
    second: asyncio.Task | None = None
    try:
        await wait_thread_event(runtime.entered[0])
        with pytest.raises(ProviderError, match="timed out"):
            await first

        second = asyncio.create_task(provider.synthesize("second", 1.0))
        await asyncio.sleep(0.05)
        assert runtime.entered[1].is_set() is False

        runtime.release[0].set()
        await wait_thread_event(runtime.entered[1])
        runtime.release[1].set()
        assert (await second).audio.startswith(b"RIFF")
    finally:
        runtime.release[0].set()
        runtime.release[1].set()
        if second is not None and not second.done():
            second.cancel()
        await asyncio.gather(first, *(tuple((second,)) if second else ()), return_exceptions=True)
        await provider.aclose()


async def test_waiting_caller_timeout_never_submits_after_gate_later_releases():
    runtime = BlockingRuntime()
    provider = blocking_provider(runtime, timeout=0.1)
    first = asyncio.create_task(provider.synthesize("first", 1.0))
    try:
        await wait_thread_event(runtime.entered[0])
        with pytest.raises(ProviderError, match="timed out"):
            await first

        with pytest.raises(ProviderError, match="timed out"):
            await provider.synthesize("never-submit", 1.0)
        assert runtime.entered[1].is_set() is False

        runtime.release[0].set()
        await provider.aclose()
        await asyncio.sleep(0)
        assert runtime.entered[1].is_set() is False
    finally:
        runtime.release[0].set()
        runtime.release[1].set()
        await asyncio.gather(first, return_exceptions=True)
        await provider.aclose()
