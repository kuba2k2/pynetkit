#  Copyright (c) Kuba Szczodrzyński 2023-9-8.

import logging
from logging import CRITICAL, DEBUG, ERROR, INFO, WARNING, log
from threading import current_thread

VERBOSE = DEBUG // 2


class LoggerMixin:
    def __init__(self):
        super().__init__()

    def verbose(self, msg, *args, **kwargs):
        self.log(VERBOSE, msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self.log(DEBUG, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.log(INFO, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.log(WARNING, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.log(ERROR, msg, *args, **kwargs)

    def exception(self, msg, *args, exc_info=True, **kwargs):
        self.error(msg, *args, exc_info=exc_info, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.log(CRITICAL, msg, *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        if logging.getLogger().level <= DEBUG:
            msg = f"{type(self).__name__}<{current_thread().name}>: {msg}"
        else:
            msg = f"{type(self).__name__}: {msg}"
        log(
            level,
            msg,
            *args,
            **kwargs,
        )
