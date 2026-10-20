# 纯视觉加速实验 · 2026-10-20

用户明确要求新加速路线不使用音频，并允许将当前完整 RallyClip 输出作为
teacher 优化目标。teacher 是冻结模型的预测，不是人工真值。本轮没有训练
一个新的学生神经网络；以 teacher 对照进行推理流水线优化与参数选择。

## 入口与隔离

```powershell
.\run_fast_visual.ps1 -Video "E:\video.mp4" -Output "E:\new_result"
```

或在项目自带 `.venv` 中：

```powershell
.\.venv\Scripts\python.exe tools/run_fast_visual.py "E:\video.mp4" --output "outputs\new_result"
```

输出回合 JSON / CSV、三个分数轨迹、分析耗时及 CPU 调用审计。输出目录必须
是新的目录。teacher 文件不是推理参数，不读取之前的 teacher 骨架、分数或
回合切分；只对本次输入视频的画面推理。分析不会处理声音。保留完整解码时间
序列及原模型的 5fps 特征网格。

该入口是独立实验版，不覆盖现有一键便携包或改变其默认算法。使用项目已有
CPU 依赖，无额外 GPU / PyTorch / 新权重下载。`requirements-visual-research.txt`
仅用于重现已淘汰的 INT8 制作实验，运行加速版不需要安装。

## 固定的 v2 配置

- 原官方960姿态权重、原 TCN、原阈值与后处理保持不变。
- 5fps 中每10个采样点重新看一次全图，其余点在上一帧找到的人附近裁图，
  使用256输入。裁图大小尽量保持人物在模型输入中的像素尺度。
- 局部检测失败、人员过多或明显画面变化时回到全图。画面变化只用于重找人，
  不直接生成回合边界。
- 上一帧没有检测到人时，最长每5个采样点（约1秒）重查；画面变化会提前触发。
  此项可能延迟新出现的人，不能当成“静止就是回合外”。
- 球场定位限制为一次候选时间，失败时用上游已有默认遮罩。它可能与完整版
  多次尝试得到的球场遮罩不同，必须纳入跨视频验证。

源码在 `src/rallycut/fast_pose.py`。适配器采用作用域内替换，退出时恢复上游
方法；不修改上游源文件和模型。`teacher_comparison.py` 单独做输出后的评估，
明确报告 teacher 起止点漏匹配、新增点和回合内时间交并比。

## 已尝试但未选入 v2 的方法

1. 每秒只做一次960姿态，再插值补回5fps：71秒开发样本的前半段对打漏识。
2. 更激进的160局部输入 / 更久才全图重找：耗时减少，但回合合并明显。
3. ONNX Runtime S8S8 / QDQ 静态量化，保留姿态输出头为 FP32：
   本机完整画面推理反而更慢，切分也发生合并，因此不采用。
4. OpenVINO FP32：本机这次更慢，未采用；不据此否定其他 CPU 上的表现。
5. 解码器 NONREF 跳帧：改变了实际采样帧及样本数，收益不稳定，v2 已撤回。

