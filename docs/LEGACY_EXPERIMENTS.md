# RallyCut：本地网球回合识别

## Windows 便携应用

面向使用者的入口是 `dist/RallyCut-Windows-x64-Light.zip`：完整解压到可写目录，
双击 `Start.cmd`，浏览器自动打开上传页面。Python、CPU 推理依赖、官方
RallyClip v0.5.0 模型和 FFmpeg 均在包内；首次启动不联网安装，不要求系统
Python、Node、显卡或 API 密钥。`Stop.cmd` 关闭程序。

当前应用使用完整 960 输入的 RallyClip，5 fps 抽帧。自动优先使用可用的 NVIDIA
CUDA 显卡（需先安装可选依赖）；无 GPU 依赖、无兼容显卡、驱动不可用或 GPU
失败时回退 CPU。GPU 运行库单独列在 `requirements-gpu.txt`，安装步骤见
[GPU 安装说明](../packaging/GPU_SETUP.md)，不再随默认 ZIP 分发。页面显示实际设备
和回退原因。历史 CPU / AutoGPU 压缩包保留作对照。
**不是此前的 416 快速配置，也不默认叠加剪辑接缝切点。**
上传后自动串行分析并生成回合片段，页面显示真实骨架、三条模型分数和
回合时间轴，支持逐回合播放、JSON 与 MP4 下载。保持原模型、原阈值；
结果仍需人工核对，打包不代表准确率已通过验收。

使用说明、项目结构与验证记录见 [便携应用说明](PORTABLE_APP.md) 和
[GPU 自动回退验证](GPU_AUTO_FALLBACK_20261020.md)、
[GPU 依赖拆分验收](OPTIONAL_GPU_PACKAGE_20261020.md)。
以下保留历史实验入口，供开发与对照，普通用户无需执行它们。

## 历史实验

新增纯视觉加速候选：`run_fast_visual.ps1 -Video "E:\video.mp4" -Output "outputs\new_result"`。
使用项目已有 `.venv`，输出 JSON / CSV 和分数轨迹；独立入口保留完整版。
本机5分钟样本约3倍加速，仍有短段遗漏，具体差异及复现方式见
[纯视觉加速实验](VISUAL_ACCELERATION_20261020.md)。teacher 对齐不是人工准确率。

目标：输入**未经剪辑的完整训练视频**，识别实际击球回合与等待/捡球/休息，
输出回合时间段 JSON/CSV、可选 MP4 切片和人工对照页。
项目有自己的依赖环境，不导入 Tennis_Vision 或 netcastApp。

**当前尚未通过完整训练原片的准确率验收。** 之前的 5 段 demo 结果主要来自
剪辑接缝诊断，已撤下作为主结果；相关 F1/平均偏差不能用来证明回合识别能力。
现有 `visual`/`audio`/`hybrid` 只是待验证基线，不能表述为已完成的算法。

已开始使用用户提供的 **demo3_clip1.mp4 开发样本**（约 5 分钟、1080p）和
11 个结束标注进行真实对照。标注文件为
`tests/fixtures/demo3_clip1.manual_ends.v1.json`，没有提供开始时间，因此
只计算结束事件匹配，不报告起点或区间 IoU。详细对照见
[原片实验记录](RAW_VIDEO_20261019.md)。
后续逐帧核查发现样本含转场和「精彩回放」，不能继续视为完全未经剪辑原片；
修正证据见 [分数诊断记录](SCORE_DIAGNOSTIC_20261020.md)，原始标注保留不变。

早期 CLI 基线路线默认无需模型权重，不加载姿态模型、
PyTorch、CUDA 或 GPU。大模型路线另有原生 Gemini/Vertex AI 适配器，以及
多图 chat-completions 协议适配器。真实推理状态与对照记录见实验文档。

2026-10-20新增用户指定的 **RallyClip＋PySceneDetect边界并集实验**，作为
单独的可选入口；该入口使用RallyClip的CPU姿态特征与官方预训练权重。
详见 [并集实现与随机测试](UNION_EXPERIMENT_20261020.md)，尚未通过验收。

## 安装与运行

要求 Python 3.10+、FFmpeg、ffprobe。导出 MP4/生成预览额外要求 FFmpeg 包含
软件编码器 libx264；程序会检查 PATH 中可用的构建。

Windows：

```powershell
.\setup.ps1
.\run_video.ps1 -Video 'D:\full_training_video.mp4' -Preview -ExportClips
```

