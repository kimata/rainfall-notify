#!/usr/bin/env python3
"""
雨雲レーダー画像を生成します．

Usage:
  rain_cloud_panel.py [-c CONFIG]

Options:
  -c CONFIG    : CONFIG を設定ファイルとして読み込んで実行します．[default: config.yaml]
"""

import datetime
import logging
import pathlib
import time

import my_lib.footprint
import my_lib.notify.line
import my_lib.voice
import my_lib.weather
import pytz
from my_lib.sensor_data import get_last_event

TIMEZONE = pytz.timezone("Asia/Tokyo")


def check_raining(config):
    raining_start = get_last_event(
        config["influxdb"],
        config["rain_fall"]["sensor"]["type"],
        config["rain_fall"]["sensor"]["name"],
        "raining",
    )

    return raining_start.astimezone(TIMEZONE)


def get_cloud_url(config):
    # MEMO: 10分遡って5分単位に丸める
    now = datetime.datetime.fromtimestamp(
        ((time.time() - 60 * 10) // (60 * 5)) * (60 * 5), tz=datetime.datetime.now().astimezone().tzinfo
    )

    url = now.strftime(config["rain_cloud"]["img"]["url_tmpl"]).format(now.minute // 5 * 5)

    logging.info("Cloud URL: %s", url)

    return url


def notify_line(config):
    logging.info("Notify by LINE")

    rainfall_info = {
        "cloud_url": config["rain_cloud"]["view"]["url"],
        "cloud_image": get_cloud_url(config),
    }

    message = {
        "type": "template",
        "altText": "雨が降り始めました！",
        "template": {
            "type": "buttons",
            "thumbnailImageUrl": rainfall_info["cloud_image"],
            "imageAspectRatio": "rectangle",
            "imageSize": "cover",
            "imageBackgroundColor": "#FFFFFF",
            "title": "天気速報",
            "text": "雨が降り始めました！",
            "defaultAction": {"type": "uri", "label": "雨雲を見る", "uri": rainfall_info["cloud_url"]},
            "actions": [
                {"type": "uri", "label": "雨雲を見る", "uri": rainfall_info["cloud_url"]},
            ],
        },
    }

    my_lib.notify.line.send(config["notify"]["line"], message)


def check_forecast(config, hour, period_hours=3):
    weather_data = my_lib.weather.get_precip_by_hour_tenki(config["rain_fall"]["forecast"]["tenki"])

    precip_list = [
        hour_data["precip"]
        for day in [weather_data["today"], weather_data["tommorow"]]
        for hour_data in day["data"]
    ]

    return sum(precip_list[hour : hour + period_hours])


def notify_voice(config):
    PERIOD_HOURS = 3

    hour = datetime.datetime.now().hour
    if (hour < config["notify"]["voice"]["hour"]["start"]) or (
        hour > config["notify"]["voice"]["hour"]["end"]
    ):
        # NOTE: 指定された時間内ではなかったら音声通知しない
        logging.info("Skipping notify by voice (out of hour)")
        return

    precip_sum = check_forecast(config, hour, PERIOD_HOURS)
    if precip_sum < 1:
        logging.info("Skipping notify by voice (small rainfall)")
        return

    logging.info("Notify by voice")

    message = f"雨が降り始めました。今後{PERIOD_HOURS}時間で{precip_sum}mm降る見込みです。"

    wav = my_lib.voice.synthesize(config, message)


def watch(config):
    raining_start = check_raining(config)
    raining_before = (datetime.datetime.now(TIMEZONE) - raining_start).total_seconds()

    if raining_before >= my_lib.footprint.elapsed(pathlib.Path(config["notify"]["footprint"]["file"])):
        # NOTE: 既に通知している場合
        return False
    elif my_lib.footprint.elapsed(pathlib.Path(config["notify"]["footprint"]["file"])) < (60 * 60):
        # NOTE: 1時間位内に通知している場合は，連続した雨とみなす
        my_lib.footprint.update(pathlib.Path(config["notify"]["footprint"]["file"]))
        return False

    logging.info(
        "Raining started at %s (%s sec before)",
        raining_start.strftime("%Y/%m/%d %H:%M"),
        f"{raining_before:,.0f}",
    )
    my_lib.footprint.update(pathlib.Path(config["notify"]["footprint"]["file"]))

    if raining_before > (30 * 60):
        logging.warning("Since this is likely the initial check, skipping notification.")
        return False

    notify_line(config)
    notify_voice(config)

    return True


if __name__ == "__main__":
    import docopt
    import my_lib.config
    import my_lib.logger

    args = docopt.docopt(__doc__)

    my_lib.logger.init("test", level=logging.INFO)

    config = my_lib.config.load(args["-c"])

    watch(config)

    logging.info("Finish.")
