import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests


CINEMA_ID = 37534
MOVIE_ID = 1545360

CINEMA_NAME = "MOViE MOViE 前滩太古里"
MOVIE_NAME = "奥德赛"

STATE_FILE = Path("state.json")

MONITOR_DAYS = 10

# 猫眼 H5 API
MAOYAN_API_URL = "https://m.maoyan.com/ajax/cinemaDetail"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": (
        "application/json, text/plain, */*"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://m.maoyan.com/",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
}


def load_state():
    if not STATE_FILE.exists():
        return {"showtimes": []}

    try:
        return json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {"showtimes": []}


def save_state(showtimes):
    data = {
        "updated_at": datetime.now().isoformat(),
        "showtimes": sorted(showtimes),
    }

    STATE_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def request_maoyan(params):
    """
    请求猫眼 H5 cinemaDetail API。

    第一阶段故意保持请求简单：
    cinemaId + movieId + date。

    如果猫眼接口对参数有不同要求，
    会把 HTTP 状态和响应内容打印出来，
    方便继续调整。
    """

    print("----------------------------------------")
    print("Calling Maoyan H5 API:")
    print(MAOYAN_API_URL)
    print(f"Params: {params}")

    response = requests.get(
        MAOYAN_API_URL,
        params=params,
        headers=HEADERS,
        timeout=30,
    )

    print(
        f"HTTP status: {response.status_code}"
    )

    print(
        f"Response length: "
        f"{len(response.text)} bytes"
    )

    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type",
        "",
    )

    print(
        f"Content-Type: {content_type}"
    )

    # 打印前 1000 个字符。
    # 第一次跑 API 时尤其重要。
    print("Response preview:")
    print(response.text[:1000])

    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(
            "Maoyan API did not return valid JSON. "
            f"Response starts with: "
            f"{response.text[:500]}"
        ) from e

    if not isinstance(data, dict):
        raise RuntimeError(
            "Maoyan API JSON root is not an object."
        )

    return data


def recursive_find_movie_objects(obj):
    """
    在未知 JSON 结构中寻找可能代表电影的 dict。

    不依赖固定的 JSON 路径。
    """

    found = []

    if isinstance(obj, dict):
        keys_lower = {
            str(k).lower()
            for k in obj.keys()
        }

        # 常见电影对象特征
        movie_like = (
            "movieid" in keys_lower
            or "movie_id" in keys_lower
            or "showtimes" in keys_lower
            or "shows" in keys_lower
        )

        if movie_like:
            found.append(obj)

        for value in obj.values():
            found.extend(
                recursive_find_movie_objects(value)
            )

    elif isinstance(obj, list):
        for item in obj:
            found.extend(
                recursive_find_movie_objects(item)
            )

    return found


def object_movie_id(obj):
    for key in (
        "movieId",
        "movie_id",
        "movieID",
        "id",
    ):
        if key in obj:
            value = obj[key]

            try:
                return int(value)
            except Exception:
                pass

    return None


def object_movie_name(obj):
    for key in (
        "movieName",
        "movie_name",
        "movieTitle",
        "movie_title",
        "name",
        "title",
    ):
        if key in obj:
            value = obj[key]

            if isinstance(value, str):
                return value.strip()

    return ""


def find_target_movie_objects(data):
    """
    找到《奥德赛》对应的电影对象。

    优先使用 MOVIE_ID。
    如果 JSON 没有 movieId，再尝试电影名称。
    """

    objects = recursive_find_movie_objects(
        data
    )

    print(
        f"Potential movie objects found: "
        f"{len(objects)}"
    )

    by_id = []

    for obj in objects:
        mid = object_movie_id(obj)

        if mid == MOVIE_ID:
            by_id.append(obj)

    if by_id:
        print(
            f"Found target movie by MOVIE_ID: "
            f"{MOVIE_ID}"
        )

        return by_id

    by_name = []

    for obj in objects:
        name = object_movie_name(obj)

        if MOVIE_NAME in name:
            by_name.append(obj)

    if by_name:
        print(
            f"Found target movie by name: "
            f"{MOVIE_NAME}"
        )

        return by_name

    return []


def recursive_find_showtime_objects(obj):
    """
    猫眼 cinemaDetail 的真实排片结构：

    movie
      └── shows[]
            └── plist[]
                  ├── tm    放映时间
                  ├── dt    日期
                  ├── th    影厅
                  ├── lang  语言
                  └── tp    版本/类型

    因此这里支持猫眼使用的短字段。
    """

    found = []

    if isinstance(obj, dict):

        # 猫眼当前 cinemaDetail API 的场次字段
        has_time = any(
            key in obj
            for key in (
                "tm",
                "showTime",
                "showtime",
                "show_time",
                "startTime",
                "start_time",
                "beginTime",
                "begin_time",
            )
        )

        if has_time:
            found.append(obj)

        for value in obj.values():
            found.extend(
                recursive_find_showtime_objects(
                    value
                )
            )

    elif isinstance(obj, list):

        for item in obj:
            found.extend(
                recursive_find_showtime_objects(
                    item
                )
            )

    return found


