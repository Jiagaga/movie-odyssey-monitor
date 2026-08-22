import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


CINEMA_ID = 37534
MOVIE_ID = 1545360

CINEMA_NAME = "MOViE MOViE 前滩太古里"
MOVIE_NAME = "奥德赛"

CINEMA_URL = f"https://www.maoyan.com/cinema/{CINEMA_ID}"

STATE_FILE = Path("state.json")

MONITOR_DAYS = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.maoyan.com/",
}


def load_state():
    if not STATE_FILE.exists():
        return {"showtimes": []}

    try:
        return json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )
    except Exception:
        return {"showtimes": []}


def save_state(showtimes):
    data = {
        "updated_at": datetime.now().isoformat(),
        "showtimes": sorted(showtimes),
    }

    STATE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_page():
    print(f"Fetching Maoyan cinema page:")
    print(CINEMA_URL)

    response = requests.get(
        CINEMA_URL,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    if len(response.text) < 10000:
        raise RuntimeError(
            f"Maoyan page is suspiciously short: "
            f"{len(response.text)} bytes"
        )

    print(
        f"Maoyan page downloaded: "
        f"{len(response.text)} bytes"
    )

    if MOVIE_NAME not in response.text:
        raise RuntimeError(
            f"Movie '{MOVIE_NAME}' was not found "
            f"in Maoyan page HTML."
        )

    print(f"Found movie '{MOVIE_NAME}' in page HTML.")

    return response.text


def extract_movie_section(html):
    """
    尝试定位《奥德赛》所在的影院页面区域。

    猫眼页面结构可能变化，因此这里采用多层
    fallback，而不是依赖一个非常脆弱的 CSS class。
    """

    soup = BeautifulSoup(html, "html.parser")

    # 第一优先：找到包含“奥德赛”的标题节点
    candidates = []

    for tag in soup.find_all(
        ["h1", "h2", "h3", "h4", "div", "span", "a"]
    ):
        text = tag.get_text(" ", strip=True)

        if text == MOVIE_NAME:
            candidates.append(tag)

    if not candidates:
        raise RuntimeError(
            f"Could not locate exact movie heading "
            f"'{MOVIE_NAME}'."
        )

    movie_node = candidates[0]

    print(
        f"Located movie node: "
        f"<{movie_node.name}>"
    )

    # 向上寻找包含排片表的较大容器
    parent = movie_node

    for _ in range(8):
        if parent.parent is None:
            break

        parent = parent.parent

        text = parent.get_text(
            " ",
            strip=True,
        )

        # 一个合理的电影排片区域通常会包含：
        # 放映时间 / 语言版本 / 放映厅
        if (
            "放映时间" in text
            and "语言版本" in text
            and "放映厅" in text
        ):
            print(
                "Found movie schedule container."
            )
            return parent

    # fallback：返回 movie node 的父级
    return movie_node.parent


def parse_date_from_text(text, reference_year):
    """
    从文本中寻找：
    8月29
    8月30日
    今天
    等日期。

    返回 YYYY-MM-DD。
    """

    # 今天
    if "今天" in text:
        return datetime.now().date()

    match = re.search(
        r"(\d{1,2})月(\d{1,2})日?",
        text,
    )

    if not match:
        return None

    month = int(match.group(1))
    day = int(match.group(2))

    try:
        return datetime(
            reference_year,
            month,
            day,
        ).date()

    except ValueError:
        return None


def parse_showtimes(html):
    """
    从猫眼影院网页中提取《奥德赛》的排片。

    注意：
    如果页面结构发生变化导致完全解析不到数据，
    这里会抛异常，而不是返回空列表。
    """

    container = extract_movie_section(html)

    text = container.get_text(
        "\n",
        strip=True,
    )

    # 检查页面是否真的包含排片相关字段
    required_words = [
        "放映时间",
        "语言版本",
        "放映厅",
    ]

    for word in required_words:
        if word not in text:
            raise RuntimeError(
                f"Movie section does not contain "
                f"expected field: {word}"
            )

    # -------------------------------------------------
    # 猫眼网页通常会把每个日期对应的排片表
    # 放在相邻的结构中。
    #
    # 这里先从所有 table 中提取《奥德赛》的
    # 时间 / 语言 / 影厅。
    # -------------------------------------------------

    tables = container.find_all("table")

    print(
        f"Found {len(tables)} schedule tables "
        f"in movie section."
    )

    results = []

    today = datetime.now().date()
    end_date = today + timedelta(
        days=MONITOR_DAYS - 1
    )

    current_date = None

    # 先从 container 的文本节点中寻找日期
    # 并尝试关联后续表格。
    elements = list(
        container.find_all(
            ["div", "ul", "li", "table"]
        )
    )

    for element in elements:
        element_text = element.get_text(
            " ",
            strip=True,
        )

        parsed_date = parse_date_from_text(
            element_text,
            today.year,
        )

        if parsed_date:
            if today <= parsed_date <= end_date:
                current_date = parsed_date

        # 表格才尝试解析场次
        if element.name != "table":
            continue

        if current_date is None:
            continue

        rows = element.find_all("tr")

        for row in rows:
            cells = [
                c.get_text(
                    " ",
                    strip=True,
                )
                for c in row.find_all(
                    ["td", "th"]
                )
            ]

            if not cells:
                continue

            row_text = " ".join(cells)

            # 找时间，例如 09:45 / 22:45
            time_match = re.search(
                r"\b([01]\d|2[0-3]):[0-5]\d\b",
                row_text,
            )

            if not time_match:
                continue

            show_time = time_match.group(0)

            # 尝试找语言版本
            language = ""

            language_candidates = [
                "英语IMAX2D",
                "英语IMAX3D",
                "英语2D",
                "英语3D",
                "国语2D",
                "国语3D",
                "粤语2D",
                "粤语3D",
            ]

            for candidate in language_candidates:
                if candidate in row_text:
                    language = candidate
                    break

            # 尝试找影厅
            hall = ""

            hall_match = re.search(
                r"([^\s|]+厅)",
                row_text,
            )

            if hall_match:
                hall = hall_match.group(1)

            if not hall:
                continue

            key = "|".join(
                [
                    current_date.isoformat(),
                    show_time,
                    hall,
                    language,
                ]
            )

            results.append(
                {
                    "key": key,
                    "date": current_date.isoformat(),
                    "time": show_time,
                    "hall": hall,
                    "language": language,
                }
            )

    # 去重
    unique = {}

    for item in results:
        unique[item["key"]] = item

    results = list(unique.values())

    if not results:
        raise RuntimeError(
            "Maoyan page contains the movie and schedule "
            "headers, but no actual showtimes could be parsed. "
            "The page structure may have changed."
        )

    return sorted(
        results,
        key=lambda x: (
            x["date"],
            x["time"],
            x["hall"],
        ),
    )


def get_bark_key():
    bark_key = os.environ.get("BARK_KEY")

    if not bark_key:
        raise RuntimeError(
            "BARK_KEY is not configured."
        )

    return bark_key


def send_bark(new_showtimes):
    bark_key = get_bark_key()

    title = f"🎬《{MOVIE_NAME}》新增场次"

    lines = [
        f"影院：{CINEMA_NAME}",
        "",
    ]

    for show in sorted(
        new_showtimes,
        key=lambda x: (
            x["date"],
            x["time"],
        ),
    ):
        lines.append(
            f"{show['date']}  "
            f"{show['time']}  "
            f"{show['language']}  "
            f"{show['hall']}"
        )

    body = "\n".join(lines)

    url = f"https://api.day.app/{bark_key}"

    response = requests.get(
        url,
        params={
            "title": title,
            "body": body,
            "group": "奥德赛监控",
            "level": "active",
            "sound": "alarm",
        },
        timeout=15,
    )

    response.raise_for_status()

    print(
        "Bark notification sent successfully."
    )

    print(
        f"Bark response: {response.text}"
    )


def send_bark_test():
    bark_key = get_bark_key()

    url = f"https://api.day.app/{bark_key}"

    response = requests.get(
        url,
        params={
            "title": "🧪《奥德赛》监控测试",
            "body": (
                "GitHub Actions → Bark → iPhone\n"
                "推送链路正常。"
            ),
            "group": "奥德赛监控",
            "level": "active",
            "sound": "alarm",
        },
        timeout=15,
    )

    response.raise_for_status()

    print(
        "Bark TEST notification sent successfully."
    )

    print(
        f"Bark response: {response.text}"
    )


def main():
    test_bark = (
        os.environ.get("TEST_BARK", "").lower()
        == "true"
    )

    if test_bark:
        print("========================================")
        print("BARK TEST MODE")
        print("========================================")

        send_bark_test()

        return

    print("========================================")
    print("NORMAL MONITOR MODE")
    print("========================================")

    old_state = load_state()

    old_keys = set(
        old_state.get("showtimes", [])
    )

    print(
        f"Previously known showtimes: "
        f"{len(old_keys)}"
    )

    # ---------------------------------------------
    # 抓猫眼网页
    # ---------------------------------------------

    html = fetch_page()

    current = parse_showtimes(html)

    current_keys = {
        x["key"]
        for x in current
    }

    print("----------------------------------------")
    print(
        f"Successfully parsed "
        f"{len(current_keys)} showtimes."
    )

    # 输出未来10天的统计
    today = datetime.now().date()

    for i in range(MONITOR_DAYS):
        date = today + timedelta(days=i)

        date_str = date.isoformat()

        count = sum(
            1
            for x in current
            if x["date"] == date_str
        )

        print(
            f"{date_str}: "
            f"{count} showtimes"
        )

    # ---------------------------------------------
    # 第一次成功抓到真实数据
    # ---------------------------------------------

    if not old_state.get("showtimes"):
        save_state(current_keys)

        print(
            "Initial baseline created "
            "from successfully parsed Maoyan data."
        )

        return

    # ---------------------------------------------
    # 找新增场次
    # ---------------------------------------------

    new_keys = current_keys - old_keys

    if new_keys:
        new_showtimes = [
            x
            for x in current
            if x["key"] in new_keys
        ]

        print(
            f"NEW SHOWTIMES FOUND: "
            f"{len(new_showtimes)}"
        )

        for show in new_showtimes:
            print(
                f"NEW: "
                f"{show['date']} "
                f"{show['time']} "
                f"{show['language']} "
                f"{show['hall']}"
            )

        send_bark(new_showtimes)

    else:
        print("No new showtimes.")

    save_state(current_keys)

    print(
        "State saved successfully."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(
            f"ERROR: {e}"
        )

        sys.exit(1)
