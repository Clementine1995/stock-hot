# README.md

## 项目定位

**stock-hot**：本地运行的 A 股 / 金融热点信息站。从**开盘啦**拉取板块强度与市场情绪数据，自算「情绪温度」，通过本地 Web 站点三栏展示——**题材强度轮动（日历墙）** + **情绪温度面板** + **数字报表**，页面上点「刷新」更新最新数据。只在本地运行，不上云、不发布、不配域名和 HTTPS。

- 数据源：开盘啦匿名接口（`apiv=w42`，免 token / 免抓包），拿「板块强度」真值 + 涨跌/涨停/跌停家数。
- 情绪温度：开盘啦「市场情绪温度计 0–100」为私有指标，匿名接口不暴露，故用涨跌家数 + 涨停/跌停家数**自算**（口径见 `docs/requirements/REQ-001-金融热点面板.md` §5）。
- 技术栈：**Python 3 标准库，零第三方依赖**；本地常驻 Web 服务 + JSON 快照存储。

## 项目负责

- 采集开盘啦板块强度排名（全板块、按交易日）+ 市场情绪家数。
- 自算情绪温度（0–100），走强/走弱按强度正负切。
- 题材强度轮动日历墙（点题材跨卡高亮 + 底部轮动轨迹）。
- 情绪温度面板（三色温度计 + 近 N 日曲线）+ 数字报表。
- 页面「刷新数据」按钮：采集最近一个交易日落快照。

## 项目不负责

- 实时行情 / 交易引擎（如需接入，另行讨论）。
- 投资建议：内容仅为信息整理与统计，不构成投资建议、不荐股。
- 发布上线、域名、HTTPS、多用户服务。
- 开机自启 / 常驻守护 / 定时任务（当前为手动打开站点 + 手动点刷新）。

## 快速开始

```bash
# 启动站点（零依赖，标准库）
python server.py

# 浏览器打开 http://127.0.0.1:8000
# 页面上点「刷新数据」拉最新交易日；切标签看题材轮动 / 情绪温度 / 数字报表
```

其他脚本方式（均保留，可独立使用）：

```bash
python collect.py 2026-11-13      # 采集指定交易日落快照
python backfill.py 10             # 回补最近 10 个交易日（自动跳周末/节假日）
python render_wheel.py            # 单独生成轮动面板静态 HTML
python render_mood.py             # 单独生成温度面板静态 HTML
python run.py 2026-11-13          # 一条命令：采集→算温度→渲染→报表（静态产物）
python -m unittest discover -s tests   # 运行单元测试
```

产物：`output/`（静态 HTML / Markdown 报表，可随时重新生成）；数据：`data/`（按交易日 JSON 快照）。

## 技术栈与形态

- **语言**：Python 3（标准库 `urllib` / `http.server` / `json` / `unittest`），无第三方依赖。
- **服务**：`server.py` 内置 `http.server`，只绑定 `127.0.0.1`，不上云、不对外。
- **前端**：`web/index.html` 单页，原生 JS 三栏 + 刷新按钮。
- **存储**：`data/snapshot-YYYY-MM-DD.json`（JSON 快照），唯一读写入口在 `src/storage/store.py`。

## 目录结构

```
stock-hot/
├── server.py             # 本地常驻 Web 服务（主入口）
├── collect.py            # 采集单日快照
├── backfill.py           # 回补历史交易日
├── render_wheel.py       # 单独生成轮动面板 HTML
├── render_mood.py        # 单独生成温度面板 HTML
├── run.py                # 静态产物一条命令（采集→温度→渲染→报表）
├── web/
│   └── index.html        # 站点单页（三栏 + 刷新按钮）
├── src/
│   ├── collectors/       # 采集层：base.py（抽象）+ kaipanla.py（开盘啦实现）
│   ├── indicators/       # 指标层：mood.py（情绪温度自算）
│   ├── render/           # 渲染层：wheel.py / mood.py / report.py
│   └── storage/          # 存储层：store.py（快照读写，唯一访问点）
├── tests/                # 单元测试
├── data/                 # JSON 快照（数据资产，进 git）
├── output/               # 静态产物（派生，可重新生成，不进 git）
└── docs/
    ├── requirements/     # 需求文档 REQ-001
    └── HANDOFF.md        # 跨机接手说明
```