def get_value(obj, keys):
    for key in keys:
        if key in obj:
            return obj[key]

    return None


def normalize_time(value):
    """
    猫眼 tm 通常就是：
    10:30
    19:45
    """

    if value is None:
        return None

    text = str(value).strip()

    match = re.search(
        r"\b([01]\d|2[0-3]):([0-5]\d)"
        r"(?::[0-5]\d)?\b",
        text,
    )

    if match:
        return (
            f"{match.group(1)}:"
            f"{match.group(2)}"
        )

    return None


def normalize_date(value, default_date):
    """
    猫眼 dt 可能是：
    2026-08-22
    08-22
    8月22日
    等形式。
    """

    if value is None:
        return default_date

    text = str(value).strip()

    patterns = [
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
        r"(\d{1,2})-(\d{1,2})",
        r"(\d{1,2})月(\d{1,2})日",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
        )

        if not match:
            continue

        try:

            groups = match.groups()

            if len(groups) == 3:

                year = int(groups[0])
                month = int(groups[1])
                day = int(groups[2])

            else:

                year = default_date.year
                month = int(groups[0])
                day = int(groups[1])

            return datetime(
                year,
                month,
                day,
            ).date()

        except ValueError:
            pass

    return default_date


def parse_showtime_object(
    show,
    request_date,
):
    """
    解析猫眼 plist 中的一条场次。

    猫眼字段：
        tm   = 时间
        dt   = 日期
        th   = 影厅
        lang = 语言
        tp   = 版本/类型
    """

    time_value = get_value(
        show,
        [
            "tm",
            "showTime",
            "showtime",
            "show_time",
            "startTime",
            "start_time",
            "beginTime",
            "begin_time",
        ],
    )

    show_time = normalize_time(
        time_value
    )

    if not show_time:
        return None

    date_value = get_value(
        show,
        [
            "dt",
            "showDate",
            "show_date",
            "date",
            "showDay",
            "show_day",
        ],
    )

    show_date = normalize_date(
        date_value,
        request_date,
    )

    hall = get_value(
        show,
        [
            "th",
            "hallName",
            "hall_name",
            "hall",
            "roomName",
            "room_name",
        ],
    )

    if hall is None:
        hall = ""

    hall = str(hall).strip()

    language = get_value(
        show,
        [
            "lang",
            "language",
            "languageName",
            "language_name",
        ],
    )

    if language is None:
        language = ""

    language = str(language).strip()

    version = get_value(
        show,
        [
            "tp",
            "showVersion",
            "show_version",
            "version",
            "versionName",
            "version_name",
        ],
    )

    if version is not None:
        version = str(version).strip()

        if version and version not in language:
            if language:
                language = (
                    f"{language}{version}"
                )
            else:
                language = version

    key = "|".join(
        [
            show_date.isoformat(),
            show_time,
            hall,
            language,
        ]
    )

    return {
        "key": key,
        "date": show_date.isoformat(),
        "time": show_time,
        "hall": hall,
        "language": language,
    }


def parse_api_showtimes(
    data,
    request_date,
):
    """
    从猫眼 cinemaDetail JSON 中解析
    目标电影的 plist 排片。
    """

    movie_objects = find_target_movie_objects(
        data
    )

    if not movie_objects:

        raise RuntimeError(
            f"Movie '{MOVIE_NAME}' "
            f"(movieId={MOVIE_ID}) "
            "was not found in Maoyan API response."
        )

    results = []

    for movie in movie_objects:

        # 猫眼真实结构：
        #
        # movie
        #   └── shows
        #         └── plist
        #
        shows = movie.get(
            "shows",
            []
        )

        print(
            f"Movie has "
            f"{len(shows)} show groups."
        )

        for show_group in shows:

            plist = show_group.get(
                "plist",
                []
            )

            print(
                f"  plist entries: "
                f"{len(plist)}"
            )

            for show in plist:

                if not isinstance(
                    show,
                    dict,
                ):
                    continue

                parsed = parse_showtime_object(
                    show,
                    request_date,
                )

                if parsed:
                    results.append(
                        parsed
                    )

    unique = {}

    for item in results:
        unique[item["key"]] = item

    results = list(
        unique.values()
    )

    return sorted(
        results,
        key=lambda x: (
            x["date"],
            x["time"],
            x["hall"],
        ),
    )


