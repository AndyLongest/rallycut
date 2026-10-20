"""Automatic CUDA sessions with a bounded, observable CPU fallback."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


def cuda_driver_available():
    """Check the driver, not just the providers compiled into an ORT wheel."""
    try:
        driver = (ctypes.WinDLL("nvcuda.dll") if os.name == "nt"
                  else ctypes.CDLL("libcuda.so.1"))
        count = ctypes.c_int()
        if driver.cuInit(0) != 0 or driver.cuDeviceGetCount(ctypes.byref(count)) != 0:
            return False
        return count.value > 0
    except (OSError, AttributeError):
        return False


class AutoRuntime:
    def __init__(self, ort, threads=2, *, mode="auto", on_change=None):
        if mode not in {"auto", "cpu"}:
            raise ValueError("RALLYCUT_DEVICE must be auto or cpu")
        self.ort = ort
        self.mode = mode
        self.factory = ort.InferenceSession
        self.threads = threads
        self.on_change = on_change
        self.sessions = []
        self.fallback_reason = None
        self.gpu_enabled = False
        if mode == "cpu":
            self.fallback_reason = "已设置使用 CPU"
        elif "CUDAExecutionProvider" not in ort.get_available_providers():
            self.fallback_reason = "当前运行环境未包含 CUDA 支持，使用 CPU"
        elif not cuda_driver_available():
            self.fallback_reason = "未检测到可用的 NVIDIA CUDA 显卡或驱动，使用 CPU"
        else:
            try:
                # Official ORT loader resolves the bundled NVIDIA wheels.
                # The embedded runtime excludes user/system Python packages.
                ort.preload_dlls(cuda=True, cudnn=True, msvc=False, directory="")
                self.gpu_enabled = True
            except Exception as exc:
                self.fallback_reason = f"GPU 运行库加载失败，已回退 CPU：{str(exc)[:500]}"
        self.notify()

    @property
    def requested_device(self):
        return "cuda" if self.gpu_enabled else "cpu"

    @property
    def device(self):
        used_gpu = any(row["gpu_runs"] for row in self.sessions)
        if used_gpu:
            return "GPU (NVIDIA CUDA)" if self.gpu_enabled else "GPU → CPU"
        return "正在检测 GPU" if self.gpu_enabled else "CPU"

    def notify(self):
        if self.on_change:
            self.on_change(self.device, self.fallback_reason)

    def fallback(self, reason):
        self.gpu_enabled = False
        # Keep the first cause instead of hiding it with later CPU sessions.
        if self.fallback_reason is None:
            self.fallback_reason = reason
        self.notify()

    def session(self, path, sess_options=None, providers=None, **kwargs):
        options = sess_options or self.ort.SessionOptions()
        options.intra_op_num_threads = self.threads
        options.inter_op_num_threads = 1
        kwargs.pop("provider_options", None)
        return FallbackSession(self, path, options, kwargs)


class FallbackSession:
    def __init__(self, runtime, path, options, kwargs):
        self.runtime = runtime
        self.path, self.options, self.kwargs = path, options, kwargs
        self._session = None
        self._gpu = False
        self.record = {
            "model": Path(path).name, "providers": [], "threads": runtime.threads,
            "gpu_runs": 0, "cpu_runs": 0, "fallback_reason": None,
        }
        runtime.sessions.append(self.record)
        if runtime.gpu_enabled:
            try:
                self._session = self._create(["CUDAExecutionProvider", "CPUExecutionProvider"])
                if "CUDAExecutionProvider" not in self._session.get_providers():
                    raise RuntimeError("CUDA 会话未建立，运行时只返回了 CPU")
                # ORT must not silently retry on a different provider behind
                # our counters; this wrapper owns the single CPU retry.
                self._session.disable_fallback()
                self._gpu = True
            except Exception as exc:
                self._fallback("GPU 初始化失败", exc)
        else:
            self._cpu()
        self.record["providers"] = self._session.get_providers()

    def _create(self, providers):
        kwargs = dict(self.kwargs)
        if providers[0] == "CUDAExecutionProvider":
            # Keep FP32 arithmetic and avoid expensive, large-workspace
            # convolution searches on small consumer GPUs.
            kwargs["provider_options"] = [{
                "use_tf32": "0", "cudnn_conv_algo_search": "HEURISTIC",
                "cudnn_conv_use_max_workspace": "0",
            }, {}]
        return self.runtime.factory(self.path, sess_options=self.options,
                                    providers=providers, **kwargs)

    def _cpu(self):
        self._gpu = False
        self._session = None  # Release this GPU allocation before retrying.
        self._session = self._create(["CPUExecutionProvider"])
        self.record["providers"] = self._session.get_providers()

    def _fallback(self, phase, exc):
        reason = f"{phase}，已回退 CPU：{str(exc)[:500]}"
        self.record["fallback_reason"] = reason
        self.runtime.fallback(reason)
        self._cpu()

    def run(self, *args, **kwargs):
        if self._gpu and not self.runtime.gpu_enabled:
            self._cpu()
        first_success = not (self.record["gpu_runs"] or self.record["cpu_runs"])
        try:
            result = self._session.run(*args, **kwargs)
        except Exception as exc:
            if not self._gpu:
                raise
            self._fallback("GPU 计算失败", exc)
            # Same input is retried once. CPU errors propagate normally.
            result = self._session.run(*args, **kwargs)
        self.record["gpu_runs" if self._gpu else "cpu_runs"] += 1
        if first_success:
            self.runtime.notify()
        return result

    def __getattr__(self, name):
        return getattr(self._session, name)
