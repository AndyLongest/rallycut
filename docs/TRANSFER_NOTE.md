# 可转发给技术总监

项目：RallyCut，本地网球回合切分。源码和交接文档：
https://github.com/AndyLongest/rallycut

先读 `docs/HANDOFF.md`，数据对接看 `docs/RESULT_CONTRACT.md`。
Releases 下载 Windows Light ZIP，完整解压后双击 Start.cmd 即可上传视频使用；
CPU 环境和模型都在包内，GPU 为可选安装。

目前有两个入口：

- 完整版：一键前端，官方960/5fps模型，支持 GPU 自动回退 CPU。
- 加速 v2：源码独立 CLI，仅画面、CPU运行。setup.ps1 准备环境后运行
  `run_fast_visual.ps1 -Video <视频路径> -Output <新目录>`。

5分钟开发视频的模型分析耗时约234秒降至78秒；这是本机实测，
不是业务服务器指标。加速版尚未接入前端，也没有完成跨机位准确率验收。
模型输出为候选时间段 JSON，建议保留人工复核。

源码包含固定上游/权重下载校验、依赖清单、测试、历史实验、故障定位和验收清单。
仓库私有，访问需项目拥有者授予权限。原始私人视频未随仓库分发。
