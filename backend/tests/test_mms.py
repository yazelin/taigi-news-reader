from __future__ import annotations

import io
import wave

import pytest

from taigi_news_reader_backend.providers import MmsTtsSynthesizer, ProviderError
from taigi_news_reader_backend.providers.mms import float_waveform_to_wav


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def synthesize(self, text: str, rate: float):
        self.calls.append((text, rate))
        return ([0.0, 0.5, -0.5, 2.0, -2.0], 16_000)


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
        runtime_loader=load,
    )
    assert loads == []

    first = await provider.synthesize("Tsit", 0.75)
    second = await provider.synthesize("Hit", 1.25)

    assert loads == [("facebook/mms-tts-nan", "cpu")]
    assert runtime.calls == [("Tsit", 0.75), ("Hit", 1.25)]
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