Linux/业务服务器的独立安装：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m rallycut.cli analyze /path/to/video.mp4 --mode hybrid --output outputs/job1 --threads 2
```

CLI 示例（Windows）：

```powershell
# 未剪辑原片：分别跑纯画面、纯音频、音画融合基线
.\.venv\Scripts\python.exe -m rallycut.cli analyze 'D:\input.mp4' --mode visual --output outputs/visual
.\.venv\Scripts\python.exe -m rallycut.cli analyze 'D:\input.mp4' --mode audio --output outputs/audio
.\.venv\Scripts\python.exe -m rallycut.cli analyze 'D:\input.mp4' --mode hybrid --output outputs/hybrid
# 纯 CPU 小球运动候选：局部亮度对比、颜色、背景分离、短时连续性
.\.venv\Scripts\python.exe -m rallycut.cli analyze 'D:\input.mp4' --mode ball-motion --output outputs/ball_motion
```

已有本地RallyClip源码和官方v0.5.0权重时，可从一个视频运行双路并集并生成
叠加视频（全CPU；目前两路分别解码，渲染时间另计）：

```powershell
.\.venv\Scripts\python.exe tools/run_union.py 'D:\input.mp4' --output outputs/union_job --threads 2 --render
# 恢复官方960输入配置，仍然只用CPU；其他时序参数和权重不变
.\.venv\Scripts\python.exe tools/run_union.py 'D:\input.mp4' --output outputs/union_960 --threads 2 --imgsz 960 --render
# 或复用同一视频已经保存的两路JSON；不重新推理
.\.venv\Scripts\python.exe -m rallycut.cli fuse outputs/union_job/rallyclip/rallies.json outputs/union_job/scenes/rallies.json --output outputs/union_job/fused --merge-tolerance 1 --short-seconds 1
```

`fused/boundaries.csv`为完整并集切点及来源；`timeline_segments.csv`为完整
分区、动作支持状态和短段标志。`rallies.json`同时保留这两组数据，但其中
`rallies`字段仅含动作模型支持的区间，未确认区间不会冒充已识别回合。
两路附近1秒内的点合并，保留原始时间和来源；同一路不同动作起止不会
合并，避免吞掉短回合。小于1秒的碎段只标记、不删除。
`--imgsz`可选416/640/960，默认保留416速度实验；960遵循官方artifact输入
配置，不是另换一套更大的权重。随机远景样本恢复960后的对照见上述实验文档。

`run_demo.ps1` 已改为普通候选基线的兼容入口，不再自动选择剪辑接缝模式或
套用 demo 标签。主入口是 `run_video.ps1`，人工标签需要明确提供 `-Labels`。

## 两条路线与当前边界

1. **CPU 路线**：使用 OpenCV MOG2/帧差提取稀疏运动证据，带限音频 onset
   作为独立/融合对照。已移除音画融合中“场景变化强行拆段”的行为。
   后续基于完整原片评测运动与实际击球活动，不能靠接缝完成切分。
2. **大模型路线**：每帧携带绝对时间，默认 1 fps、60 秒窗口、10 秒重叠，
   交给支持多图输入的多模态服务。没有人工标签、回合数量提示或音频输入。
   长视频分窗结果需要解决重复和冲突；冲突会显式失败。

`edited`/`scene` 仅保留为**历史剪辑诊断**，不属于回合识别验收路线。
`visual`/`audio`/`hybrid` 均为待验证的回合候选生成基线；不能将
拼接 demo 的结果当作未经剪辑训练/比赛长视频的准确率。
`ball-motion` 也只是实验，不能把颜色/运动候选宣传成可靠逐球跟踪。

验收口径：从发球、教练/球机喂球后的首次有效击球等开始，到该球停止对打；
不要求每回合都有发球或比分变化。标注须包含等待、捡球、休息及短回合。
分别计算回合漏检/误检、起止时间误差及空闲时间误保留，速度用完整原片和
目标 CPU 配额测量。导出缓冲时间须与实际回合标签分开。

CPU YOLOX-Nano 另有可选实验开关，仅记录球员框证据；目前没有切分精度收益
证明，不参与默认决策，也没有作为第二条路线的必要依赖。

## 输出与人工评测

- `rallies.json`：原视频信息、候选回合、证据、复核标志、分阶段耗时。
- `rallies.csv`：回合号、起止秒数。
- `review.html`：播放候选片段、比较人工标注、编辑并导出人工标签。
- `clips/rally_001.mp4` 等：`--export-clips` 时生成，软件重编码保证切点。
- `preview.mp4`：`--preview` 时生成，解决浏览器不能播放 HEVC 的情况。
- `visual_features.json`：抽帧诊断数据，便于排查漏切/误切。

时间均相对视频第一帧，从 0 开始。FFmpeg 的均匀采样时间网格避免用
输入帧号除以固定 30 fps，支持可变帧率。抽帧减少画面分析成本，
H.264/H.265 的解码通常仍需遍历参考帧，不能宣称总成本下降到 4/30。
大部分耗时来自视频解码，软件剪片和可选预览的成本另列。

人工标注格式：

```json
{"source":"human", "rallies":[{"start_seconds":0,"end_seconds":9}]}
```

```powershell
.\.venv\Scripts\python.exe -m rallycut.cli evaluate outputs/job1/rallies.json labels.json --tolerance 1
.\.venv\Scripts\python.exe tools/benchmark.py 'D:\input.mp4' --labels labels.json
.\.venv\Scripts\python.exe -m pytest -q
```

评测分别报告内部切点 F1（1 秒容差，不计视频起止的平凡边界）和回合时间
IoU≥0.5 的一对一匹配，避免整段输出一个回合也得到虚高分。
你的原始整数秒标签保存在 `tests/fixtures/demo.manual.v1.json`。
末尾 58 秒原样保留；评测按视频流的实际 57.9 秒截断，音轨/容器略长。

## 大模型接口

```powershell
.\.venv\Scripts\python.exe -m rallycut.cli vlm-prepare 'D:\input.mp4' --output outputs/vlm_job1
# 配置支持多图的 chat-completions 接口（例如已部署的 Qwen-VL 服务）
$env:RALLYCUT_VLM_URL = 'https://your-provider.example/v1/chat/completions'
$env:RALLYCUT_VLM_MODEL = 'your-available-vision-model'
# RALLYCUT_VLM_API_KEY 由用户在环境中配置；不要写入源码或聊天。
.\.venv\Scripts\python.exe -m rallycut.cli vlm-call outputs/vlm_job1 --labels labels.json
```

配置接口并调用会向该服务发送抽样图像，并可能产生服务调用费用。
准备阶段不访问模型服务。成功窗口保存检查点，重启不会重复请求；
超时不自动重试，避免对未知计费状态的重复消费。更换输入/模型后须使用
新输出目录。原生 Gemini 应使用下面的独立命令，不能直接填入该 URL。

### 原生 Gemini / Vertex AI

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[gemini]'
# 复用已有 Vertex AI 账号时，使用外部 ADC/服务账号文件，不把密钥放入项目。
$env:GOOGLE_GENAI_USE_VERTEXAI = 'true'
$env:GOOGLE_CLOUD_PROJECT = 'your-existing-project'
$env:GOOGLE_CLOUD_LOCATION = 'global'
$env:GOOGLE_APPLICATION_CREDENTIALS = 'C:\private\service-account.json'
.\.venv\Scripts\python.exe -m rallycut.cli gemini-call outputs/vlm_job1 --model your-available-gemini-model --labels labels.json
```

