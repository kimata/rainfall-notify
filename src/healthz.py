#!/usr/bin/env python3
"""
Liveness のチェックを行います

Usage:
  healthz.py [-c CONFIG] [-D]

Options:
  -c CONFIG         : CONFIG を設定ファイルとして読み込んで実行します。[default: config.yaml]
  -D                : デバッグモードで動作します。
"""

import logging
import pathlib
import sys

import my_lib.healthz

SCHEMA_CONFIG = "config.schema"


def check_liveness(target_list):
    for target in target_list:
        if not my_lib.healthz.check_liveness(target["name"], target["liveness_file"], target["interval"]):
            return False

    return True


######################################################################
if __name__ == "__main__":
    import docopt
    import my_lib.config
    import my_lib.logger
    import my_lib.pretty

    args = docopt.docopt(__doc__)

    config_file = args["-c"]
    debug_mode = args["-D"]

    log_level = logging.DEBUG if debug_mode else logging.INFO

    my_lib.logger.init("notify.rainfall", level=log_level)

    config = my_lib.config.load(config_file, pathlib.Path(SCHEMA_CONFIG))

    target_list = [
        {
            "name": name,
            "liveness_file": pathlib.Path(config["liveness"]["file"][name]),
            "interval": config[name]["interval_sec"],
        }
        for name in ["watch"]
    ]

    logging.debug(my_lib.pretty.format(target_list))

    if check_liveness(target_list):
        logging.info("OK.")
        sys.exit(0)
    else:
        sys.exit(-1)