def fetch_showtimes_for_date(
    target_date
):
    """
    当前猫眼 cinemaDetail 实际上会返回
    影院/电影的完整排片结构。

    因此 date 参数继续传入，但解析时
    以返回数据中的 dt 为准。
    """

    params = {
        "movieId": MOVIE_ID,
        "cinemaId": CINEMA_ID,
        "date": target_date.isoformat(),
    }

    data = request_maoyan(
        params
    )

    results = parse_api_showtimes(
        data,
        target_date,
    )

    return results


def fetch_all_showtimes():
    """
    查询未来 MONITOR_DAYS 天。

    逐日请求，避免 API 一次只返回当天数据。
    """

    today = datetime.now().date()

    end_date = (
        today
        + timedelta(
            days=MONITOR_DAYS - 1
        )
    )

    all_results = []

    print("========================================")
    print("MAOYAN API MONITOR")
    print("========================================")
    print(
        f"Cinema: {CINEMA_NAME}"
    )
    print(
        f"Cinema ID: {CINEMA_ID}"
    )
    print(
        f"Movie: {MOVIE_NAME}"
    )
    print(
        f"Movie ID: {MOVIE_ID}"
    )
    print(
        f"Date range: "
        f"{today} -> {end_date}"
    )

    for i in range(
        MONITOR_DAYS
    ):

        target_date = (
            today
            + timedelta(days=i)
        )

        print()
        print(
            "========================================"
        )
        print(
            f"Checking date: "
            f"{target_date}"
        )
        print(
            "========================================"
        )

        try:

            results = fetch_showtimes_for_date(
                target_date
            )

            print(
                f"Parsed "
                f"{len(results)} "
                f"showtimes for "
                f"{target_date}"
            )

            all_results.extend(
                results
            )

        except Exception as e:

            print(
                f"WARNING: Failed to fetch "
                f"{target_date}: {e}"
            )

            # 第一天失败时不要静默当成没有排片。
            # 直接抛错，方便判断猫眼接口是否风控。
            if i == 0:
                raise

    unique = {}

    for item in all_results:
        unique[item["key"]] = item

    return sorted(
        unique.values(),
        key=lambda x: (
            x["date"],
            x["time"],
            x["hall"],
        ),
    )


def get_bark_key():
    bark_key = os.environ.get(
        "BARK_KEY"
    )

    if not bark_key:
        raise RuntimeError(
            "BARK_KEY is not configured."
        )

    return bark_key


def send_bark(new_showtimes):
    bark_key = get_bark_key()

    title = (
        f"🎬《{MOVIE_NAME}》新增场次"
    )

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

        language = (
            show["language"]
            or "版本未知"
        )

        hall = (
            show["hall"]
            or "影厅未知"
        )

        lines.append(
            f"{show['date']}  "
            f"{show['time']}  "
            f"{language}  "
            f"{hall}"
        )

    body = "\n".join(
        lines
    )

    url = (
        f"https://api.day.app/"
        f"{bark_key}"
    )

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
        f"Bark response: "
        f"{response.text}"
    )


def send_bark_test():
    bark_key = get_bark_key()

    url = (
        f"https://api.day.app/"
        f"{bark_key}"
    )

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
        f"Bark response: "
        f"{response.text}"
    )


def main():

    test_bark = (
        os.environ.get(
            "TEST_BARK",
            ""
        ).lower()
        == "true"
    )

    if test_bark:

        print(
            "========================================"
        )
        print(
            "BARK TEST MODE"
        )
        print(
            "========================================"
        )

        send_bark_test()

        return

    print(
        "========================================"
    )
    print(
        "NORMAL MONITOR MODE"
    )
    print(
        "========================================"
    )

    old_state = load_state()

    old_keys = set(
        old_state.get(
            "showtimes",
            []
        )
    )

    print(
        f"Previously known showtimes: "
        f"{len(old_keys)}"
    )

    # -----------------------------------------
    # 使用猫眼 API 获取排片
    # -----------------------------------------

    current = fetch_all_showtimes()

    current_keys = {
        x["key"]
        for x in current
    }

    print(
        "----------------------------------------"
    )

    print(
        f"Successfully parsed "
        f"{len(current_keys)} "
        f"showtimes."
    )

    # -----------------------------------------
    # 输出未来10天统计
    # -----------------------------------------

    today = datetime.now().date()

    for i in range(
        MONITOR_DAYS
    ):

        date = (
            today
            + timedelta(days=i)
        )

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

    # -----------------------------------------
    # 第一次成功抓到真实数据
    # -----------------------------------------

    if not old_state.get(
        "showtimes"
    ):

        save_state(
            current_keys
        )

        print(
            "Initial baseline created "
            "from successfully parsed "
            "Maoyan API data."
        )

        return

    # -----------------------------------------
    # 找新增场次
    # -----------------------------------------

    new_keys = (
        current_keys
        - old_keys
    )

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

        send_bark(
            new_showtimes
        )

    else:

        print(
            "No new showtimes."
        )

    save_state(
        current_keys
    )

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
