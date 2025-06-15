#!/usr/bin/env python3
# ruff: noqa: S101
import datetime
import logging
import pathlib
from unittest import mock

import app
import my_lib.sensor
import pytest

CONFIG_FILE = "config.example.yaml"
SCHEMA_CONFIG = "config.schema"


@pytest.fixture(scope="session", autouse=True)
def env_mock():
    with mock.patch.dict(
        "os.environ",
        {
            "TEST": "true",
            "NO_COLORED_LOGS": "true",
        },
    ) as fixture:
        yield fixture


@pytest.fixture(scope="session", autouse=True)
def line_mock():
    with mock.patch(
        "linebot.v3.messaging.MessagingApi",
        return_value=True,
    ) as fixture:
        yield fixture


@pytest.fixture(scope="session", autouse=True)
def voice_play_mock():
    with mock.patch.multiple(
        "my_lib",
        voice=mock.Mock(play=mock.Mock(return_value=True)),
        synthesize=mock.Mock(return_value=True),
    ) as fixture:
        yield fixture


@pytest.fixture(scope="session")
def config():
    import my_lib.config

    return my_lib.config.load(CONFIG_FILE, pathlib.Path(SCHEMA_CONFIG))


@pytest.fixture(autouse=True)
def _clear(config):
    import my_lib.footprint
    import my_lib.notify.slack

    my_lib.footprint.clear(config["liveness"]["file"]["watch"])
    my_lib.footprint.clear(config["notify"]["footprint"]["line"]["file"])
    my_lib.footprint.clear(config["notify"]["footprint"]["voice"]["file"])

    my_lib.notify.line.hist_clear()


def move_to(time_machine, hour, minutes=0):
    import my_lib.time

    logging.info("TIME move to %02d:%02d", hour, minutes)
    time_machine.move_to(my_lib.time.now().replace(hour=hour, minute=minutes, second=0))


def check_notify_line(message, index=-1):
    import my_lib.notify.line

    notify_hist = my_lib.notify.line.hist_get()
    logging.debug(notify_hist)

    if message is None:
        assert notify_hist == [], "通知してはいけないいのに、通知がされています。"
    else:
        assert len(notify_hist) != 0, "通知がされていません。"
        assert notify_hist[index].find(message) != -1, f"「{message}」が Line で通知されていません。"


def sensor_mock(mocker, last_event, raining_sum, precip_sum, solar_rad):
    mocker.patch(
        "my_lib.sensor_data.fetch_data",
        return_value={
            "value": [solar_rad],
            "time": [],
            "valid": True,
        },
    )
    mocker.patch("my_lib.sensor_data.get_minute_sum", return_value=raining_sum)
    mocker.patch("my_lib.sensor_data.get_last_event", return_value=last_event)
    mocker.patch("rainfall.monitor.check_forecast", return_value=precip_sum)


def check_liveness(config):
    import healthz

    liveness = healthz.check_liveness(
        [
            {
                "name": name,
                "liveness_file": pathlib.Path(config["liveness"]["file"][name]),
                "interval": config[name]["interval_sec"],
            }
            for name in ["watch"]
        ]
    )

    assert liveness, "Liveness が更新されていません。"


######################################################################
def test_basic(config):
    app.do_work(config, 1)
    check_liveness(config)


def test_basic_with_rainfall_0(config, mocker, time_machine):
    import my_lib.time

    def voice_play(wav_data):
        voice_play.done = True

    voice_play.done = False

    mocker.patch("my_lib.voice.play", side_effect=voice_play)
    sensor_mock(mocker, last_event=my_lib.time.now(), raining_sum=10, precip_sum=1, solar_rad=0)

    move_to(time_machine, 12)

    app.do_work(config, 1)

    check_notify_line("雨が降り始めました！")
    assert voice_play.done


def test_basic_with_rainfall_1(config, mocker, time_machine):
    import my_lib.time

    def voice_play(wav_data):
        voice_play.done = True

    voice_play.done = False

    mocker.patch("my_lib.voice.play", side_effect=voice_play)
    sensor_mock(mocker, last_event=my_lib.time.now(), raining_sum=10, precip_sum=1, solar_rad=0)

    move_to(time_machine, 0)

    app.do_work(config, 1)

    check_notify_line("雨が降り始めました！")
    # NOTE: 深夜は音声通知しない
    assert not voice_play.done


def test_basic_with_rainfall_2(config, mocker, time_machine):
    import my_lib.time

    def voice_play(wav_data):
        voice_play.done = True

    voice_play.done = False

    mocker.patch("my_lib.voice.play", side_effect=voice_play)
    sensor_mock(mocker, last_event=my_lib.time.now(), raining_sum=0.05, precip_sum=0.05, solar_rad=0)

    move_to(time_machine, 12)

    app.do_work(config, 1)

    check_notify_line("雨が降り始めました！")
    # NOTE: 総雨量も予想雨量も小さい場合は音声通知しない
    assert not voice_play.done


def test_basic_with_rainfall_3(config, mocker, time_machine):
    import my_lib.time

    def voice_play(wav_data):
        voice_play.done = True

    voice_play.done = False

    mocker.patch("my_lib.voice.play", side_effect=voice_play)
    sensor_mock(mocker, last_event=my_lib.time.now(), raining_sum=10, precip_sum=1, solar_rad=0)

    move_to(time_machine, 12)

    app.do_work(config, 1)

    check_notify_line("雨が降り始めました！")
    assert voice_play.done


def test_basic_with_rainfall_4(config, mocker, time_machine):
    import my_lib.footprint
    import my_lib.time

    def voice_play(wav_data):
        voice_play.done = True

    voice_play.done = False
    mocker.patch("my_lib.voice.play", side_effect=voice_play)

    move_to(time_machine, 12)
    mocker.patch("rainfall.monitor.get_process_start", return_value=my_lib.time.now())
    sensor_mock(mocker, last_event=my_lib.time.now(), raining_sum=10, precip_sum=1, solar_rad=0)
    move_to(time_machine, 13)
    # NOTE: 通知済みにする
    my_lib.footprint.update(config["notify"]["footprint"]["line"]["file"])
    my_lib.footprint.update(config["notify"]["footprint"]["voice"]["file"])

    app.do_work(config, 1)

    check_notify_line(None)
    assert not voice_play.done


def test_basic_with_rainfall_5(config, mocker, time_machine):
    import my_lib.footprint
    import my_lib.time

    def voice_play(wav_data):
        voice_play.done = True

    voice_play.done = False
    mocker.patch("my_lib.voice.play", side_effect=voice_play)

    # NOTE: 12時に通知したことにする
    move_to(time_machine, 12, 0)
    my_lib.footprint.update(config["notify"]["footprint"]["line"]["file"])
    my_lib.footprint.update(config["notify"]["footprint"]["voice"]["file"])

    # NOTE: 12時1分に雨が降り始めたことにする
    move_to(time_machine, 12, 1)
    sensor_mock(mocker, last_event=my_lib.time.now(), raining_sum=10, precip_sum=1, solar_rad=0)
    mocker.patch("rainfall.monitor.get_process_start", return_value=my_lib.time.now())

    app.do_work(config, 1)

    check_notify_line(None)
    assert not voice_play.done


def test_basic_without_rainfall(config, mocker):
    sensor_mock(
        mocker,
        last_event=my_lib.time.now() - datetime.timedelta(days=1),
        raining_sum=10,
        precip_sum=1,
        solar_rad=0,
    )

    app.do_work(config, 1)

    check_notify_line(None)
