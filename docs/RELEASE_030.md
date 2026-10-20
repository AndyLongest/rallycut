# RallyCut 0.3.0 · 前端默认分区并集

上传视频后默认执行纯视觉加速v2 + 全图/左右分区剪辑检测 + 边界并集，
无需选择命令行模式。修复持续活动因超过60秒而整段丢失的问题；
时间轴标注剪辑候选，JSON和MP4按同一份结果导出。
保留GPU优先/CPU回退；剪辑检测使用CPU，不分析音频。

下载 `RallyCut-Windows-x64-Light-0.3.0.zip`，完整解压后双击 `Start.cmd`。
运行环境与模型包含在包内；GPU依赖按 `GPU_SETUP.md` 独立安装。
旧0.2.0包不会自动升级，历史包保持原样。

- 112项测试通过；实际网页上传、播放、下载和中文目录解压后的CPU运行通过。
- 51秒漏检开发样本补出候选，尚未完成独立业务准确率验收，切点需复核。
- 输入仍要求至少20秒、720p。
- ZIP：263,178,727字节；SHA256：
  `058d9697b805316452239a31b69a8d16d667da20c4e61d1d7c845ef1e7c23418`

技术交接见 [HANDOFF.md](https://github.com/AndyLongest/rallycut/blob/main/docs/HANDOFF.md)，
本版验收见 [FRONTEND_UNION_030.md](https://github.com/AndyLongest/rallycut/blob/main/docs/FRONTEND_UNION_030.md)。
