#  Copyright (c) Kuba Szczodrzyński 2024-10-14.

import curses
import sys
from logging import warning

if sys.platform == "win32":

    class Keycodes:
        KEY_UP = curses.KEY_UP
        KEY_DOWN = curses.KEY_DOWN
        KEY_LEFT = curses.KEY_LEFT
        KEY_RIGHT = curses.KEY_RIGHT
        KEY_HOME = curses.KEY_HOME
        KEY_END = curses.KEY_END
        KEY_BACKSPACE = curses.KEY_BACKSPACE
        KEY_DC = curses.KEY_DC

        CTL_LEFT = curses.CTL_LEFT
        CTL_RIGHT = curses.CTL_RIGHT
        CTL_BKSP = curses.CTL_BKSP
        CTL_DEL = curses.CTL_DEL

        ALT_LEFT = curses.ALT_LEFT
        ALT_RIGHT = curses.ALT_RIGHT
        ALT_BKSP = curses.ALT_BKSP
        ALT_DEL = curses.ALT_DEL

        MAPPING = {
            "\x08": KEY_BACKSPACE,
            "\x7F": CTL_BKSP,
        }

elif sys.platform == "linux":

    class Keycodes:
        KEY_UP = curses.KEY_UP
        KEY_DOWN = curses.KEY_DOWN
        KEY_LEFT = curses.KEY_LEFT
        KEY_RIGHT = curses.KEY_RIGHT
        KEY_HOME = curses.KEY_HOME
        KEY_END = curses.KEY_END
        KEY_BACKSPACE = curses.KEY_BACKSPACE
        KEY_DC = curses.KEY_DC

        CTL_LEFT = 443
        CTL_RIGHT = 444
        CTL_BKSP = 505
        CTL_DEL = 527

        ALT_LEFT = 493
        ALT_RIGHT = 492
        ALT_BKSP = 504
        ALT_DEL = 478

        MAPPING = {}

else:
    warning("Unknown platform - command line keycodes will not work correctly")

    class Keycodes:
        MAPPING = {}
