# 旧剪辑 demo：同一CPU模型复查（2026-10-19）

用户看过原片叠加视频后，要求用当前模型试一下之前依赖剪辑接缝演示的
那段视频。此次仅复查该历史样本，不恢复它作为完整训练视频的主测试。

- 输入：`E:\Built\TennisVision\Tennis_Vision\assets\demo\demo.mp4`，视频流57.90秒。
- 相同 RallyClip v0.5.0 预训练权重，5fps、416姿态输入、CPU两线程。
- 没有调参、再训练、加入剪辑检测或把人工时间交给模型。
- 实际推理14.1238秒，仅输出 **0.4387—57.3509秒，一段候选**。
- 人工原标注5回合；9、17、36、45秒这4个内部结束，在±2秒内全部未匹配。
- 片尾58秒是视频结束，不应算作成功找到内部回合分界。叠加标注按视频流
  时长截到57.90秒，原始58保存在派生标注的 `reported_end_seconds`；原fixture未改。

预测、CPU审计、派生结束标注和内部匹配摘要保存在
`outputs/demo_edited_rallyclip_416/`。该结果与旧的接缝检测结果是两种方法，
不可把旧的接缝对齐分数当作当前时序模型的成绩。

已渲染 `outputs/demo_edited_rallyclip_416_rendered/prediction_cpu416.mp4`，
1280×864、30fps、57.90秒、保留音频，展示预测区间和人工结束标记。
CPU编码耗时8.78秒，单独记录，不计入识别耗时。渲染目录保留ASS、编码日志
及审计。浏览器播放/跳转及整段音视频解码检查通过；36个代码测试通过。

此次结果表明当前配置未能拆开这段拼接demo。等待时间被剪掉、动作上下文
不连续是待验证的解释，不能据此认定所有少量剪辑都会失败，也不能声称
混剪处理已经完成。没有使用GPU或新API调用。

推理复现：

```powershell
.\.venv\Scripts\python.exe tools/benchmark_rallyclip.py outputs/upstream_rallyclip/RallyClip-main 'E:\Built\TennisVision\Tennis_Vision\assets\demo\demo.mp4' --output outputs/demo_edited_rallyclip_416 --threads 2 --imgsz 416
```

## 2026-10-20：按用户要求重新运行剪辑接缝检测

用户进一步明确用原来的剪辑痕迹算法识别此视频。重新运行 `edited` 模式
（OpenCV/PySceneDetect诊断，4fps、320宽、CPU两线程），没有用人体姿态或
人工时间干预检测。检测耗时5.985秒，输出9.75、16.75、36.75、45.00秒四个
剪辑点，形成5段。对原始人工内部结束9、17、36、45秒，±1秒内4/4对齐，
平均绝对偏差0.4375秒；片尾未计入这4个内部匹配。

输出保存在 `outputs/demo_edited_seams_20261020/`，含原始特征、检测结果、
指标、派生叠加结束标注与 `seam_recheck_summary.json`。旧预测没有覆盖。
`outputs/demo_edited_seams_20261020_rendered/prediction_seams.mp4` 为57.90秒
的叠加视频，显示剪辑分段编号，并在接缝处闪现检测时间，与人工结束分别
展示。渲染约7秒，和检测时间分开计量，具体耗时以审计JSON为准。播放/跳转、整段解码和10秒画面
检查通过，代码36个测试通过。播放页为同目录 `review.html`。

此结果只说明接缝检测在此剪辑样本上能对齐切口，不能转述为完整训练视频
回合识别准确率。剪辑模式仍是辅助诊断；未更改连续原片识别逻辑。

```powershell
.\.venv\Scripts\python.exe -m rallycut.cli analyze 'E:\Built\TennisVision\Tennis_Vision\assets\demo\demo.mp4' --mode edited --fps 4 --width 320 --threads 2 --output outputs/demo_edited_seams_20261020 --labels tests/fixtures/demo.manual.v1.json
.\.venv\Scripts\python.exe tools/render_prediction_video.py outputs/demo_edited_seams_20261020/rallies.json outputs/demo_edited_seams_20261020/manual_end_overlay.json --output outputs/demo_edited_seams_20261020_rendered/prediction_seams.mp4
```
