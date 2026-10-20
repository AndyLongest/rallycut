# 技术交接与验收 · 2026-10-20

## 交付状态

独立 RallyCut 项目：本机上传视频、纯画面回合切分、复核及导出。
不依赖其他工作区项目、云端账号或业务数据库。尚未部署业务服务器。
当前完整版本与加速 v2 均保留；加速 v2 是流水线优化，没有新训练学生模型。

Release 的 Windows Light ZIP 是已经验收过的完整模型应用 0.2.0；
加速 v2 位于源码中，尚未接入该 ZIP 前端。不能把 ZIP 的耗时当成加速版耗时。
源码标签 `v0.2.0-handoff.1` 表示交付快照，不表示重训模型。

## 给使用者：五步启动

1. 从 Releases 下载 `RallyCut-Windows-x64-Light.zip`，完整解压到可写目录。
2. 双击 `Start.cmd`，浏览器自动打开；不需安装 Python/Node/FFmpeg。
3. 上传至少 20 秒、720p 的视频。上限 8GiB；准备约原视频三倍加 512MiB 空间。
4. 等待准备、分析、导出完成，查看骨架、分数、时间轴，复核后下载 JSON/MP4。
5. 双击 `Stop.cmd` 退出。关浏览器不会停止分析；网页删除只删除应用内任务副本。

默认 CPU 可用。GPU 按 `GPU_SETUP.md` 安装到 `runtime/gpu-site-packages`，
不能覆盖 CPU 基础环境。实际设备/回退原因在页面与结果中可见；
AMD/Intel 显卡暂走 CPU。更多说明见 [PORTABLE_APP.md](PORTABLE_APP.md)。

## 开发者从源码恢复

Windows 验证环境为 Python 3.12 x64，项目依赖安装到项目自己的 `.venv`。

```powershell
git clone https://github.com/AndyLongest/rallycut.git
cd rallycut
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

脚本安装 CPU 依赖及项目，下载并校验固定上游。上游 commit
`ebf1a82b9853ae62d03f4da2c2b8a0d647a48261`，模型 `rallyclip_v0.5.0`；
`upstream-lock.json` 固定归档和 90 个关键文件的 SHA-256。
已有上游被修改时会报错，不自动覆盖；需要保留自己的修改后另选目录。

FFmpeg 准备任选其一：

- 从 Light ZIP 复制整个 `runtime/ffmpeg` 到本源码的 `runtime/ffmpeg`，
  `Start-Source.cmd` 与 `run_fast_visual.ps1` 自动找到项目内媒体工具。
- 开发机自行安装带 libx264 的 FFmpeg，把 `ffmpeg` 和 `ffprobe` 放到 PATH。
  直接用 Python CLI 时可设 `$env:PATH="$PWD\runtime\ffmpeg\bin;$env:PATH"`。

完整前端：双击 `Start-Source.cmd`。源码模式停止命令：

```powershell
.\.venv\Scripts\python.exe -m rallycut.local_app --stop
```

加速版（每次输出新目录）：

```powershell
.\run_fast_visual.ps1 -Video 'D:\videos\training.mp4' -Output 'outputs\fast_case_01'
```

完整版 CPU 对照，不导出 MP4：

```powershell
$env:PATH="$PWD\runtime\ffmpeg\bin;$env:PATH"
.\.venv\Scripts\python.exe tools/benchmark_rallyclip.py `
  outputs/upstream_rallyclip/RallyClip-main 'D:\videos\training.mp4' `
  --output outputs\full_case_01 --threads 2 --capture-scores
```

生成同一视频两版同步叠加对照：

```powershell
New-Item -ItemType Directory outputs\comparison_01
.\.venv\Scripts\python.exe tools/build_acceleration_review.py outputs\comparison_01 `
  --pair '完整 / 加速' ..\full_case_01 ..\fast_case_01
```

浏览器打开 `outputs/comparison_01/review.html`。源视频须在结果记录的位置；
分享页面时需另外提供有权共享的视频并重建页面，仓库不包含私人视频。

Linux CPU 接手：Python 3.12 建 `.venv`，安装 `requirements-runtime.txt` 与
`pip install -e '.[test]'`，运行 `tools/bootstrap_upstream.py`，准备 FFmpeg 后
执行相同 Python 命令。本次未在 Linux/业务服务器实测，Windows 启动器和便携包
不能用于 Linux。

