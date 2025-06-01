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
        retunr_value=True,
    ) as fixture:
        yield fixture


@pytest.fixture(scope="session", autouse=True)
def voice_play_mock():
    with mock.patch(
        "my_lib.voice.play",
        retunr_value=True,
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


def check_notify_line(message, index=-1):
    import my_lib.notify.line

    notify_hist = my_lib.notify.line.hist_get()
    logging.debug(notify_hist)

    if message is None:
        assert notify_hist == [], "正常なはずなのに、エラー通知がされています。"
    else:
        assert len(notify_hist) != 0, "異常が発生したはずなのに、エラー通知がされていません。"
        assert notify_hist[index].find(message) != -1, f"「{message}」が Slack で通知されていません。"


######################################################################
def test_basic(config):
    app.do_work(config, 1)


def test_basic_with_rainfall(config, mocker):
    import my_lib.time

    mocker.patch(
        "my_lib.sensor_data.fetch_data",
        return_value={
            "value": [0],
            "time": [],
            "valid": True,
        },
    )
    mocker.patch("my_lib.sensor_data.get_last_event", return_value=my_lib.time.now())
    app.do_work(config, 1)

    check_notify_line("雨が降り始めました！")


def test_basic_with_rainfall_solar_rad(config, mocker):
    import my_lib.time

    mocker.patch(
        "my_lib.sensor_data.fetch_data",
        return_value={
            "value": [1000],
            "time": [],
            "valid": True,
        },
    )
    mocker.patch("my_lib.sensor_data.get_last_event", return_value=my_lib.time.now())
    app.do_work(config, 1)

    check_notify_line(None)


def test_basic_without_rainfall(config, mocker):
    mocker.patch(
        "my_lib.sensor_data.fetch_data",
        return_value={
            "value": [0],
            "time": [],
            "valid": True,
        },
    )
    mocker.patch(
        "my_lib.sensor_data.get_last_event",
        return_value=my_lib.time.now() - datetime.timedelta(days=1),
    )
    app.do_work(config, 1)

    check_notify_line(None)
