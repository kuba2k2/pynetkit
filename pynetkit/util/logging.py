#  Copyright (c) Kuba Szczodrzyński 2022-12-22.

import logging
import sys
import threading
from logging import (
    DEBUG,
    ERROR,
    INFO,
    Logger,
    LogRecord,
    StreamHandler,
    error,
    exception,
    log,
)
from threading import Lock
from time import time
from typing import Callable

import click

VERBOSE = DEBUG // 2


# Stripped-down logging handler from ltchiptool
class LoggingHandler(StreamHandler):
    INSTANCE: "LoggingHandler" = None
    LOG_COLORS = {
        "": "white",
        "V": "bright_cyan",
        "D": "bright_blue",
        "I": "bright_green",
        "W": "bright_yellow",
        "E": "bright_red",
        "C": "bright_magenta",
        "S": "bright_magenta",
    }

    @staticmethod
    def get() -> "LoggingHandler":
        if LoggingHandler.INSTANCE:
            return LoggingHandler.INSTANCE
        return LoggingHandler()

    def __init__(
        self,
        timed: bool = False,
        raw: bool = False,
        full_traceback: bool = True,
    ) -> None:
        super().__init__()
        LoggingHandler.INSTANCE = self
        self.time_start = time()
        self.time_prev = self.time_start
        self.timed = timed
        self.raw = raw
        self.full_traceback = full_traceback
        self.emitters = []
        self.attach()
        sys.excepthook = self.excepthook
        threading.excepthook = self.excepthook
        self.emit_lock = Lock()

    @property
    def level(self):
        return logging.root.level

    @level.setter
    def level(self, value: int):
        logging.root.setLevel(value)

    def attach(self, logger: Logger = None):
        logging.addLevelName(VERBOSE, "VERBOSE")
        logging.captureWarnings(True)
        if logger:
            root = logging.root
            logger.setLevel(root.level)
        else:
            logger = logging.root
        for h in logger.handlers:
            logger.removeHandler(h)
        logger.addHandler(self)

    def add_emitter(self, emitter: Callable[[str, str, str, bool], None]):
        self.emitters.append(emitter)

    def clear_emitters(self):
        self.emitters.clear()

    def add_level(self, name: str, color: str, level: int):
        logging.addLevelName(level, name)
        self.LOG_COLORS[name[0]] = color

    # noinspection PyUnresolvedReferences,PyProtectedMember
    def hook_stdout(self):
        # keep original values
        if not hasattr(sys.stdout, "_write_hook"):
            setattr(sys.stdout, "_write_hook", sys.stdout.write)
            setattr(sys.stderr, "_write_hook", sys.stderr.write)
        # hook stdout/stderr write() to capture all messages
        sys.stdout.write = self.write
        sys.stderr.write = self.write
        # also add hooks for click.echo() calls
        setattr(click.utils, "_default_text_stdout", lambda: sys.stdout)
        setattr(click.utils, "_default_text_stderr", lambda: sys.stderr)
        setattr(click._compat, "_get_windows_console_stream", lambda c, *_: c)
        setattr(click.utils, "auto_wrap_for_ansi", lambda s, *_: s)

    def unhook_stdout(self):
        if not hasattr(sys.stdout, "_write_hook"):
            return
        sys.stdout.write = getattr(sys.stdout, "_write_hook")
        sys.stderr.write = getattr(sys.stderr, "_write_hook")

    def emit(self, record: LogRecord) -> None:
        message = record.msg
        if message and record.args:
            message = message % record.args
        if record.exc_info:
            _, e, _ = record.exc_info
            if e:
                self.emit_exception(e=e, msg=message)
        else:
            self.emit_string(record.levelname[:1], message)

    def emit_string(
        self,
        log_prefix: str,
        message: str,
        color: str = None,
        nl: bool = True,
    ):
        now = time()
        elapsed_total = now - self.time_start
        elapsed_current = now - self.time_prev

        color = color or self.LOG_COLORS[log_prefix]

        if log_prefix:
            if self.timed:
                message = f"{log_prefix} [{elapsed_total:11.3f}] (+{elapsed_current:5.3f}s) {message}"
            elif not self.raw:
                message = f"{log_prefix}: {message}"

        self.emit_lock.acquire(timeout=1.0)
        if sys.stdout.write != self.write:
            file = sys.stderr if log_prefix and log_prefix in "WEC" else sys.stdout
            if file:
                if self.raw:
                    click.echo(message, file=file, nl=nl)
                else:
                    click.secho(message, file=file, nl=nl, fg=color)
        for emitter in self.emitters:
            emitter(log_prefix, message, color, nl)
        self.emit_lock.release()

        self.time_prev += elapsed_current

    def emit_exception(self, e: BaseException, msg: str = None):
        def tb_echo(echo_tb):
            filename = echo_tb.tb_frame.f_code.co_filename
            name = echo_tb.tb_frame.f_code.co_name
            line = echo_tb.tb_lineno
            graph(1, f'File "{filename}", line {line}, in {name}', loglevel=ERROR)

        original_exc = e
        if msg:
            error(msg)
        while e:
            if e == original_exc:
                error(f"{type(e).__name__}: {e}")
            else:
                error(f"Caused by {type(e).__name__}: {e}")
            tb = e.__traceback__
            if tb:
                while tb.tb_next:
                    if self.full_traceback:
                        tb_echo(tb)
                    tb = tb.tb_next
                tb_echo(tb)
            e = e.__context__

    def write(self, s) -> None:
        if isinstance(s, bytes):
            s = s.decode("utf-8")
        self.emit_string("", str(s), nl=False)

    def excepthook(self, *args):
        if isinstance(args[0], type):
            exception(None, exc_info=args[1])
        else:
            exception(None, exc_info=args[0].exc_value)


def verbose(msg, *args, **kwargs):
    logging.log(VERBOSE, msg, *args, **kwargs)


def graph(level: int, *message, loglevel: int = INFO):
    prefix = (level - 1) * "|   " + "|-- " if level else ""
    message = " ".join(str(m) for m in message)
    log(loglevel, f"{prefix}{message}")
