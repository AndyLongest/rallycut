# Windows 便携应用

## 交付范围

独立的 Windows 10/11 x64 本地应用。浏览器界面参考工作区 Netcast TennisVision
前端的深紫、紫色和黄绿色色板；不依赖其后端或任何账号接口。
仅监听 `127.0.0.1`，视频在本机处理，不上传云端。

完整解压整个目录到有写权限、足够剩余空间的磁盘后，双击 `Start.cmd`。
系统浏览器打开页面；双击 `Stop.cmd` 退出。建议使用近期的 Edge 或 Chrome。
Light 包的 CPU 使用无需安装 Python、Node、FFmpeg、CUDA 或配置 API 密钥。
GPU 为可选安装，见压缩包根目录 GPU_SETUP.md / requirements-gpu.txt。
不要直接在压缩包里运行。
运行环境、模型、临时文件、日志、上传副本和结果都在应用目录内。
移动目录前请停止程序。

输入遵循所用作者模型的现有要求：至少 20 秒、至少 720p，建议固定机位单打视频。
支持 MP4、MOV、MKV、AVI、WebM、M4V、MTS/M2TS、TS；容器内具体编码必须能由
打包的 FFmpeg/PyAV 解码。单文件最多 8 GiB。上传前至少预留原文件三倍加
512 MiB 的剩余空间；复杂视频的重编码输出可能更大。

## 功能和算法边界

- 单任务串行队列；可继续上传、查看历史、取消任务、删除本地历史及其输出。
- 原始文件只复制到应用的 `data/jobs/`，不修改或删除用户选择的外部原件。
- 0.3.0默认纯视觉加速v2：定期960全图、其余256人物裁图，5fps，同一官方权重。
- 加入全图/左右下部区域剪辑候选，合并边界；恢复超过60秒的活动并保留长片段待复核。
- 模型实际姿态与三条分数同步叠加到预览。没有人工标签输入，没有在上传视频上训练。
- 自动生成浏览器可播放的 H.264 预览、准确时间裁剪的 MP4、切片 ZIP 与 JSON。
- 进度分为视频准备、动作分析、分区剪辑/并集与媒体导出。分析耗时含剪辑检测，不含导出。
- UI 显示模型候选回合，仍可能漏切、合并或出现短片段。没有新增准确率承诺。
- 当前前端封装加速与分区剪辑并集；此前Gemini和其他实验基线保留在
  源项目中，没有默认混入应用结果。

## 目录

```
Start.cmd / Stop.cmd       启动和退出
src/rallycut/              本应用源码及离线网页
runtime/python/            便携 Python
runtime/site-packages/     锁定的依赖
runtime/gpu-site-packages/ 可选 GPU 依赖（用户自行安装，不在 Light ZIP 内）
runtime/ffmpeg/            CPU 解码、预览和裁剪
vendor/RallyClip/          上游源代码、模型和出处
data/jobs/                 每个视频的独立任务目录
data/logs/                 应用日志
data/temp/ data/cache/     包内临时目录
THIRD_PARTY_NOTICES*       第三方来源和许可说明
```

开发入口：

```powershell
.\.venv\Scripts\python.exe -m rallycut.local_app --open
```

发行构建入口是 `tools/build_portable.py`，具体参数见其 `--help`。只按白名单收集
必要运行时和上游模型，不复制开发虚拟环境、测试视频、用户数据、密钥或浏览器缓存。
构建时可以联网获取官方运行环境；最终应用启动与推理均不需要联网。

## 资源、故障与退出

默认 Light 包不含 GPU 运行库，只包含独立的 GPU requirements 和安装说明。
用户按说明安装至 runtime/gpu-site-packages 并验证启用后，优先使用该目录的
ONNX Runtime GPU 版；基础 CPU 运行库不被覆盖。未完成或未启用的安装不会加载。
优先检测可用的 NVIDIA 驱动并建立 CUDA 会话；驱动由操作系统提供，
不随应用安装或更新。没有兼容显卡、缺少驱动、GPU 初始化或计算失败时，自动回退
CPU。同一输入最多重试 CPU 一次，CPU 本身失败时正常报错，不无限重试。
AMD / Intel 显卡目前使用 CPU 路径。可选依赖首次安装需联网，应用启动和回退无需联网。

界面、progress.json 和 result.json 记录实际设备、会话执行次数和回退原因。
运行中曾使用 GPU 后转到 CPU，会显示「GPU → CPU」。保持官方960输入、5fps、
同一模型和解码参数；GPU 使用 FP32（关闭 TF32），不通过降低画质提速。
CPU 推理仍设置两个线程；视频解码与导出也使用 CPU。这不是严格的两核资源隔离。
业务繁忙机器应逐个处理视频。维护者可设置 RALLYCUT_DEVICE=cpu 强制 CPU 排查。

默认包构建：`python tools/build_portable.py --name RallyCut-Windows-x64-Light`。
不要传 `--gpu-dependencies`，以免把 GPU 库再次装进默认包。
原 AutoGPU 大包和历史 GPU 验证保留作记录。

页面刷新或关闭浏览器不会取消计算，重新启动会打开当前服务。取消操作停止本任务及其
媒体导出子进程；退出应用取消正在运行的任务，尚未开始的队列会保留。
异常断电后未完成的运行任务显示为失败，不伪装成已完成结果。

失败可查看 `data/jobs/<任务编号>/worker.log`，不要通过改名伪造成功状态。
确认不再需要后，可从网页删除历史任务释放磁盘空间。

## 第三方来源

RallyClip: https://github.com/iroblesrazzaq/RallyClip

当前使用的上游快照没有发现根目录 LICENSE，不能由本项目代为授予其代码及模型的
对外分发许可。FFmpeg 构建及姿态模型也有各自许可要求；保留包中的第三方声明和原始
许可文件。便携运行验证与对外分发许可确认是两件独立的事。
