# 开源选型记录 · 2026-10-19

目标是 CPU 业务服务器上的回合时间切分，不要求逐帧识别球、落点或人体姿态。
下列上游在本次工作中经过在线查阅；没有把项目宣传或其他数据集指标当作本项目准确率。

| 上游 | 本项目用途/决策 | 适用边界 |
|---|---|---|
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) / [AdaptiveDetector 文档](https://www.scenedetect.com/docs/latest/api/detectors.html) | **直接集成 Python 库**；局部内容差分与滚动比值检测，CPU 默认方案 | 检测编辑切换，不能单独识别所有真实回合结束。上游常规最小变化幅度 15 在同机位 demo 漏检；改为亮度、幅度 .5、比值 3 后有效，属于开发集调参。锁定 0.6.7.1 做本轮实测，在线 latest 文档已经是 0.7 系列。 |
| [OpenCV MOG2](https://docs.opencv.org/4.x/d1/dc5/tutorial_background_subtraction.html) | **直接调用**背景建模、帧差与 ROI，提供稀疏运动证据 | 固定机位较合适；走动、捡球、阴影、相机运动会干扰。运动不是回合语义。 |
| [TennisHighlights](https://github.com/zanyaziz/TennisHighlights) / [motion source](https://github.com/zanyaziz/TennisHighlights/blob/main/scripts/motion_analysis.py) / [audio source](https://github.com/zanyaziz/TennisHighlights/blob/main/scripts/audio_analysis.py) | 参考其抽帧运动、球场 ROI、音频 onset 聚类和缓冲的组合思路；**未复制源代码**，未作为代码依赖 | 没有发现可直接套用的可靠同数据评测；音频邻场串音和固定 gap 会误合并/误切。 |
| [tennis-coach](https://github.com/live1206/tennis-coach) | 查阅音频候选回合、CPU YOLOX/OpenCV 与结构化信号的组合；没有引入其 AGPL 项目代码 | 整条全量姿态/球跟踪流水线超出本次低成本目标。 |
| [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) / [official ONNX inference](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/demo/ONNXRuntime/onnx_inference.py) | 官方 Nano ONNX + OpenCV DNN **CPU**；实验可选，无姿态，无 CUDA。参考上游网格解码及 BGR/letterbox 预处理约定 | 增加约 5.82 秒检测时间，未证明切分精度收益；默认不加载。球员框本身不能区分击球/走动。Apache-2.0。 |
| [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL) | 大模型路线的开源参考：时间戳对齐、多图/视频抽样、分窗时间定位；本项目实现协议适配，**尚未真实调用** | 不在无显卡业务服务器上默认部署模型；外部服务准确率/费用需实际比较。1 fps 无法保证观察到每次击球。 |
| [Google Gemini 多图输入](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/samples/googlegenaisdk-textgen-with-multi-local-img) / [结构化输出](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output) | 用户指定的现有商业模型接口，另行完成原生 SDK/Vertex AI 适配及一次真实对照。**Gemini 不是本项目使用的开源模型** | 本轮只测 `gemini-3.6-flash` 的 1 fps 多图提示词。没有配置本地 GPU，也不能将首次结果视作服务的最优准确率。详见实验追加记录。 |
| [TennisTV](https://arxiv.org/abs/2509.15602) | 查阅网球多模态模型评测，说明通用视频理解能力不足以证明精确体育时间定位 | 回合理解问题与长视频切段不是同一个评测任务。 |
| [F3Set](https://github.com/F3SET/F3Set) / [F3Tennis](https://github.com/F3EST/F3Tennis) | 更细粒度事件检测/标注的研究候选 | 本轮未部署、未测 CPU 速度；不可据此声称能低成本切原始业余视频。 |
| [TransNetV2](https://github.com/soCzech/TransNetV2) | 学习型镜头转场候选 | 未在本轮部署；同机位回合变化与镜头变化不同，先验证轻量上游基线。 |
| [ruptures](https://github.com/deepcharles/ruptures) | 查阅通用时序变点检测 | 未接入产品决策，无可靠视频特征前不能用它代替回合语义。 |
| [Breakpoint](https://github.com/xinyiz1226/Breakpoint) | 更贴近完整业余比赛原片的对照：音频 onset、间隔分组、密度修边；尚未在用户原片运行 | 视觉运动主要用于排序，不能当作纯画面语义分段的实证。未引入其项目代码。 |
| [RallyClip](https://github.com/iroblesrazzaq/RallyClip) / [发行模型 manifest](https://github.com/iroblesrazzaq/RallyClip/blob/main/models/rallyclip_v0.5.0/manifest.json) | 完整视频专项参照，实际最新版为v0.5.0 TCN起止热图，5fps姿态＋20秒窗口；CPU2线程对照960/640/416分辨率 | 416本机约48.59s处理299.6s，±2秒对齐8/11结束事件，仍漏发球失误及合并回合；没有默认部署。旧PROJECT_SUMMARY的v0.3.1/LSTM描述不能替代实际manifest。 |
| [leonbeier/tennis_demo](https://github.com/leonbeier/tennis_demo) | 已实测约0.9MB双帧小球ONNX；CPU2fps | 输入为两张完整1080p图，实际整段233.57s，速度与精度都不能按权重大小推断。与上游许可一并保存在忽略目录，未部署；完整记录见RAW_VIDEO_20261019.md。 |

## 可选模型来源

- 权重：[YOLOX 0.1.1rc0 官方 yolox_nano.onnx](https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx)
- 文件大小：3,659,407 字节；输入 416×416；输出 3549×85；只读取 COCO person 类。
- SHA-256：`c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d`
- `install-person-model` 下载并校验；权重保存在忽略目录 `models/`，运行时不自动下载。
- 上游许可保存在 `third_party/YOLOX_LICENSE`。本项目未发布/转售第三方权重。

没有一个引用能够证明“速度与准确率全球最好”。当前只选择已实测、符合 CPU
限制的最小基线。后续须用独立原片比较漏切、误切、短回合、时间误差和端到端成本。
