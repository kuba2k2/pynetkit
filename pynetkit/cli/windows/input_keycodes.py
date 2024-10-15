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

        # https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
        MAPPING = {
            "\x1b[A": KEY_UP,
            "\x1b[B": KEY_DOWN,
            "\x1b[D": KEY_LEFT,
            "\x1b[C": KEY_RIGHT,
            "\x7f": KEY_BACKSPACE,
            "\x08": KEY_BACKSPACE,
            "\x1b[3~": KEY_DC,
            "\x1b\x7f": ALT_BKSP,
            "\x1b\x08": ALT_BKSP,
            # PuTTY (default settings)
            "\x1b[1~": KEY_HOME,
            "\x1b[4~": KEY_END,
            "\x1bOD": CTL_LEFT,
            "\x1bOC": CTL_RIGHT,
            "\x1b\x1b[D": ALT_LEFT,
            "\x1b\x1b[C": ALT_RIGHT,
            "\x1b\x1b[3~": ALT_DEL,
            # xterm
            "\x1b[H": KEY_HOME,
            "\x1b[F": KEY_END,
            "\x1b[1;5D": CTL_LEFT,
            "\x1b[1;5C": CTL_RIGHT,
            "\x1b[1;3D": ALT_LEFT,
            "\x1b[1;3C": ALT_RIGHT,
        }

else:
    warning("Unknown platform - command line keycodes will not work correctly")

    class Keycodes:
        MAPPING = {}