## 数据源与指标（摘要）

- **板块强度排名**：`RealRankingInfo` 接口（历史域 `apphis.longhuvip.com`），支持按 `Date` 回查历史；`st` 固定 30、`Index` 每页 +30 翻页；`errcode=1020` = 非交易日。字段：代码 / 名称 / 强度 / 涨跌幅 / 成交额 / 主力净额。
- **市场情绪**：`MoodNumCount` 接口（当日域 `apphwhq.longhuvip.com`），只返回当前最新（**不支持历史回查**），故情绪温度历史只能靠每天刷新累积。
- 完整字段映射见 `docs/research-开盘啦数据源调研.md`。

## 架构与扩展

分层（依赖单向，上层不反向依赖下层）：

```
采集层 collectors/  →  存储层 storage/  →  指标层 indicators/  →  展示/服务层 server.py + web/
```

- **加信源**（Tushare / 通达信 / AKShare）：新增 `Collector` 实现类。
- **加指标**（连板率、炸板率等）：`indicators/` 加纯函数 + 单测。
- **加面板**：`web/index.html` 加 tab + render 函数，`server.py` 的 `/api/data` 加字段。
- **DeepSeek 点评**：届时新增 `llm/` 模块，走「采集→计算→点评」后处理链路（待做）。
- 详细扩展点见 `docs/HANDOFF.md`。

## 文件地图（治理文档）

| 文件 | 角色 | 必读时机 |
| --- | --- | --- |
| `AGENTS.md` | 入口：授权边界、禁止事项、文档索引、开工清单 | 进入项目即读 |
| `ARCHITECTURE.md` | 架构红线与验证映射（通用工程红线，部分条款针对原 AIHOT 三进程场景，以实际代码为准） | 改架构、加接口前 |
| `STYLE.md` | 工程风格 | 写代码前 |
| `TESTING.md` | 测试纪律 | 写或改测试前 |
| `COLLABORATION.md` | 任务分级、协作生命周期、证据口径 | 任何非平凡任务前 |
| `WORKFLOW.md` | 命令唯一来源 | 执行任何命令前 |
| `REQUIREMENT.md` | 需求文档标准与模板 | 新功能、数据变化前 |
| `DOMAIN.md` | 金融热点站领域专项 | 开发时 |

## 权威层级

- 授权边界以 `AGENTS.md` 为准，架构红线以 `ARCHITECTURE.md` 为准，风格以 `STYLE.md` 为准，测试纪律以 `TESTING.md` 为准，协作与证据以 `COLLABORATION.md` 为准，命令以 `WORKFLOW.md` 为准，领域专项以 `DOMAIN.md` 为准。
- 各文件职责不得互相覆盖；同类事实只在一个文件里维护。
- 代码、测试和最新运行现场是事实的最高来源；文档与其不一致时，以实际为准并先报告差异。

## 待办

1. **DeepSeek 每日点评**（批次 4b）：待用户提供 API key，接入 `llm/` 读近 5 日趋势写点评。
2. **轮动面板编辑型工具栏**（反红 / 标增 / 删除 / 重排 / 保存，含本地标注持久化）：待用户需要时单独批。
3. **快照 schema 扩展**：若要加龙虎榜 / 涨停梯队 / 连板率等新数据维度，建议先把快照改成分类型文件（`data/日期/plates.json`、`mood.json`、`lhb.json`…）。
4. **README 中 ARCHITECTURE.md 的定位说明**：其红线模板有部分条款（迁移、缓存、多用户）不适用于本项目，后续可精简为贴合本项目的版本。
