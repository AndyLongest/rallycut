# 可选 GPU 环境

默认的 Light 压缩包包含 CPU 环境，可以直接解压、双击 `Start.cmd`。
GPU 运行库不在压缩包内；不使用 GPU 的用户可以跳过本文。

## 使用 GPU 的要求

- Windows 10 / 11 x64；兼容 CUDA 12 的 NVIDIA 显卡和驱动。
- 安装时联网，并预留约 5GB 临时及运行库空间。
- 安装工具需要 Python **3.12 x64** 和 pip。这里只用它安装依赖，实际运行仍使用包内 Python。
  若电脑尚未安装，可从 https://www.python.org/downloads/windows/ 安装 3.12 x64，
  并包含 Python Launcher / pip。无需安装完整 CUDA Toolkit。
- 本机验证配置为 RTX 3050 Ti Laptop、驱动 551.61；其他显卡以实际初始化结果为准。
  AMD / Intel 显卡目前走 CPU 路径。

## 安装步骤

先双击 `Stop.cmd` 退出此目录的应用。在**解压后的应用根目录**打开 PowerShell：

```powershell
py -3.12 -m pip install --only-binary=:all: --no-deps --target ".\runtime\gpu-site-packages" -r ".\requirements-gpu.txt"
```

等这条命令成功后，再执行：

```powershell
.\runtime\python\python.exe -X utf8 -B -m rallycut.optional_gpu
```

第二步检查固定版本、文件完整性和 CPU 回退能力，成功后才启用 GPU 目录。
随后双击 `Start.cmd` 即可。启动和分析本身不需要联网。
页面会显示实际使用的是 GPU、CPU，或运行中发生了 GPU → CPU 回退。

依赖安装在本项目的 `runtime/gpu-site-packages`，不会替换 CPU 环境。
不要将 GPU requirements 安装到 `runtime/site-packages`；两个 ORT 版本不能混装到同一目录。
`--no-deps` 是有意设置的：NumPy、protobuf、packaging、flatbuffers 等基础依赖已在包内。
这份 requirements 是便携包的 GPU 扩展，不是空白 Python 环境的完整应用 requirements。

如果首次安装失败，应用仍使用 CPU。重试前将 `runtime/gpu-site-packages` 改名保留，
再按上面步骤安装到新的空目录，不要对半安装的目录直接叠加。
更新依赖前同样先退出程序，并保留旧目录作为备份。
如需停用 GPU，退出程序后将 `runtime/gpu-site-packages` 改名，再重新启动即可。

## 固定版本

具体版本以根目录 `requirements-gpu.txt` 为准：ONNX Runtime GPU 1.22.0，
CUDA Runtime 12.4.127、cuBLAS 12.4.5.8、cuDNN 9.1.0.70、
NVRTC 12.4.127、cuFFT 11.2.1.3。缺少 cuFFT 也会导致 CUDA 会话初始化失败。
显卡驱动由系统提供，requirements 不会安装或更新驱动。
