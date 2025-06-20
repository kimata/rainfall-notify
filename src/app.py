#!/usr/bin/env python3
"""
雨の降り始めを通知します。

Usage:
  app.py [-c CONFIG] [-n COUNT] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -n COUNT     	    : 実行回数 [default: 0]
  -D                : デバッグモードで動作します。
"""

import logging
import time

import my_lib.footprint
import rainfall.monitor

SCHEMA_CONFIG = "config.schema"


def do_work(config, count=0):
    i = 0
    while True:
        start_time = time.time()
        rainfall.monitor.watch(config)

        my_lib.footprint.update(config["liveness"]["file"]["watch"])

        i += 1
        if i == count:
            logging.info("The specified number of attempts has been reached, so the process will end.")
            break

        time.sleep(max(config["watch"]["interval_sec"] - (time.time() - start_time), 1))


if __name__ == "__main__":
    import docopt
    import my_lib.config
    import my_lib.logger

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    count = int(args["-n"])
    debug_mode = args["-D"]

    log_level = logging.DEBUG if debug_mode else logging.INFO

    my_lib.logger.init("notify.rainfall", level=log_level)

    config = my_lib.config.load(config_file, SCHEMA_CONFIG)

    do_work(config, count)
