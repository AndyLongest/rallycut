# GPU 依赖拆分（2026-10-20）

用户要求不要将大型 GPU 运行库放进默认压缩包，改为明确列出 requirements。
这项要求替代历史 AutoGPU 全量打包方案，原包与实测结果保留。

新默认包为 `dist/RallyCut-Windows-x64-Light.zip`，263,122,848 字节，
SHA256：`672c56dbf2f5f06b38cb38370f4e900efed1ab141a9e7d3cc0092ec8f2376ec9`。
CPU Python、依赖、模型和 FFmpeg 仍随包提供。包内没有 NVIDIA 运行库或
onnxruntime-gpu，包含 `requirements-gpu.txt` 和 `GPU_SETUP.md`。

GPU 扩展固定为此前本机实际验证过的 ONNX Runtime GPU 1.22.0 / CUDA 12
组合，包括曾导致初始化失败的 cuFFT。安装工具使用 Python 3.12 x64 pip，
以 `--no-deps --target runtime/gpu-site-packages` 安装。基础依赖来自便携包，
不能将这份 GPU 扩展 requirements 当作空白环境的完整应用 requirements。

可选目录必须经过 `python -m rallycut.optional_gpu` 验证固定版本、文件完整性、
模型 CPU 加载能力后才启用。未完成安装不影响原 CPU 路径。GPU 目录优先级只在
推理进程中启用，不覆盖原 CPU 文件。原有显卡/驱动探测及 GPU 失败后 CPU 重试
逻辑保留；`RALLYCUT_DEVICE=cpu` 可强制跳过可选目录。

源代码测试：93 passed。交付包验收脚本和实测数据保存在
`outputs/light_package_20261020/`。这是包装与设备兼容性检查，不是新的准确率
测试或业务服务器性能承诺。

交付 ZIP 实际解压至中文、空格路径后通过 CRC 和 3,593 个文件哈希检查。
没有可选依赖时，71 秒样本以 CPU 完成，3 个区间与历史参考一致；按文档安装
并启用 GPU 扩展后，同一样本的三个会话实际分别执行 11 / 355 / 7 次 GPU 推理，
仍为 3 个区间，最大边界差约 0.0000003 秒。再次校验确认安装没有修改基础包文件。
独立前端启动返回 HTTP 200，验收服务已关闭。

单次 CPU / GPU 分析耗时分别为 65.708 / 24.489 秒，总耗时 75.396 / 31.979 秒，
仅记录本次安装验收，不用于硬件性能比较。最初的验收辅助脚本误将设备名期望为
`GPU`，实际产品字段为 `GPU (NVIDIA CUDA)`；修正检查后，通过
`collect_acceptance.py` 对已完成的真实结果及基础文件重新核验，未重复推理。
最终证据为 `outputs/light_package_20261020/acceptance.json`。
