# 🎬 《奥德赛》影院排片监控

一个基于 **Python + GitHub Actions + 猫眼 H5 API + Bark** 的自动排片监控程序。

当指定影院的《奥德赛》出现新的目标日期场次时，程序会自动通过 Bark 推送通知。

## 🧩 项目结构

```text
movie-odyssey-monitor/
├── monitor.py                 # 核心监控程序
├── state.json                 # 已知排片状态，由程序自动维护
├── .github/
│   └── workflows/
│       └── monitor.yml        # GitHub Actions 自动运行配置
└── README.md                  # 项目说明
```

### `monitor.py`

负责核心监控逻辑：

1. 请求猫眼 `cinemaDetail` H5 API；
2. 定位目标电影《奥德赛》（movie ID `1545360`）；
3. 查询配置的目标日期；
4. 解析放映时间、影厅、语言/版本；
5. 与 `state.json` 中已经记录的场次比较；
6. 发现新的目标日期场次后，通过 Bark 推送到 iPhone；
7. 推送后约 2 分钟再次发送相同内容，作为重复提醒；
8. 更新 `state.json`。

### `monitor.yml`

GitHub Actions 工作流配置，负责提供云端运行环境并按照设定的时间表启动 Python 程序。

自动任务原配置为每 5 分钟运行一次。目前自动 `schedule` 已暂停，但仍保留 `workflow_dispatch`，因此可以手动运行程序或测试 Bark 推送链路。

### `state.json`

程序的历史状态文件，用于记录已经发现过的排片，避免同一场次在后续运行中重复触发通知。

## 🎯 为什么不比较“排片总数”？

不能简单使用：

```text
当前排片数量 > 上次排片数量 → Bark
```

因为已经放映完的场次会从猫眼下架。例如：

```text
昨天：34 场
今天：29 场
```

即使今天开放了新的目标日期场次，总数仍然可能下降。

因此程序按**目标日期 + 具体场次**记录历史。只要目标日期出现以前没有记录过的新场次，就会触发通知。

## 📅 修改监控日期

在 `monitor.py` 中修改 `TARGET_DATES`：

```python
TARGET_DATES = [
    "2026-09-04",
    "2026-09-05",
    "2026-09-06",
]
```

可以同时设置多个日期，例如：

```python
TARGET_DATES = [
    "2026-10-01",
    "2026-10-02",
    "2026-10-03",
]
```

日期格式为 `YYYY-MM-DD`。

## 🔔 Bark

Bark Key 不写入代码，而是通过 GitHub Actions Secret 保存：

```text
BARK_KEY
```

程序运行时通过环境变量读取：

```python
os.environ.get("BARK_KEY")
```

不要将真实 Bark Key 直接写入代码、README 或其他提交文件。

## ▶️ 手动运行

GitHub → **Actions** → **Monitor The Odyssey** → **Run workflow**。

如果勾选：

> Send a Bark test notification to the iPhone

程序会进入测试模式，只测试 Bark 推送链路，不执行正常排片监控。

## ⏸️ 自动任务

自动监控通过 GitHub Actions 的 `schedule` 运行。需要停止自动监控时，可以暂停或移除 workflow 中的 `schedule` 配置；需要恢复时，再启用相应的 cron 配置即可。

手动 `workflow_dispatch` 可以继续用于测试和临时运行。

## 🛠️ 技术栈

- Python
- `requests`
- `beautifulsoup4`
- 猫眼 H5 API
- GitHub Actions
- Bark
- JSON

## 🔄 工作流程

```text
猫眼 API
   ↓
Python 获取并解析排片
   ↓
state.json 记录历史
   ↓
发现新的目标日期场次
   ↓
Bark
   ↓
iPhone 通知
```

GitHub Actions 负责在云端按照计划运行整个监控程序。
