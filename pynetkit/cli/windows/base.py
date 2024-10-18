#  Copyright (c) Kuba Szczodrzyński 2024-10-10.

import curses
import curses.panel
from curses import A_BOLD

from pynetkit.util.logging import LoggingHandler

COLORS: dict[str, tuple[int, int, int]]


def colors_init():
    global COLORS
    # name: (fg, curses_pair, curses_attr)
    COLORS = {
        "black": (curses.COLOR_BLACK, 8, curses.color_pair(8)),
        "red": (curses.COLOR_RED, 1, curses.color_pair(1)),
        "yellow": (curses.COLOR_YELLOW, 3, curses.color_pair(3)),
        "green": (curses.COLOR_GREEN, 2, curses.color_pair(2)),
        "blue": (curses.COLOR_BLUE, 4, curses.color_pair(4)),
        "magenta": (curses.COLOR_MAGENTA, 5, curses.color_pair(5)),
        "cyan": (curses.COLOR_CYAN, 6, curses.color_pair(6)),
        "white": (curses.COLOR_WHITE, 7, curses.color_pair(7)),
        "bright_black": (curses.COLOR_BLACK, 8, curses.color_pair(8) | A_BOLD),
        "bright_red": (curses.COLOR_RED, 1, curses.color_pair(1) | A_BOLD),
        "bright_green": (curses.COLOR_GREEN, 2, curses.color_pair(2) | A_BOLD),
        "bright_yellow": (curses.COLOR_YELLOW, 3, curses.color_pair(3) | A_BOLD),
        "bright_blue": (curses.COLOR_BLUE, 4, curses.color_pair(4) | A_BOLD),
        "bright_magenta": (curses.COLOR_MAGENTA, 5, curses.color_pair(5) | A_BOLD),
        "bright_cyan": (curses.COLOR_CYAN, 6, curses.color_pair(6) | A_BOLD),
        "bright_white": (curses.COLOR_WHITE, 7, curses.color_pair(7) | A_BOLD),
    }
    curses.use_default_colors()
    for fg, curses_pair, _ in COLORS.values():
        if curses_pair == 0:
            continue
        curses.init_pair(curses_pair, fg, -1)


class BaseWindow:
    TITLE = "Window"
    border: curses.window
    win: curses.window

    def _get_size(self, y: int | None, x: int | None) -> tuple[int, int]:
        maxy, maxx = self.stdscr.getmaxyx()
        if y is None:
            y = maxy
        elif y < 0:
            y += maxy
        if x is None:
            x = maxx
        elif x < 0:
            x += maxx
        return y, x

    def __init__(
        self,
        stdscr: curses.window,
        nlines: int | None,
        ncols: int | None,
        y: int,
        x: int,
    ):
        self.logger = LoggingHandler.get()
        self.stdscr = stdscr
        self.nlines = nlines
        self.ncols = ncols
        self.y = y
        self.x = x
        self.__post_init__()
        self.create()

    def __post_init__(self) -> None:
        pass

    def create(self) -> None:
        nlines, ncols = self._get_size(self.nlines, self.ncols)
        y, x = self._get_size(self.y, self.x)
        self.border = self.stdscr.subwin(nlines, ncols, y, x)
        self.border.border()
        self.border.addstr(0, 2, f" {self.TITLE} ")
        self.border.refresh()
        self.win = self.stdscr.subwin(nlines - 2, ncols - 2, y + 1, x + 1)
        self.win.refresh()

    def resize(self) -> None:
        # completely destroy the old window and create a new one
        # after hours of troubleshooting, I have not found a single solution
        # that would properly (and reliably) handle terminal resizing, without crashing
        del self.border
        del self.win
        self.create()

    @staticmethod
    def color_attr(name: str):
        return COLORS[name][2]