量化参考 ONNX Runtime 的[官方量化文档](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)；
实现基于现有 [RallyClip](https://github.com/iroblesrazzaq/RallyClip) 的 ONNX 姿态
与时序管线，裁图、缩放和画面差分使用 OpenCV。

首次量化设置 `CalibMaxIntermediateOutputs=1` 在本环境 ORT1.31.0 导致采集数据
被清空、报 `No data is collected`；保留两次失败目录，移除该设置后成功。
最终量化产物在 `outputs/visual_acceleration_20261020/int8_v2/`，未用于发行。

## 数据分工与边界

开发：`demo_forrating2.mp4`、`demo3_clip1.mp4`。模型量化校准也仅使用这两段。
v2 参数锁定后验证：`deemo1.mp4`、`demo3_clip2.mp4`。clip2 是与开发 clip1 同一
录制的另一段，不代表独立场景泛化。`flat_deemo.mp4` 因960×544低于 teacher
要求的720p，teacher拒绝执行；未伪造空标签，也未绕过限制纳入一致性数字。

保留 `frozen_validation_protocol.json` 与后续的 `frozen_validation_v2.json`，
后者解释开发阶段撤回 NONREF、增加空画面重查间隔及替换不受支持视频的原因。
所有试验保存在 `outputs/visual_acceleration_20261020/`。

耗时是本机 Ryzen7 6800H 的 CPU 两线程分析，不含媒体导出；不同运行的后台
负载和温度未固定。没有访问或部署业务服务器，不能承诺其耗时或并发容量。
teacher 的错误会继续进入一致性目标，不能将高一致性写成真实准确率。

## v2 实测结果

| 视频 | 时长 | 完整版 | 加速版 | 加速倍数 | 耗时/片长 | teacher→候选回合数 |
|---|---:|---:|---:|---:|---:|---:|
| 开发 demo_forrating2 | 70.97s | 32.51s | 16.80s | 1.93× | 0.237× | 3→4 |
| 开发 demo3_clip1 | 299.60s | 233.52s | 78.15s | 2.99× | 0.261× | 12→11 |
| 未用于本轮调参 deemo1 | 111.10s | 86.48s | 41.13s | 2.10× | 0.370× | 0→0 |
| 未用于本轮调参 demo3_clip2 | 303.27s | 224.33s | 75.76s | 2.96× | 0.250× | 12→11 |

不能将 deemo1 两版都是零解释成识别正确；teacher 本身没有检出回合，该样本
只能提供本轮速度和空输出一致性的证据，不能验证回合召回能力。

其余三段回合内时间交并比分别为99.10%、98.06%、94.78%。按±1秒一对一匹配：

- 短开发视频：三个 teacher 结束点全匹配，但多出一个切点，38.99–39.50秒的
  约0.51秒间隙将 teacher 的一个回合拆成两段。
- 长开发视频：11/12结束点匹配；未匹配的是 teacher 的140.00–140.40秒短段。
- clip2：11/12结束点匹配；未匹配的是 teacher 的90.72–91.87秒短段。
  匹配到的结束点平均偏差0.120秒、最大0.370秒。不能未经人工复核就将漏掉的
  1.14秒短段称为“发球失误”或认为可忽略。

这是可运行的独立加速候选，尚不能作为完整版无损替代。所有原始失败对照均
保留，没有通过改 teacher、使用 teacher 缓存或删掉不利视频来提高数字。
`final_report.json` 保留 teacher/候选文件哈希、模型哈希和未匹配事件。

验收：98项 pytest 通过。`review.html` 中四个真实视频均已验证加载、跳转和
播放；差异导航正常，桌面及390px手机布局无横向溢出、无 JavaScript 错误。
模型文件哈希与原完整版一致。完整结果见
`outputs/visual_acceleration_20261020/final_report.json`、
`review_data.json` 和 `review_qa.json`。
# Additional unchanged-parameter video check

At the owner's request, `deemo2.mp4` was selected before inference as a video
not previously used in this acceleration experiment. Its duration is 133.639s,
resolution 2880x1620. The full teacher and frozen v2 ran sequentially on local
CPU with two threads; no audio analysis or parameter changes were involved.

- Full teacher: 68.585929s, 7 intervals.
- Fast v2: 27.104916s, 5 intervals; 2.53x speedup, 0.203x video duration.
- Active-time IoU against teacher: 0.401550.
- At ±1s, starts match 1/7 (6 missing, 4 extra); ends match 2/7
  (5 missing, 3 extra). Missed teacher-active time: 15.3s; extra active time: 4.0s.

This materially weakens the earlier positive speed/quality result: v2 has not
demonstrated reliable agreement across videos. Teacher predictions remain a
comparison target, not human annotations. No causal explanation for this loss
has yet been verified. Preserve this negative result without tuning on it.

Review and machine-readable comparison:
`outputs/visual_acceleration_deemo2_20261020/review.html` and `review_data.json`.
The review overlays both states on the source video with synchronized timelines
and a jump-to-difference control. Browser playback, seeking and mobile layout
were checked with no JavaScript errors.