浏览器自动化为维护者可选工具，普通用户不用 Node。维护者安装 Node 后运行
`npm ci`，再运行 `npm run qa:review -- outputs/comparison_01`。
Windows 默认用系统 Edge；其他系统先执行 `npx playwright install chromium`。
`qa_portable_ui.cjs` 是历史固定样本验收，需要隔离的测试安装包，以及环境变量
`RALLYCUT_QA_VIDEO`（demo_forrating2 原片）、`RALLYCUT_QA_REFERENCE`
（其 smoke_verification.json，包含 intervals 数组）。它会上传、取消和删除
测试任务，不要对用户正在工作的安装目录执行。原片由拥有者另行提供。

## 业务集成

先用独立 CLI 子进程接入：提供输入路径、唯一输出目录，成功退出且 JSON 完整后
读取结果。非零退出保留日志并标记失败，不能用空列表替代失败。
不要解析实验脚本的标准输出，也不要在同一个 Python 进程并发调用加速适配器，
它通过作用域内替换上游方法实现优化。

公共数据接口为 `rallies: [{start_seconds,end_seconds,...}]`，
见 [RESULT_CONTRACT.md](RESULT_CONTRACT.md)。UI 与 CLI 外层 JSON 不同。
只要切点的业务应使用 CLI，避免为取时间段而先导出所有 MP4。
模型分析、转码/导出、排队/上传时间分别统计。

前端绑定 `127.0.0.1`，单任务串行执行，接口带本机 token。它是本地应用，
不能直接暴露公网。服务器接入需另做身份验证、任务队列、配额和文件隔离。
CPU 两线程设置不是严格两核资源隔离；业务服务器资源与并发尚未验证。

## 最小验收清单

- [ ] `tools/bootstrap_upstream.py --verify-only` 通过并记录版本。
- [ ] `python -m pytest -q` 全部通过。
- [ ] ZIP SHA-256 与 Release 附件一致，中文/空格路径可启动。
- [ ] 视频上传、播放、JSON/切片下载、取消/停止可用。
- [ ] 无 GPU 依赖仍能完成 CPU 分析；GPU 模式记录实际执行设备与回退原因。
- [ ] 加速版独立分析同一视频，区间合法、可回放，实际耗时有记录。
- [ ] 在不同机位/距离/光照视频上标注起止，分别测漏检、误检和边界误差。
- [ ] 在目标服务器记录 CPU/配额、内存、视频编码/尺寸、并发及耗时/视频时长。

本机证据见 [DELIVERY_ACCEPTANCE.md](DELIVERY_ACCEPTANCE.md)；
历史完整包 CPU/GPU 验收见 [OPTIONAL_GPU_PACKAGE_20261020.md](OPTIONAL_GPU_PACKAGE_20261020.md)。
`tests/fixtures/demo3_clip1.manual_ends.v1.json` 只有结束标注，
不能从中推造开始点或区间准确率。

## 故障定位

| 现象 | 检查与处理 |
|---|---|
| 双击未启动 | `data/logs/launcher.log`；完整解压到可写目录 |
| 分析失败 | `data/jobs/<id>/worker.log`；检查时长/720p/文件完整性/时间戳 |
| 缺模型 | 源码跑 bootstrap 校验；便携包重新完整解压，保留日志 |
| GPU 回退 | 看 fallback_reason，按 GPU_SETUP 校验独立依赖与驱动 |
| CLI 缺 FFmpeg | 准备项目内媒体工具或 PATH，再用 run_fast_visual.ps1 |
| 加速漏段/合并 | 保留视频、rallies.json、model_scores.npz，与完整版/人工标注对照 |
| 磁盘占用大 | 从前端删除不要的任务；任务目录含上传副本，不要删用户原片 |
| 0 个回合 | 是模型未检出，不能证明没有回合，须人工核查 |

## 后续优先级与范围

先验收真实业务数据与 CPU 服务器，明确边界容差及短发球策略；再围绕全图重定位、
裁图漂移、人物缺失与球场 mask 加诊断。加速达标后再接入 UI/任务队列，
保留完整版用于对照。开发样本的 teacher 一致性不是人工准确率。
deemo2 按负责人要求排除后续测试和方案评价，历史记录保留。

上游源码快照没有根 LICENSE，其代码/模型及姿态权重、FFmpeg 的许可需团队在
对外分发前确认；本项目不代上游授予许可。私有交接不代表已经取得商用授权。
