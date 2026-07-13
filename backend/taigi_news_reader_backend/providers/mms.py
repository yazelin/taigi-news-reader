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


_WAV_HEADER_BYTES = 44
_PCM_SAMPLE_BYTES = 2


class MmsRuntime(Protocol):
    def synthesize(
        self,
        text: str,
        rate: float,
        max_samples: int,
    ) -> tuple[Iterable[float], int]: ...


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

    def synthesize(
        self,
        text: str,
        rate: float,
        max_samples: int,
    ) -> tuple[Iterable[float], int]:
        try:
            encoded = self.tokenizer(text=text, return_tensors="pt")
            device = next(self.model.parameters()).device
            encoded = {key: value.to(device) for key, value in encoded.items()}
            with self.torch.inference_mode():
                output = self.model(**encoded, speaking_rate=rate)
            waveform = output.waveform.detach()
            sample_count = int(waveform.numel())
            if sample_count > max_samples:
                raise ProviderError(
                    "MMS speech audio exceeds the configured size limit"
                )
            sample_rate = int(self.model.config.sampling_rate)
            if not 8_000 <= sample_rate <= 192_000:
                raise ProviderError("MMS returned an invalid sample rate")
            # Check the tensor while it is still compact. Calling .tolist() on
            # an unbounded waveform could otherwise allocate a huge Python list
            # before the WAV encoder gets a chance to reject it.
            samples = waveform.cpu().flatten().tolist()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("MMS speech synthesis failed") from exc
        if not samples or sample_rate <= 0:
            raise ProviderError("MMS returned empty or invalid audio")
        return samples, sample_rate


def float_waveform_to_wav(
    samples: Iterable[float],
    sample_rate: int,
    *,
    max_audio_bytes: int = 25 * 1024 * 1024,
) -> bytes:
    if not 8_000 <= sample_rate <= 192_000:
        raise ProviderError("speech provider returned an invalid sample rate")
    if max_audio_bytes < _WAV_HEADER_BYTES + _PCM_SAMPLE_BYTES:
        raise ProviderError("configured audio size limit is too small")
    max_samples = (max_audio_bytes - _WAV_HEADER_BYTES) // _PCM_SAMPLE_BYTES
    try:
        known_length = len(samples)  # type: ignore[arg-type]
    except TypeError:
        known_length = None
    if known_length is not None and known_length > max_samples:
        raise ProviderError("speech provider audio exceeds the configured size limit")
    pcm = array("h")
    for sample in samples:
        if len(pcm) >= max_samples:
            raise ProviderError("speech provider audio exceeds the configured size limit")
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
    encoded = output.getvalue()
    if len(encoded) > max_audio_bytes:
        raise ProviderError("speech provider audio exceeds the configured size limit")
    return encoded


class MmsTtsSynthesizer:
    def __init__(
        self,
        *,
        model_name: str,
        device: str,
        timeout_seconds: float,
        max_audio_bytes: int,
        runtime_loader: Callable[[str, str], MmsRuntime] | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.timeout_seconds = timeout_seconds
        self.max_audio_bytes = max_audio_bytes
        if max_audio_bytes < _WAV_HEADER_BYTES + _PCM_SAMPLE_BYTES:
            raise ValueError("max_audio_bytes is too small for WAV audio")
        self._max_pcm_samples = (
            max_audio_bytes - _WAV_HEADER_BYTES
        ) // _PCM_SAMPLE_BYTES
        self._runtime_loader = runtime_loader or TransformersMmsRuntime.load
        self._runtime: MmsRuntime | None = None
        self._lock = threading.Lock()
        # asyncio cancellation cannot stop a function already running in a
        # worker thread. This gate stays held until that real worker exits,
        # even when its HTTP/job caller times out or is cancelled, so repeated
        # requests cannot pile up concurrent or queued MMS inference work.
        self._inference_gate = asyncio.Lock()
        self._detached_workers: set[asyncio.Task[bytes]] = set()

    @property
    def name(self) -> str:
        return f"huggingface:{self.model_name}"

    def _synthesize_sync(self, text: str, rate: float) -> bytes:
        # The lock both makes lazy initialization race-free and keeps inference
        # serialized: a single VITS model instance is not assumed thread-safe.
        with self._lock:
            if self._runtime is None:
                self._runtime = self._runtime_loader(self.model_name, self.device)
            samples, sample_rate = self._runtime.synthesize(
                text,
                rate,
                self._max_pcm_samples,
            )
            return float_waveform_to_wav(
                samples,
                sample_rate,
                max_audio_bytes=self.max_audio_bytes,
            )

    async def synthesize(self, text: str, rate: float) -> AudioResult:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout_seconds
        acquired = False
        detached = False
        worker: asyncio.Task[bytes] | None = None
        try:
            await asyncio.wait_for(
                self._inference_gate.acquire(),
                timeout=max(0.0, deadline - loop.time()),
            )
            acquired = True
            worker = asyncio.create_task(
                asyncio.to_thread(self._synthesize_sync, text, rate),
                name="mms-inference",
            )
            audio = await asyncio.wait_for(
                asyncio.shield(worker),
                timeout=max(0.0, deadline - loop.time()),
            )
        except asyncio.CancelledError:
            if worker is not None and not worker.done():
                self._detach_worker(worker)
                detached = True
            raise
        except TimeoutError as exc:
            if worker is not None and not worker.done():
                self._detach_worker(worker)
                detached = True
            raise ProviderError("MMS speech synthesis timed out") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("MMS speech synthesis failed") from exc
        finally:
            if acquired and not detached:
                self._inference_gate.release()
        return AudioResult(audio=audio)

    def _detach_worker(self, worker: asyncio.Task[bytes]) -> None:
        """Release single-flight capacity only after a real thread finishes."""

        self._detached_workers.add(worker)

        def finished(completed: asyncio.Task[bytes]) -> None:
            self._detached_workers.discard(completed)
            self._inference_gate.release()
            # The original caller is gone, so explicitly retrieve a possible
            # exception instead of letting asyncio log provider internals.
            try:
                completed.exception()
            except asyncio.CancelledError:
                pass

        worker.add_done_callback(finished)

    async def aclose(self) -> None:
        # Job shutdown cancellation detaches non-cooperative thread workers.
        # Python cannot kill those threads, so wait for their real completion
        # instead of returning while model inference still mutates resources.
        workers = tuple(self._detached_workers)
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
