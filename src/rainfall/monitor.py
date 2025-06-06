#!/usr/bin/env python3
"""
降雨の開始を監視します。

Usage:
  monitor.py [-c CONFIG] [-d] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -d                : ダミーモードで実行します。CI テストで利用することを想定しています。
  -D                : デバッグモードで動作します。
"""

import datetime
import logging
import pathlib
import time

import my_lib.footprint
import my_lib.notify.line
import my_lib.sensor_data
import my_lib.time
import my_lib.voice
import my_lib.weather
import psutil

PERIOD_HOURS = 3  # NOTE: Yahoo天気のデータは3時間毎の降雨量なのでそれに合わせる
SUM_MIN = 3  # NOTE: 直近の雨量を積算する期間[分]
SOLAR_RAD_THRESHOLD = 600  # 日射量がこれよりある場合は、雨の降り始め扱いにしない


def get_solar_rad(config, raining_start):
    start = (raining_start - datetime.timedelta(minutes=10)).isoformat()
    stop = (raining_start + datetime.timedelta(minutes=1)).isoformat()

    solar_rad_info = my_lib.sensor_data.fetch_data(
        config["influxdb"],
        config["sensor"]["rain_fall"]["measure"],
        config["sensor"]["rain_fall"]["hostname"],
        "solar_rad",
        start=start,
        stop=stop,
        last=True,
    )

    return solar_rad_info["value"][0] if solar_rad_info["valid"] else None


def check_raining(config):
    raining_start = my_lib.sensor_data.get_last_event(
        config["influxdb"],
        config["sensor"]["rain_fall"]["measure"],
        config["sensor"]["rain_fall"]["hostname"],
        "raining",
    )

    if raining_start is None:
        # NOTE: まだデータがない場合は、一年前に降り始めたことにする
        return my_lib.time.now() - datetime.timedelta(days=365)

    return raining_start.astimezone(my_lib.time.get_zoneinfo())


def get_raining_sum(config):
    raining_sum = my_lib.sensor_data.get_minute_sum(
        config["influxdb"],
        config["sensor"]["rain_fall"]["measure"],
        config["sensor"]["rain_fall"]["hostname"],
        "rain",
        SUM_MIN,
    )

    return raining_sum if raining_sum is not None else 0


def get_cloud_url(config):
    # MEMO: 10分遡って5分単位に丸める
    now = datetime.datetime.fromtimestamp(
        ((time.time() - 60 * 10) // (60 * 5)) * (60 * 5), tz=my_lib.time.get_zoneinfo()
    )

    url = now.strftime(config["rain_cloud"]["img"]["url_tmpl"]).format(now.minute // 5 * 5)

    logging.info("Cloud URL: %s", url)

    return url


def notify_line_impl(config, precip_sum):
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


def notify_voice_impl(config, raining_sum, precip_sum):
    message = "雨が降り始めました。"
    if raining_sum >= 0.1:
        message += f"過去{SUM_MIN}分間に{raining_sum:.1f}mm降っています。"
    if precip_sum >= 0.1:
        message += f"今後{PERIOD_HOURS}時間で{precip_sum:.1f}mm降る見込みです。"

    message_wav = my_lib.voice.synthesize(config, message)

    if "chime" in config["notify"]["voice"]:
        with pathlib.Path(config["notify"]["voice"]["chime"]["file"]).open("rb") as file:
            my_lib.voice.play(
                my_lib.voice.convert_wav_data(file.read()), config["notify"]["voice"]["chime"]["duration"]
            )

    my_lib.voice.play(message_wav)

    return True


def get_process_start():
    return datetime.datetime.fromtimestamp(psutil.Process().create_time(), tz=my_lib.time.get_zoneinfo())


def is_notify_done(config, raining_start, mode):
    process_start = get_process_start()

    if (raining_start - process_start).total_seconds() < -60 * 10:
        # NONE 雨の降り始めがプログラム開始前の場合、通知をしない
        logging.debug("Since this is likely the initial check, skipping notification.")
        return True

    raining_before = (my_lib.time.now() - raining_start).total_seconds()

    if raining_before >= my_lib.footprint.elapsed(config["notify"]["footprint"][mode]["file"]):
        # NOTE: 既に通知している場合
        return True
    if my_lib.footprint.elapsed(config["notify"]["footprint"][mode]["file"]) < (30 * 60):
        # NOTE: 30分内に通知している場合は、連続した雨とみなす
        logging.info("Recent notification sent. Treated as continuous rain. Skipping.")
        my_lib.footprint.update(config["notify"]["footprint"][mode]["file"])
        return True

    solar_rad = get_solar_rad(config, raining_start)
    if (solar_rad is not None) and (solar_rad >= SOLAR_RAD_THRESHOLD):
        logging.warning("Rain detected by sensor, but ignored due to high solar radiation.")
        # NOTE: 雨の降り始め時点で日射量が多い場合、光学式雨量計の誤検知の可能性が高いので、
        # 無視する (狐の嫁入りの可能性もありますが...)
        my_lib.footprint.update(config["notify"]["footprint"][mode]["file"])
        return True

    return False


def notify_line(config, raining_start, precip_sum):
    logging.info("Notify by LINE")
    logging.info("Raining started at %s", raining_start.strftime("%Y/%m/%d %H:%M"))

    notify_line_impl(config, precip_sum)

    my_lib.footprint.update(pathlib.Path(config["notify"]["footprint"]["line"]["file"]))


def notify_voice(config, raining_start, raining_sum, precip_sum):
    logging.info("Notify by LINE")
    if notify_voice_impl(config, raining_sum, precip_sum):
        my_lib.footprint.update(pathlib.Path(config["notify"]["footprint"]["voice"]["file"]))
        return True

    return False


def should_notify_line(config, raining_start):
    if is_notify_done(config, raining_start, "line"):
        return False

    return True


def should_notify_voice(config, raining_start, raining_sum, precip_sum, hour):
    if is_notify_done(config, raining_start, "voice"):
        return False

    if (raining_sum < 0.1) and (precip_sum < 0.1):
        logging.info(
            "Skipping notify by voice (small rainfall, sum: %.2fmm, forecast: %.1fmm)",
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

    return True


def watch(config, dummy_mode=False):
    raining_start = check_raining(config)

    hour = my_lib.time.now().hour
    raining_sum = get_raining_sum(config)
    precip_sum = check_forecast(config, hour)

    logging.debug("raining_sum: %.2f, precip_sum: %.2f", raining_sum, precip_sum)

    if dummy_mode:
        return

    if should_notify_line(config, raining_start):
        notify_line(config, raining_start, precip_sum)
    if should_notify_voice(config, raining_start, raining_sum, precip_sum, hour):
        notify_voice(config, raining_start, raining_sum, precip_sum)


if __name__ == "__main__":
    # TEST Code
    import docopt
    import my_lib.config
    import my_lib.logger

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    dummy_mode = args["-d"]
    debug_mode = args["-D"]

    my_lib.logger.init("test", level=logging.DEBUG if debug_mode else logging.INFO)

    config = my_lib.config.load(config_file)

    watch(config, dummy_mode)

    logging.info("Finish.")
