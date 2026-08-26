import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests


CINEMA_ID = 37534
MOVIE_ID = 1545360

CINEMA_NAME = "MOViE MOViE 前滩太古里"
MOVIE_NAME = "奥德赛"

# ==============================
# 只需要修改这一行，就可以换监控日期
# ==============================
TARGET_DATE = "2026-08-31"

STATE_FILE = Path("state.json")

# 猫眼 H5 API
MAOYAN_API_URL = "https://m.maoyan.com/ajax/cinemaDetail"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://m.maoyan.com/",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
}


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(target_date, showtimes):
    data = {
        "updated_at": datetime.now().isoformat(),
        "target_date": target_date,
        "showtimes": sorted(showtimes),
    }

    STATE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def request_maoyan(params):
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

    print(f"HTTP status: {response.status_code}")
    print(f"Response length: {len(response.text)} bytes")

    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    print(f"Content-Type: {content_type}")

    print("Response preview:")
    print(response.text[:1000])

    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(
            "Maoyan API did not return valid JSON. "
            f"Response starts with: {response.text[:500]}"
        ) from e

    if not isinstance(data, dict):
        raise RuntimeError("Maoyan API JSON root is not an object.")

    return data


def recursive_find_movie_objects(obj):
    found = []

    if isinstance(obj, dict):
        keys_lower = {str(k).lower() for k in obj.keys()}

        movie_like = (
            "movieid" in keys_lower
            or "movie_id" in keys_lower
            or "showtimes" in keys_lower
            or "shows" in keys_lower
        )

        if movie_like:
            found.append(obj)

        for value in obj.values():
            found.extend(recursive_find_movie_objects(value))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(recursive_find_movie_objects(item))

    return found


def object_movie_id(obj):
    for key in ("movieId", "movie_id", "movieID", "id"):
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
    objects = recursive_find_movie_objects(data)

    print(f"Potential movie objects found: {len(objects)}")

    by_id = [
        obj for obj in objects
        if object_movie_id(obj) == MOVIE_ID
    ]

    if by_id:
        print(f"Found target movie by MOVIE_ID: {MOVIE_ID}")
        return by_id

    by_name = [
        obj for obj in objects
        if MOVIE_NAME in object_movie_name(obj)
    ]

    if by_name:
        print(f"Found target movie by name: {MOVIE_NAME}")
        return by_name

    return []


def get_value(obj, keys):
    for key in keys:
        if key in obj:
            return obj[key]

    return None


def normalize_time(value):
    if value is None:
        return None

    text = str(value).strip()

    match = re.search(
        r"\b([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\b",
        text,
    )

    if match:
        return f"{match.group(1)}:{match.group(2)}"

    return None


def normalize_date(value, default_date):
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
        match = re.search(pattern, text)
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

            return datetime(year, month, day).date()

        except ValueError:
            pass

    return default_date


def parse_showtime_object(show, request_date):
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

    show_time = normalize_time(time_value)

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

    show_date = normalize_date(date_value, request_date)

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

    hall = "" if hall is None else str(hall).strip()

    language = get_value(
        show,
        [
            "lang",
            "language",
            "languageName",
            "language_name",
        ],
    )

    language = "" if language is None else str(language).strip()

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
            language = f"{language}{version}" if language else version

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


def parse_api_showtimes(data, request_date):
    movie_objects = find_target_movie_objects(data)

    if not movie_objects:
        raise RuntimeError(
            f"Movie '{MOVIE_NAME}' (movieId={MOVIE_ID}) "
            "was not found in Maoyan API response."
        )

    results = []

    for movie in movie_objects:
        shows = movie.get("shows", [])

        print(f"Movie has {len(shows)} show groups.")

        for show_group in shows:
            plist = show_group.get("plist", [])

            print(f"  plist entries: {len(plist)}")

            for show in plist:
                if not isinstance(show, dict):
                    continue

                parsed = parse_showtime_object(show, request_date)

                if parsed:
                    results.append(parsed)

    unique = {item["key"]: item for item in results}

    return sorted(
        unique.values(),
        key=lambda x: (x["date"], x["time"], x["hall"]),
    )


