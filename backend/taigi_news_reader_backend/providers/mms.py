"""Lazy Meta MMS VITS provider that emits in-memory WAV audio."""

from __future__ import annotations

import asyncio
from array import array
from collections.abc import Callable, Iterable
from dataclasses import dataclass
import io
import math
import sys
import threading
from typing import Protocol
import wave

from .base import AudioResult, ProviderError


class MmsRuntime(Protocol):
    def synthesize(self, text: str, rate: float) -> tuple[Iterable[float], int]: ...


@dataclass(slots=True)
class TransformersMmsRuntime:
    tokenizer: object
    model: object
    torch: object

    @classmethod
    def load(cls, model_name: str, device: str) -> "TransformersMmsRuntime":
        try:
            import torch
            from transformers import VitsModel, VitsTokenizer
        except ImportError as exc:
            raise ProviderError(
                "MMS dependencies are missing; install the backend with the 'tts' extra"
            ) from exc

        if device.startswith("cuda") and not torch.cuda.is_available():
            raise ProviderError(f"configured MMS device {device!r} is unavailable")
        try:
            tokenizer = VitsTokenizer.from_pretrained(model_name)
            model = VitsModel.from_pretrained(model_name).to(device)
            model.eval()
        except Exception as exc:
            raise ProviderError(f"could not load MMS model {model_name!r}") from exc
        return cls(tokenizer=tokenizer, model=model, torch=torch)

    def synthesize(self, text: str, rate: float) -> tuple[Iterable[float], int]:
        try:
            encoded = self.tokenizer(text=text, return_tensors="pt")
            device = next(self.model.parameters()).device
            encoded = {key: value.to(device) for key, value in encoded.items()}
            with self.torch.inference_mode():
                output = self.model(**encoded, speaking_rate=rate)
            samples = output.waveform.detach().cpu().flatten().tolist()
            sample_rate = int(self.model.config.sampling_rate)
        except Exception as exc:
            raise ProviderError("MMS speech synthesis failed") from exc
        if not samples or sample_rate <= 0:
            raise ProviderError("MMS returned empty or invalid audio")
        return samples, sample_rate


def float_waveform_to_wav(samples: Iterable[float], sample_rate: int) -> bytes:
    if not 8_000 <= sample_rate <= 192_000:
        raise ProviderError("speech provider returned an invalid sample rate")
    pcm = array("h")
    for sample in samples:
        value = float(sample)
        if not math.isfinite(value):
            raise ProviderError("speech provider returned a non-finite audio sample")
        pcm.append(round(max(-1.0, min(1.0, value)) * 32_767))
    if not pcm:
        raise ProviderError("speech provider returned empty audio")
    if sys.byteorder != "little":
        pcm.byteswap()
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return output.getvalue()


class MmsTtsSynthesizer:
    def __init__(
        self,
        *,
        model_name: str,
        device: str,
        timeout_seconds: float,
        runtime_loader: Callable[[str, str], MmsRuntime] | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.timeout_seconds = timeout_seconds
        self._runtime_loader = runtime_loader or TransformersMmsRuntime.load
        self._runtime: MmsRuntime | None = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return f"huggingface:{self.model_name}"

    def _synthesize_sync(self, text: str, rate: float) -> bytes:
        # The lock both makes lazy initialization race-free and keeps inference
        # serialized: a single VITS model instance is not assumed thread-safe.
        with self._lock:
            if self._runtime is None:
                self._runtime = self._runtime_loader(self.model_name, self.device)
            samples, sample_rate = self._runtime.synthesize(text, rate)
            return float_waveform_to_wav(samples, sample_rate)

    async def synthesize(self, text: str, rate: float) -> AudioResult:
        try:
            audio = await asyncio.wait_for(
                asyncio.to_thread(self._synthesize_sync, text, rate),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            raise ProviderError("MMS speech synthesis timed out") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("MMS speech synthesis failed") from exc
        return AudioResult(audio=audio)

    async def aclose(self) -> None:
        return None
