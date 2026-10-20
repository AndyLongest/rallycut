from types import SimpleNamespace

import pytest

from rallycut import device_runtime as module


def runtime(monkeypatch, *, available=True, driver=True, creation=None, execution=None):
    calls = []

    class Session:
        def __init__(self, providers):
            self.providers = providers
            self.disabled = False

        def get_providers(self):
            return self.providers

        def disable_fallback(self):
            self.disabled = True

        def run(self, names, feed):
            calls.append(("run", self.providers[0], feed))
            if execution:
                execution(self.providers[0], feed)
            return [feed["input"] + 1]

    def factory(path, *, providers, **kwargs):
        calls.append(("create", providers[0], path))
        if creation:
            changed = creation(providers[0])
            if changed:
                providers = changed
        return Session(providers)

    ort = SimpleNamespace(
        InferenceSession=factory, SessionOptions=lambda: SimpleNamespace(),
        get_available_providers=lambda: (
            ["CUDAExecutionProvider", "CPUExecutionProvider"] if available
            else ["CPUExecutionProvider"]),
        preload_dlls=lambda **kw: None,
    )
    monkeypatch.setattr(module, "cuda_driver_available", lambda: driver)
    return module.AutoRuntime(ort), calls


@pytest.mark.parametrize("available,driver", [(False, True), (True, False)])
def test_no_gpu_runs_cpu_without_attempting_cuda(monkeypatch, available, driver):
    auto, calls = runtime(monkeypatch, available=available, driver=driver)
    session = auto.session("pose.onnx")
    assert session.run(None, {"input": 7}) == [8]
    assert auto.device == "CPU"
    assert all(call[1] == "CPUExecutionProvider" for call in calls)


def test_real_gpu_session_must_complete_a_run_before_reporting_gpu(monkeypatch):
    auto, calls = runtime(monkeypatch)
    session = auto.session("pose.onnx")
    assert auto.device == "正在检测 GPU"
    assert session._session.disabled
    assert session.run(None, {"input": 7}) == [8]
    assert auto.device == "GPU (NVIDIA CUDA)"
    assert auto.sessions[0]["gpu_runs"] == 1
    assert auto.fallback_reason is None


@pytest.mark.parametrize("silent", [False, True])
def test_initialization_error_or_silent_cpu_fallback_is_recorded(monkeypatch, silent):
    def creation(provider):
        if provider == "CUDAExecutionProvider":
            if silent:
                return ["CPUExecutionProvider"]
            raise RuntimeError("missing CUDA DLL")

    auto, calls = runtime(monkeypatch, creation=creation)
    session = auto.session("pose.onnx")
    assert session.run(None, {"input": 7}) == [8]
    assert auto.device == "CPU"
    assert "初始化失败" in auto.fallback_reason
    auto.session("tcn.onnx").run(None, {"input": 8})
    assert sum(call[:2] == ("create", "CUDAExecutionProvider") for call in calls) == 1


def test_oom_retries_same_input_once_and_disables_other_gpu_sessions(monkeypatch):
    def execution(provider, feed):
        if provider == "CUDAExecutionProvider" and feed["input"] == 8:
            raise RuntimeError("CUDA out of memory")

    auto, calls = runtime(monkeypatch, execution=execution)
    pose = auto.session("pose.onnx")
    tcn = auto.session("tcn.onnx")
    assert pose.run(None, {"input": 7}) == [8]
    feed = {"input": 8}
    assert pose.run(None, feed) == [9]
    retries = [call for call in calls if call[0] == "run" and call[2] is feed]
    assert [call[1] for call in retries] == ["CUDAExecutionProvider", "CPUExecutionProvider"]
    assert auto.device == "GPU → CPU"
    assert tcn.run(None, {"input": 9}) == [10]
    assert tcn.get_providers() == ["CPUExecutionProvider"]
    assert auto.sessions[0]["gpu_runs"] == auto.sessions[0]["cpu_runs"] == 1
    assert "out of memory" in auto.fallback_reason


def test_cpu_failure_is_not_retried_forever_or_hidden(monkeypatch):
    def execution(provider, feed):
        raise ValueError("invalid input shape")

    auto, calls = runtime(monkeypatch, execution=execution)
    with pytest.raises(ValueError, match="invalid input shape"):
        auto.session("pose.onnx").run(None, {"input": 7})
    assert len([call for call in calls if call[0] == "run"]) == 2


def test_cpu_only_failure_propagates_without_retry(monkeypatch):
    def execution(provider, feed):
        raise ValueError("bad input")

    auto, calls = runtime(monkeypatch, available=False, execution=execution)
    with pytest.raises(ValueError, match="bad input"):
        auto.session("pose.onnx").run(None, {"input": 7})
    assert len([call for call in calls if call[0] == "run"]) == 1


def test_dll_loading_failure_falls_back_before_session_creation(monkeypatch):
    auto, calls = runtime(monkeypatch)

    def broken(**kw):
        raise OSError("missing cudnn")

    auto.ort.preload_dlls = broken
    fallback = module.AutoRuntime(auto.ort)
    assert not fallback.gpu_enabled
    assert "运行库加载失败" in fallback.fallback_reason
    assert fallback.session("pose.onnx").run(None, {"input": 3}) == [4]


def test_manual_cpu_override_does_not_probe_driver(monkeypatch):
    auto, calls = runtime(monkeypatch)
    monkeypatch.setattr(module, "cuda_driver_available",
                        lambda: pytest.fail("CPU override must not initialize CUDA"))
    fallback = module.AutoRuntime(auto.ort, mode="cpu")
    assert fallback.session("pose.onnx").run(None, {"input": 3}) == [4]
    assert fallback.device == "CPU"
