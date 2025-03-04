#  Copyright (c) Kuba Szczodrzyński 2024-10-10.

import curses
import curses.panel

from .windows.base import colors_init
from .windows.input import InputWindow
from .windows.log import LogWindow


def main(stdscr: curses.window):
    colors_init()

    def on_resize() -> None:
        stdscr.clear()
        log_window.resize()
        input_window.resize()

    try:
        cmd_size = 3
        log_window = LogWindow(stdscr, nlines=-cmd_size, ncols=None, y=0, x=0)
        input_window = InputWindow(
            stdscr, nlines=cmd_size, ncols=None, y=-cmd_size, x=0
        )
        input_window.on_resize = on_resize
        input_window.on_scroll = log_window.on_scroll
        input_window.run()
    except SystemExit:
        # exit gracefully, allowing curses to reset the terminal
        pass

    # disable mouse events
    curses.mousemask(0)
    # unhook logger from stdout
    log_window.logger.unhook_stdout()


def cli_curses():
    curses.wrapper(main)