也支持使用环境中的 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY` 调用 Google Developer
API；此时不设置 `GOOGLE_GENAI_USE_VERTEXAI=true`。可用模型由用户账号决定。
SDK 仅为可选依赖，CPU 路线不需要安装。

原生适配器使用时间戳图像序列、JSON schema 输出、逐窗口检查点。
失败/超时留下尝试记录并停止，不能自动重复可能计费的请求。人工标签
只在调用完成后加载评测。账号凭据不写入请求记录或回合结果。

本机不承担大模型推理；本地 CPU 是否适合运行小型 VLM 尚未实测。
业务服务器的确切 CPU/RAM 及长视频性能还未验收。

### 原生视频输入对照

```powershell
.\.venv\Scripts\python.exe -m rallycut.cli gemini-video-prepare 'D:\input.mp4' --output outputs/gemini_native --fps 2
.\.venv\Scripts\python.exe -m rallycut.cli gemini-call outputs/gemini_native --model your-available-gemini-model --labels labels.json
```

先用 CPU 生成 640px 宽、至少 4 fps 的紧凑视频，再让 Gemini 按指定帧率采样，
显式使用低媒体分辨率。默认保留音频，`--no-audio` 可做纯画面对照。
准备耗时、API 耗时和 token 用量分别记录，不能用缓存复核耗时冒充模型速度。

开源选型见 [docs/RESEARCH.md](RESEARCH.md)，实验记录见
[docs/EXPERIMENTS.md](EXPERIMENTS.md)。

### 骨架与原始分数诊断

`benchmark_rallyclip.py` 增加 `--capture-features --capture-scores` 可选开关，
保存实际人体分配、362维特征，以及切分前的“回合中/开始/结束”三条分数。
`tools/diagnose_scores.py` 用已有结束标注逐层检查阈值段、边界细化、时长过滤
及合并；`tools/build_score_diagnostic.py` 生成普通本地网页，视频上叠加实际
骨架，下方同步显示分数和人工结束点。完整复现与发现见
[docs/SCORE_DIAGNOSTIC_20261020.md](SCORE_DIAGNOSTIC_20261020.md)。
本轮复核发现 demo3_clip1 含「精彩回放」和转场，不能继续将其称为完全
未经剪辑的训练视频；既有人工结束标签与历史结果仍原样保留。