def fetch_showtimes_for_date(target_date):
    params = {
        "movieId": MOVIE_ID,
        "cinemaId": CINEMA_ID,
        "date": target_date,
    }

    data = request_maoyan(params)
    request_date = datetime.fromisoformat(target_date).date()
    return parse_api_showtimes(data, request_date)


def get_bark_key():
    bark_key = os.environ.get("BARK_KEY")

    if not bark_key:
        raise RuntimeError("BARK_KEY is not configured.")

    return bark_key


def send_bark(new_showtimes):
    bark_key = get_bark_key()

    title = f"🎬《{MOVIE_NAME}》{TARGET_DATE} 新增场次"

    lines = [
        f"影院：{CINEMA_NAME}",
        f"日期：{TARGET_DATE}",
        "",
    ]

    for show in sorted(new_showtimes, key=lambda x: x["time"]):
        language = show["language"] or "版本未知"
        hall = show["hall"] or "影厅未知"

        lines.append(
            f"{show['time']}  {language}  {hall}"
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

    print("Bark notification sent successfully.")
    print(f"Bark response: {response.text}")


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

    print("Bark TEST notification sent successfully.")
    print(f"Bark response: {response.text}")


def main():
    test_bark = (
        os.environ.get("TEST_BARK", "").lower() == "true"
    )

    if test_bark:
        print("========================================")
        print("BARK TEST MODE")
        print("========================================")
        send_bark_test()
        return

    print("========================================")
    print("TARGET-DATE MONITOR MODE")
    print("========================================")
    print(f"Cinema: {CINEMA_NAME}")
    print(f"Movie: {MOVIE_NAME}")
    print(f"Target date: {TARGET_DATE}")

    old_state = load_state()

    # 如果用户修改了 TARGET_DATE，则自动把新日期视为全新的监控任务。
    if old_state.get("target_date") != TARGET_DATE:
        old_keys = set()
        print("Target date changed. Starting a fresh baseline for this date.")
    else:
        old_keys = set(old_state.get("showtimes", []))

    print(f"Previously known showtimes for target date: {len(old_keys)}")

    current = fetch_showtimes_for_date(TARGET_DATE)

    # API 返回的数据可能包含其他日期；这里严格只保留目标日期。
    current = [
        show for show in current
        if show["date"] == TARGET_DATE
    ]

    current_keys = {show["key"] for show in current}

    print("----------------------------------------")
    print(f"Target date {TARGET_DATE}: {len(current_keys)} showtimes")

    if current:
        for show in current:
            print(
                f"CURRENT: {show['date']} "
                f"{show['time']} "
                f"{show['language']} "
                f"{show['hall']}"
            )
    else:
        print(f"No showtimes released yet for {TARGET_DATE}.")

    # 只比较“这个目标日期”历史上见过的场次。
    # 已经结束的场次不会因为下架而导致整体数量下降，从而干扰判断。
    new_keys = current_keys - old_keys

    if new_keys:
        new_showtimes = [
            show for show in current
            if show["key"] in new_keys
        ]

        print("----------------------------------------")
        print(f"NEW SHOWTIMES FOUND: {len(new_showtimes)}")

        for show in new_showtimes:
            print(
                f"NEW: {show['date']} "
                f"{show['time']} "
                f"{show['language']} "
                f"{show['hall']}"
            )

        send_bark(new_showtimes)

    else:
        print("No new showtimes for target date.")

    # 保存“历史上见过”的场次，而不是只保存当前场次。
    # 这样场次短暂下架后重新出现，也不会重复骚扰。
    seen_keys = old_keys | current_keys

    save_state(TARGET_DATE, seen_keys)

    print(
        f"State saved successfully. "
        f"Known target-date showtimes: {len(seen_keys)}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
