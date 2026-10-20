# RallyCut · 网球回合切分

输入视频，输出回合的开始/结束时间，支持视频复核与 MP4 导出。
当前交付给团队技术负责人接手：**纯画面识别，本机运行，无需云端账号或 API 密钥。**

## 从这里开始

- **直接使用**：[下载 Windows Light 包](https://github.com/AndyLongest/rallycut/releases)。完整解压，双击 `Start.cmd`，浏览器上传视频；`Stop.cmd` 退出。CPU 环境、模型、FFmpeg 均在包内。GPU 依赖独立安装，见 [GPU_SETUP.md](packaging/GPU_SETUP.md)。
- **技术接手**：先读 [技术交接与验收](docs/HANDOFF.md)，再看 [结果数据契约](docs/RESULT_CONTRACT.md)。
- **开发运行**：安装 Python 3.12 x64 后，在项目目录执行 `.\setup.ps1`。配置 FFmpeg/ffprobe 或从 Light 包复制 `runtime/ffmpeg`，双击 `Start-Source.cmd`。
- **加速版实验**：完成源码安装后执行下面的命令；加速版目前是独立 CLI，**尚未接入便携包前端**。

```powershell
.\run_fast_visual.ps1 -Video 'D:\training.mp4' -Output 'outputs\new_job'
```

## 两个交付入口

| | 完整版 | 纯视觉加速 v2 |
|---|---|---|
| 入口 | Light ZIP / `Start-Source.cmd` | `run_fast_visual.ps1` |
| 算法 | 官方 960 人体姿态 + TCN，5fps | 同一模型，定期全图找人，其余采样点在人附近裁图 |
| 设备 | 可选 NVIDIA GPU，失败回退 CPU | 固定 CPU，默认两线程 |
| 输出 | 时间段、骨架/分数、预览、MP4、JSON | 时间段 JSON/CSV、分数、耗时审计、复核页 |
| 状态 | 当前完整模型参考版本，需人工复核 | 加速候选，仍需跨视频验证 |

当前主入口不使用声音判断回合，也不混入剪辑接缝检测。播放/导出视频可能保留原声，
这与模型切分输入无关。早期音频、Gemini、并集等代码仅作历史实验保留，
不要将 `run_video.ps1` / `analyze --mode hybrid` 当成本次交付入口。

## 已有实测

本机 CPU 两线程单次模型分析；不包含预览转换、切片导出，不是业务服务器实测。

| 视频 | 时长 | 完整版 | 加速版 | teacher / 加速回合数 | 回合内时间 IoU |
|---|---:|---:|---:|---:|---:|
| demo3_clip1（开发样本） | 299.60s | 233.52s | 78.15s | 12 / 11 | 98.06% |
| demo3_clip2（同录制另一段） | 303.27s | 224.33s | 75.76s | 12 / 11 | 94.78% |

这些数值是与完整版 teacher 的一致性，**不是人工准确率**。clip1 含回放；
clip2 不是独立机位。deemo2 按项目负责人要求退出后续测试和方案评价，
其历史记录保留；不能据此宣称已验证跨机位泛化。
可机读结果见 [交付基准](docs/benchmarks/handoff_visual.json)。

## 结构与复现

```text
src/rallycut/local_app.py       本地网页服务、串行任务队列
src/rallycut/local_worker.py    完整版推理、诊断、媒体导出
src/rallycut/device_runtime.py  GPU 探测与 CPU 回退
src/rallycut/fast_pose.py       加速 v2 的局部裁图适配
tools/run_fast_visual.py       加速版独立入口
tools/benchmark_rallyclip.py   完整/实验 CPU 推理与审计
tools/bootstrap_upstream.py    获取并校验固定上游代码和权重
upstream-lock.json             上游 commit、下载链接、SHA-256
requirements-runtime.txt      已验证的 CPU 依赖
requirements-gpu.txt           便携环境的可选 GPU 扩展
tests/                        单元与集成回归
```

源仓库不包含模型、运行环境、原始视频或任务输出。`setup.ps1` 首次联网准备，
环境放在 `.venv`，上游代码/模型放在 `outputs/upstream_rallyclip/RallyClip-main`；
完成后本地识别无需网络。Light ZIP 则已包含离线 CPU 运行环境。

```powershell
.\.venv\Scripts\python.exe tools/bootstrap_upstream.py --verify-only
.\.venv\Scripts\python.exe -m pytest -q
```

## 接手时必须知道

输入按当前作者模型要求至少 20 秒、720p，建议固定机位单打。
人物太小、遮挡、回放、镜头移动、短发球失误都可能影响切分；当前尚无独立真实
业务数据的准确率验收。业务服务器的速度、并发、内存也需要在目标环境测量。
先以 JSON 接入业务，保留人工复核与原始文件，避免把教师一致性当作准确率承诺。

项目基于 [RallyClip](https://github.com/iroblesrazzaq/RallyClip) 官方模型；
精确版本在 `upstream-lock.json`。使用的源码快照缺少根 LICENSE，
其代码及模型的对外分发/商用授权尚需团队确认；本仓库不代替上游授予许可。
详见 [第三方声明](packaging/THIRD_PARTY_NOTICES.md)。当前仓库用于团队私有交接。

历史研究、失败尝试及原始口径见 [历史实验入口](docs/LEGACY_EXPERIMENTS.md)
和 [加速实验记录](docs/VISUAL_ACCELERATION_20261020.md)。
