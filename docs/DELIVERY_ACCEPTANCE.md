# 本次交付验收 · 2026-10-20

本记录针对团队私有仓库的交付完整性，不构成真实业务准确率/服务器性能验收。

## 已完成

- 当前完整开发环境回归：103 passed（包含已安装的可选 Gemini SDK 测试）。

- 固定上游 commit `ebf1a82b9853ae62d03f4da2c2b8a0d647a48261`。
  从官方归档获取的 82 个 src 文件与本地实验上游逐字节一致。
- 官方 v0.5.0 模型归档 SHA-256 与发行方校验一致；
  bootstrap 对源码、模型等 90 个关键文件逐个校验。
- 全新 Python 3.12 x64 虚拟环境，仅按 requirements-runtime.txt 和项目 test
  extra 安装；`pip check` 无冲突。
- 全新环境测试：99 passed、1 skipped。跳过的是未安装可选 google-genai SDK
  的历史 Gemini 模块；本次纯视觉运行不依赖该 SDK。
- 全新环境与新解压上游实际执行 `demo_forrating.mp4`（42.57s）的完整与加速推理，
  两者均成功输出 3 个候选区间；CPUExecutionProvider，audio_used=false。
  此为环境恢复冒烟测试，不是速度或准确率对比实验。
- 历史 Light ZIP 重新通过 CRC 和 3,593 个清单文件 SHA-256 检查。
  应用 `data/` 没有用户任务，模型和 CPU 环境齐全；没有重新打入 GPU 大型依赖。
- 原完整版 GPU/CPU 安装验收、中文路径解压和 HTTP 启动证据保持有效：
  发行包字节未变，详见 OPTIONAL_GPU_PACKAGE_20261020.md。

## Release 资产

`RallyCut-Windows-x64-Light.zip`，263,122,848 字节：

```text
672c56dbf2f5f06b38cb38370f4e900efed1ab141a9e7d3cc0092ec8f2376ec9
```

源码项目中的独立验证命令：

```powershell
python tools/verify_release.py RallyCut-Windows-x64-Light.zip `
  --sha256 672c56dbf2f5f06b38cb38370f4e900efed1ab141a9e7d3cc0092ec8f2376ec9
```

根目录 README、技术交接、结果契约、模型版本锁、CI 和问题模板一起进入源码。
Windows ZIP 是已验收过的完整应用；加速入口和此次新交接说明在源码中。
运行视频由接手者自行提供，测试夹具只包含人工时间标注，不包含私人媒体。

## 仍由团队验收

业务服务器实测、独立机位人工标注、上游许可确认、对公网部署和加速模式前端接入
均未在此轮完成，也没有包装成完成项。GitHub CI 只验证源码测试；
没有原视频/模型时不能声称它执行了全量视觉回归。
