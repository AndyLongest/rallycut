# RallyCut · 团队技术交付

本次提供源码交接与已经验证的完整模型 Windows 应用，另含纯视觉加速 v2 独立 CLI。

## 下载与启动

- `RallyCut-Windows-x64-Light.zip`：263,122,848 字节，完整解压后双击 `Start.cmd`。
  CPU 运行环境、官方模型、FFmpeg 已包含。GPU 依赖独立安装，见包内 GPU_SETUP.md。
- `RallyCut-Windows-x64-Light.zip.sha256`：下载完整性校验。
- `HANDOFF.md` / `RESULT_CONTRACT.md`：技术交接及 JSON 数据接口说明。
- GitHub 自动生成的 Source code ZIP：源码，不包含模型或 Python 环境；
  源码准备使用 `setup.ps1`，固定上游与权重通过 `upstream-lock.json` 校验。

交接主文档：[HANDOFF.md](https://github.com/AndyLongest/rallycut/blob/main/docs/HANDOFF.md)。

## 版本区分

Windows ZIP 是已验收的完整960/5fps应用0.2.0，支持可选GPU自动回退CPU。
加速 v2 在源码中，使用 `run_fast_visual.ps1`，目前只走CPU，尚未接入该 ZIP 前端。
两条交付主路径均只使用画面做切分。历史音频/Gemini/剪辑并集实验不是默认交付入口。

开发视频 demo3_clip1（299.60s）：完整233.52s → 加速78.15s，teacher12段 → 加速11段。
这是本机两线程分析时间，不含导出；98.06%时间IoU是teacher一致性，不是人工准确率。
独立业务数据准确率、业务服务器性能、加速版前端接入仍待团队验收。

## 验证

- 完整开发环境：103项测试通过。
- 全新CPU环境：99项通过，1个可选Gemini模块跳过；pip check无冲突。
- 新环境、新解压上游完成真实视频的完整/加速两条推理。
- 上游90个关键文件校验；Light ZIP CRC及3593个清单文件校验通过。
- 对照页播放、差异跳转、移动布局检查通过。

Light ZIP SHA-256：
`672c56dbf2f5f06b38cb38370f4e900efed1ab141a9e7d3cc0092ec8f2376ec9`

私人视频、任务数据、密钥没有进入源码或交付包。上游源码快照缺根 LICENSE，
代码及模型的对外分发/商用授权尚需团队确认；第三方声明随包保留。
