#!/usr/bin/env python3
"""
降雨の開始を監視します．

Usage:
  monitor.py [-c CONFIG]

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
import zoneinfo
from my_lib.sensor_data import get_last_event, get_sum

ZONEINFO = zoneinfo.ZoneInfo("Asia/Tokyo")
PERIOD_HOURS = 3  # NOTE: Yahoo天気のデータは3時間毎の降雨量なのでそれに合わせる
SUM_MIN = 3


def check_raining(config):
    raining_start = get_last_event(
        config["influxdb"],
        config["rain_fall"]["sensor"]["type"],
        config["rain_fall"]["sensor"]["name"],
        "raining",
    )

    if raining_start is None:
        # NOTE: まだデータがない場合は，一日前に降り始めたことにする
        return datetime.now(ZONEINFO) - datetime.timedelta(days=1)
    else:
        return raining_start.astimezone(ZONEINFO)


def get_raining_sum(config):
    raining_sum = get_sum(
        config["influxdb"],
        config["rain_fall"]["sensor"]["type"],
        config["rain_fall"]["sensor"]["name"],
        "rain",
        f"-{SUM_MIN}m",
        every_min=1,
        window_min=1,
    )

    return raining_sum if raining_sum is not None else 0


def get_cloud_url(config):
    # MEMO: 10分遡って5分単位に丸める
    now = datetime.datetime.fromtimestamp(((time.time() - 60 * 10) // (60 * 5)) * (60 * 5), tz=ZONEINFO)

    url = now.strftime(config["rain_cloud"]["img"]["url_tmpl"]).format(now.minute // 5 * 5)

    logging.info("Cloud URL: %s", url)

    return url


def notify_line_impl(config, precip_sum):
    logging.info("Notify by LINE")

    message = {
        "type": "template",
        "altText": "雨が降り始めました！",
        "template": {
            "type": "buttons",
            "thumbnailImageUrl": get_cloud_url(config),
            "imageAspectRatio": "rectangle",
            "imageSize": "cover",
            "imageBackgroundColor": "#FFFFFF",
            "title": "天気速報",
            "text": f"雨が降り始めました。\n今後{PERIOD_HOURS}時間で{precip_sum:.1f}mm降る見込みです。",
            "defaultAction": {
                "type": "uri",
                "label": "雨雲を見る",
                "uri": config["rain_cloud"]["view"]["url"],
            },
            "actions": [
                {"type": "uri", "label": "天気予報", "uri": config["weather"]["forecast"]["yahoo"]["url"]},
                {"type": "uri", "label": "雨雲", "uri": config["rain_cloud"]["view"]["url"]},
            ],
        },
    }

    my_lib.notify.line.send(config["notify"]["line"], message)

    return True


def check_forecast(config, hour):
    weather_info = my_lib.weather.get_weather_yahoo(config["weather"]["forecast"]["yahoo"])
    weather_data = weather_info["today"]["data"] + weather_info["tomorrow"]["data"]

    precip_list = [hour_data["precip"] for hour_data in weather_data]

    # NOTE: 3時間毎のデータなので線形補完する
    lower = hour // PERIOD_HOURS
    upper = lower + 1

    weight_upper = (hour - lower * PERIOD_HOURS) / PERIOD_HOURS
    weight_lower = 1 - weight_upper

    return precip_list[lower] * weight_lower + precip_list[upper] * weight_upper


def notify_voice_impl(config, raining_sum, precip_sum, hour):
    if (raining_sum < 0.1) and (precip_sum < 0.1):
        logging.info(
            "Skipping notify by voice (small rainfall, sum: %.2fmm,  forecast: %.1fmm)",
            raining_sum,
            precip_sum,
        )
        return False

    if (hour < config["notify"]["voice"]["hour"]["start"]) or (
        hour > config["notify"]["voice"]["hour"]["end"]
    ):
        # NOTE: 指定された時間内ではなかったら音声通知しない
        logging.info("Skipping notify by voice (out of hour: %d)", hour)
        return False

    logging.info("Notify by voice")

    message = "雨が降り始めました。"
    if raining_sum >= 0.1:
        message += f"過去{SUM_MIN}分間に{raining_sum:.1f}mm降っています。"
    if precip_sum >= 0.1:
        message += f"今後{PERIOD_HOURS}時間で{precip_sum:.1f}mm降る見込みです。"

    message_wav = my_lib.voice.synthesize(config, message)

    with pathlib.Path(config["notify"]["voice"]["chime"]["file"]).open("rb") as file:
        my_lib.voice.play(
            my_lib.voice.convert_wav_data(file.read()), config["notify"]["voice"]["chime"]["duration"]
        )

    my_lib.voice.play(message_wav)

    return True


def is_notify_done(config, raining_before, mode):
    if raining_before >= my_lib.footprint.elapsed(pathlib.Path(config["notify"]["footprint"][mode]["file"])):
        # NOTE: 既に通知している場合
        return True
    elif my_lib.footprint.elapsed(pathlib.Path(config["notify"]["footprint"][mode]["file"])) < (30 * 60):
        # NOTE: 30分内に通知している場合は，連続した雨とみなす
        my_lib.footprint.update(pathlib.Path(config["notify"]["footprint"][mode]["file"]))
        return True

    if raining_before > (30 * 60):
        logging.warning("Since this is likely the initial check, skipping notification.")
        return True

    return False


def notify_line(config, raining_start, raining_before, precip_sum):
    if is_notify_done(config, raining_before, "line"):
        return False

    logging.info(
        "Raining started at %s (%s sec before)",
        raining_start.strftime("%Y/%m/%d %H:%M"),
        f"{raining_before:,.0f}",
    )

    notify_line_impl(config, precip_sum)

    my_lib.footprint.update(pathlib.Path(config["notify"]["footprint"]["line"]["file"]))


def notify_voice(config, raining_start, raining_before, raining_sum, precip_sum, hour):
    if is_notify_done(config, raining_before, "voice"):
        return False

    if notify_voice_impl(config, raining_sum, precip_sum, hour):
        my_lib.footprint.update(pathlib.Path(config["notify"]["footprint"]["voice"]["file"]))
        return True

    return False


def watch(config):
    raining_start = check_raining(config)
    raining_before = (datetime.datetime.now(ZONEINFO) - raining_start).total_seconds()

    hour = datetime.datetime.now(ZONEINFO).hour
    raining_sum = get_raining_sum(config)
    precip_sum = check_forecast(config, hour)

    logging.debug("raining_sum: %.2f, precip_sum: %.2f", raining_sum, precip_sum)

    notify_line(config, raining_start, raining_before, precip_sum)
    notify_voice(config, raining_start, raining_before, raining_sum, precip_sum, hour)

    return True


if __name__ == "__main__":
    import docopt
    import my_lib.config
    import my_lib.logger

    args = docopt.docopt(__doc__)

    my_lib.logger.init("test", level=logging.DEBUG)

    config = my_lib.config.load(args["-c"])

    watch(config)

    logging.info("Finish.")
