# 回合结果数据契约

## 公共核心

内存中为 Python 字典包裹的回合列表，文件为 UTF-8 JSON。
`rallies` 按时间排列，元素表示半开时间区间 `[start,end)`。
时间单位为视频时间线上的秒，浮点数，不是帧号或 Unix 时间。

```json
{
  "schema_version": 1,
  "rallies": [
    {"start_seconds": 6.401, "end_seconds": 50.112, "needs_review": true},
    {"start_seconds": 59.645, "end_seconds": 82.955, "needs_review": true}
  ]
}
```

这是简化示例，数值已四舍五入。空列表合法，表示模型未检出，不能证明没有回合。
区间外是模型判断的回合外。`needs_review` 是待复核标志，不是数值置信度；
没有校准后的回合置信度字段。接入方保留原浮点精度，展示时才格式化。
合法区间满足 `0 <= start < end <= duration`。

## 加速/实验 CLI

主要文件为 `outputs/<job>/rallies.json`：

| 字段 | 含义 |
|---|---|
| schema_version | 当前 1 |
| status | candidate_predictions |
| method | 完整 CPU：upstream_rallyclip_tcn_cpu；加速：experimental_rallyclip_visual_accelerated |
| video | path、duration_seconds、width、height、native_fps、流索引/起始时间等 |
| wall_seconds | benchmark 内分析计时，不包含最终报告、脚本启动、视频导出 |
| visual_stats | providers、threads、加速调用计数、audio_used=false 等审计 |
| rallies | start_seconds、end_seconds、evidence、needs_review |
| limitations | 本次运行的限制 |

`rallies.csv` 列为 `rally,start_seconds,end_seconds,needs_review`，从 1 编号；
实验 JSON 的回合没有持久 ID，以数组次序编号。
`model_scores.npz` 为捕获的模型轨迹，`benchmark_audit.json` 为配置/耗时审计。
加速 CLI 默认不导出 MP4，并拒绝覆盖已有输出目录。

`video` 中音频流索引等是容器元数据，不是音频特征；本次两条主路径均纯画面推理。

## 本地前端

完成文件为 `data/jobs/<job-id>/result.json`，页面下载名为 `rallies.json`。

| 字段 | 含义 |
|---|---|
| filename / duration_seconds | 输入名 / 分析视频时长 |
| analysis_seconds | 完整模型分析耗时 |
| export_seconds / total_seconds | 导出 / worker 总耗时，不包含浏览器上传和排队 |
| rallies | 另有从 1 开始的 id 和 duration_seconds |
| scores / poses | 真实模型分数 / 显示骨架（长视频显示可能抽稀） |
| model | name、实际 device、fallback_reason、权重 SHA-256、执行 sessions |
| source_video | 原始编码、尺寸、起始时间戳、方向 |
| input_normalized / inference_source | 是否先归一化方向/起始时间及实际推理源 |
| media_converted / pose_playback_offset_seconds | 播放转换与骨架对齐 |
| needs_review / notes | 复核标志与说明 |

`clips/rally_001.mp4` 等为重编码切片，时间受视频帧量化限制。
`clips.zip` 内的 `rallies.json` **仅为回合数组**，不是完整结果对象。
CLI 与 UI 的外层结构不能混用，公共部分为 `rallies` 及区间语义。

通常视频从 0 计时。非零/异常起始时间戳或旋转可能先归一化，须结合
`source_video`、`input_normalized`、`inference_source` 理解，
不能把结果秒数直接当成原容器的绝对 PTS。

## 接入约定

每个任务独立输出目录，记录输入文件哈希与算法配置；子进程成功退出后读完整 JSON。
失败保留日志，不以空数组伪装成功。消费已知字段并允许附加字段，保存 schema_version。
人工修订另存，保留模型原结果便于追溯。

## 纯视觉并集 v2

`run_visual_union.ps1` 输出到 `fused/rallies.json`：
`method=boundary_union_cpu`、`pipeline_version=visual_union_v2`。
`rallies` 仍是动作支持的开始/结束区间。`boundaries` 保留并集边界及来源；
`timeline_segments` 为全视频分区，动作外区间不进入回合数组。
`activity_recovery` 记录原始最终段数、恢复长段及原60秒上限。
段级 `restored_long_activity` 表示来自恢复长段，
`exceeds_original_duration_limit` 表示拆分后仍超原上限；均须复核。
`timings.cached_rallyclip/cached_scenes` 指明是否显式复用，
`current_invocation_analysis_seconds` 才是本次调用计时；
复用时不要把旧阶段时间相加当作新端到端测速。

可选分区检测通过 `--scene-profile regional` 启用。
`scene_profile` 为 `global` 或 `regional`，`scene_detection` 保留剪辑检测参数；
分区模式另含 `region_cut_candidates_seconds` 和 `regions_normalized_xyxy`，
便于追溯是全图、左下部还是右下部触发。区域坐标固定，不是人体追踪框。
同一采样时刻多个区域触发只保留一个剪辑点。不同时间的区域候选不相互
强行吸附，仍按既有并集规则与动作边界去重。
明确复用场景结果时校验模式，不允许请求分区却悄悄读取旧全图缓存。
