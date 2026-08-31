# 🎬 《奥德赛》影院排片监控

一个基于 **Python + GitHub Actions + 猫眼 H5 API + Bark** 的自动排片监控小程序。

它的目标很简单：当指定影院的《奥德赛》出现**新的目标日期场次**时，自动通过 Bark 推送到 iPhone。

> 本项目最初用于监控 **MOViE MOViE 前滩太古里** 的《奥德赛》开票情况。

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

负责真正的“干活”：

1. 请求猫眼 `cinemaDetail` H5 API；
2. 找到目标电影《奥德赛》（movie ID `1545360`）；
3. 查询指定目标日期；
4. 解析放映时间、影厅、语言/版本；
5. 与 `state.json` 中已经见过的场次比较；
6. 如果发现新场次，通过 Bark 推送到 iPhone；
7. Bark 推送后会延迟约 2 分钟再次发送相同内容，作为防漏看提醒；
8. 更新 `state.json`。

### `monitor.yml`

这是 GitHub Actions 的“定时器 + 运行环境”。

它负责在 GitHub 云端启动 Python 程序，并安装 `requests`、`beautifulsoup4` 等依赖。

原来的自动监控频率为**每 5 分钟一次**。本次《奥德赛》购票完成后，定时任务已经暂停，但仍保留 `workflow_dispatch`，以后可以手动运行测试。

### `state.json`

这是程序的“记忆”。

它记录已经发现过的排片，避免同一场次每 5 分钟重复报警。

## 🎯 为什么不是比较“排片总数”？

这是这个项目实际踩过的坑。

如果简单判断：

```text
当前排片数量 > 上次排片数量 → Bark
```

就会漏掉真正重要的“新日期开票”。

例如：

```text
昨天：34 场
今天：29 场
```

即使今天突然开放了目标日期的新场次，总数仍然可能下降，因为已经放映完的场次同时从猫眼下架。

因此本项目采用的是：

> **按目标日期 + 具体场次记录历史，发现该目标日期以前没有见过的新场次就报警。**

这才符合“9 月 4 日开票了就告诉我”的实际需求。

## 📅 修改监控日期

打开 `monitor.py`，修改：

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

日期使用 `YYYY-MM-DD` 格式。

## 🔔 Bark

Bark Key 不写进代码，而是通过 GitHub Actions Secret：

```text
BARK_KEY
```

程序运行时通过环境变量读取：

```python
os.environ.get("BARK_KEY")
```

因此即使仓库公开，也不要把真实 Bark Key 直接写进 `monitor.py`、`README.md` 或其他提交文件。

## ▶️ 手动运行

GitHub → **Actions** → **Monitor The Odyssey** → **Run workflow**。

如果勾选：

> Send a Bark test notification to the iPhone

程序会进入测试模式，只测试 Bark 推送链路，不执行正常排片监控。

## ⏸️ 当前状态

**2026-09-01：项目任务完成。**

《奥德赛》已经成功购票，因此自动排片监控已暂停。

以后如果有新的电影/日期需要监控，可以重新启用 `monitor.yml` 中的 `schedule`，或者基于本项目复制一个新的监控项目。

## 🛠️ 技术栈

- Python
- `requests`
- `beautifulsoup4`
- 猫眼 H5 API
- GitHub Actions
- Bark
- JSON

## ❤️ 项目小结

这个项目本质上是一个很小但完整的自动化系统：

```text
猫眼 API
   ↓
Python 解析排片
   ↓
state.json 记录历史
   ↓
发现新场次
   ↓
Bark
   ↓
iPhone 通知
```

而 GitHub Actions 负责让它按照计划在云端自动运行。

---

**Mission accomplished. 🎬🍿**
