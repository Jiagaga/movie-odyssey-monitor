import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests

CINEMA_ID = 37534
MOVIE_ID = 1545360

CINEMA_NAME = "MOViE MOViE 前滩太古里"
MOVIE_NAME = "奥德赛"

API_URL = "https://m.maoyan.com/ajax/cinemaDetail"

STATE_FILE = Path("state.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Referer": "https://m.maoyan.com/",
    "Accept": "application/json, text/plain, */*",
}

def load_state():
    if not STATE_FILE.exists():
        return {"showtimes": []}

    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
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

def fetch_showtimes(date):
    params = {
        "movieId": MOVIE_ID,
        "cinemaId": CINEMA_ID,
        "date": date,
        "optimus_uuid": uuid.uuid4().hex,
        "optimus_risk_level": 71,
        "optimus_code": 10,
    }

    response = requests.get(
        API_URL,
        params=params,
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()
    data = response.json()

    results = []

    for show_date in data.get("showDates", []):
        actual_date = show_date.get("date") or date

        for show in show_date.get("plist", []):
            time = show.get("tm")
            hall = show.get("th")
            language = show.get("lang")
            price = show.get("sellPr")

            if not time or not hall:
                continue

            key = "|".join(
                str(x)
                for x in [
                    actual_date,
                    time,
                    hall,
                    language or "",
                ]
            )

            results.append(
                {
                    "key": key,
                    "date": actual_date,
                    "time": time,
                    "hall": hall,
                    "language": language or "",
                    "price": price,
                    "seat_status": show.get("seatStatus"),
                }
            )

    return results

def fetch_all():
    """
    猫眼通常会在 cinemaDetail 返回未来若干天的排片。
    为了避免频繁请求，只请求今天一次。
    """

    today = datetime.now().strftime("%Y-%m-%d")

    return fetch_showtimes(today)

def send_bark(new_showtimes):
    bark_key = os.environ.get("BARK_KEY")

    if not bark_key:
        print("BARK_KEY is not configured.")
        return False

    title = f"🎬《{MOVIE_NAME}》新增场次"

    lines = [
        f"影院：{CINEMA_NAME}",
        "",
    ]

    for show in sorted(new_showtimes, key=lambda x: (x["date"], x["time"])):
        lines.append(
            f"{show['date']}  {show['time']}  "
            f"{show['language']}  {show['hall']}"
        )

    body = "\n".join(lines)

    url = f"https://api.day.app/{bark_key}/"

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

    print("Bark notification sent.")
    return True

def main():
    old_state = load_state()
    old_keys = set(old_state.get("showtimes", []))

    print("Checking Maoyan...")

    current = fetch_all()
    current_keys = {x["key"] for x in current}

    print(f"Current showtimes: {len(current)}")
    print(f"Previously known: {len(old_keys)}")

    # 第一次运行：建立基准，不发送通知
    if not old_state.get("showtimes"):
        save_state(current_keys)
        print("Initial baseline created. No notification sent.")
        return

    new_keys = current_keys - old_keys

    if new_keys:
        new_showtimes = [
            x for x in current
            if x["key"] in new_keys
        ]

        print(f"NEW SHOWTIMES FOUND: {len(new_showtimes)}")

        for show in new_showtimes:
            print(
                show["date"],
                show["time"],
                show["hall"],
                show["language"],
            )

        send_bark(new_showtimes)
    else:
        print("No new showtimes.")

    save_state(current_keys)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
