#!/usr/bin/env python3
# ruff: noqa: S101
import datetime
import pathlib
from unittest import mock

import app
import my_lib.config
import pytest
import zoneinfo

TIMEZONE = zoneinfo.ZoneInfo("Asia/Tokyo")
CONFIG_FILE = "config.example.yaml"


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


@pytest.fixture(autouse=True)
def _clear():
    import my_lib.notify.slack

    config = my_lib.config.load(CONFIG_FILE)

    pathlib.Path(config["liveness"]["file"]["watch"]).unlink(missing_ok=True)
    pathlib.Path(config["notify"]["footprint"]["line"]["file"]).unlink(missing_ok=True)
    pathlib.Path(config["notify"]["footprint"]["voice"]["file"]).unlink(missing_ok=True)


@pytest.fixture()
def config():
    return my_lib.config.load(CONFIG_FILE, pathlib.Path(app.SCHEMA_CONFIG))


######################################################################
def test_basic(config):
    app.do_work(config, 1)


def test_basic_with_rainfall(config, mocker):
    mocker.patch("rainfall.monitor.get_last_event", return_value=datetime.datetime.now(TIMEZONE))
    app.do_work(config, 1)


def test_basic_without_rainfall(config, mocker):
    mocker.patch(
        "rainfall.monitor.get_last_event",
        return_value=datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=1),
    )
    app.do_work(config, 1)
