#  Copyright (c) Kuba Szczodrzyński 2024-10-10.

import curses
import curses.panel
from curses import A_BOLD
from enum import Enum, auto
from logging import info, warning
from typing import Callable

from pynetkit.cli.command import run_command
from pynetkit.util.logging import LoggingHandler

from .keycodes import Keycodes


class EscState(Enum):
    NONE = auto()
    ESCAPE = auto()
    FE_SS3 = auto()
    FE_CSI = auto()


COLORS: dict[str, tuple[int, int, int]]


def colors_init():
    global COLORS
    # name: (fg, curses_pair, curses_attr)
    COLORS = {
        "black": (curses.COLOR_BLACK, 0, curses.color_pair(0)),  # ANSI 0
        "blue": (curses.COLOR_BLUE, 4, curses.color_pair(4)),  # ANSI 1
        "green": (curses.COLOR_GREEN, 2, curses.color_pair(2)),  # ANSI 2
        "cyan": (curses.COLOR_CYAN, 6, curses.color_pair(6)),  # ANSI 3
        "red": (curses.COLOR_RED, 1, curses.color_pair(1)),  # ANSI 4
        "magenta": (curses.COLOR_MAGENTA, 5, curses.color_pair(5)),  # ANSI 5
        "yellow": (curses.COLOR_YELLOW, 3, curses.color_pair(3)),  # ANSI 6
        "white": (curses.COLOR_WHITE, 7, curses.color_pair(7)),  # ANSI 7
        "bright_black": (curses.COLOR_BLACK, 0, curses.color_pair(0) | A_BOLD),
        "bright_blue": (curses.COLOR_BLUE, 4, curses.color_pair(4) | A_BOLD),
        "bright_green": (curses.COLOR_GREEN, 2, curses.color_pair(2) | A_BOLD),
        "bright_cyan": (curses.COLOR_CYAN, 6, curses.color_pair(6) | A_BOLD),
        "bright_red": (curses.COLOR_RED, 1, curses.color_pair(1) | A_BOLD),
        "bright_magenta": (curses.COLOR_MAGENTA, 5, curses.color_pair(5) | A_BOLD),
        "bright_yellow": (curses.COLOR_YELLOW, 3, curses.color_pair(3) | A_BOLD),
        "bright_white": (curses.COLOR_WHITE, 7, curses.color_pair(7) | A_BOLD),
    }
    curses.use_default_colors()
    for fg, curses_pair, _ in COLORS.values():
        if curses_pair == 0:
            continue
        curses.init_pair(curses_pair, fg, -1)


def color_attr(name: str):
    return COLORS[name][2]


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


class LogWindow(BaseWindow):
    TITLE = "Log console"

    def __post_init__(self):
        # hook stdout/stderr and print in the log console
        logger = LoggingHandler.get()
        logger.add_emitter(self.emit_raw)
        logger.hook_stdout()

    def create(self) -> None:
        super().create()
        self.win.scrollok(True)
        self.win.idlok(True)
        self.win.leaveok(True)
        self.win.refresh()
        y, x = self.win.getmaxyx()
        self.win.move(y - 1, 0)

    def emit_raw(self, _: str, message: str, color: str, nl: bool) -> None:
        if nl:
            message = f"{message}\n"
        self.win.addstr(message, color_attr(color))
        self.win.refresh()


class InputWindow(BaseWindow):
    TITLE = "Command input"

    on_resize: Callable = None
    prompt: str = "=> "
    history: list[str]
    lines: list[str]
    index: int = 0
    pos: int = 0
    escape_state: EscState = EscState.NONE
    escape_code: str = ""

    def __post_init__(self) -> None:
        self.history = []
        self.lines = [""]

    def create(self) -> None:
        super().create()
        self.win.nodelay(False)
        curses.curs_set(1)
        self.redraw_prompt()

    def run(self) -> None:
        while True:
            ch = self.win.get_wch()
            ch = self.handle_escape(ch)
            if ch:
                self.handle_keypress(ch)

    def handle_escape(self, ch: int | str) -> int | str | None:
        in_ch = ch
        if isinstance(ch, str):
            if len(ch) != 1:
                return ch
            ch = ord(ch)
        match self.escape_state, ch:
            # process C0 control codes
            case (_, 0x1B):  # ESC, 0x1B
                self.escape_state = EscState.ESCAPE
            case (EscState.NONE, _):
                return in_ch
            # process C1 control codes
            case (EscState.ESCAPE, _) if ch in range(0x40, 0x5F + 1):
                match ch:
                    case 0x4E:  # ESC N, 0x8E, SS2
                        self.escape_state = EscState.NONE
                    case 0x4F:  # ESC O, 0x8F, SS3
                        self.escape_state = EscState.FE_SS3
                    case 0x50:  # ESC P, 0x90, DCS
                        self.escape_state = EscState.NONE
                    case 0x5B:  # ESC [, 0x9B, CSI
                        self.escape_state = EscState.FE_CSI
                    case 0x5C:  # ESC \, 0x9C, ST
                        self.escape_state = EscState.NONE
                    case 0x5D:  # ESC ], 0x9D, OSC
                        self.escape_state = EscState.NONE
            # terminate SS3
            case (EscState.FE_SS3, _):
                self.escape_state = EscState.NONE
            # terminate CSI
            case (EscState.FE_CSI, _) if ch not in range(0x20, 0x3F + 1):
                self.escape_state = EscState.NONE
        # store all characters received during escape sequence
        self.escape_code += in_ch
        if self.escape_code in Keycodes.MAPPING:
            # escape sequence found in key mapping, terminate immediately
            self.escape_state = EscState.NONE
        if self.escape_state == EscState.NONE:
            # no longer in the escape sequence (but it was active)
            code = self.escape_code
            self.escape_code = ""
            return code
        return None

    def set_cursor(self) -> None:
        self.win.move(0, len(self.prompt) + self.pos)

    def redraw_prompt(self) -> None:
        self.win.clear()
        self.win.addstr(0, 0, self.prompt + self.lines[self.index])
        self.set_cursor()

    def reset_prompt(self) -> None:
        self.win.clear()
        self.win.addstr(0, 0, self.prompt)
        self.lines = self.history + [""]
        self.index = len(self.history)
        self.pos = 0

    def cut_length(self, line: str, n: int) -> None:
        self.lines[self.index] = line[0 : self.pos] + line[self.pos + n :]
        self.win.move(0, len(self.prompt) + self.pos)
        self.win.addstr(line[self.pos + n :])
        self.win.addstr(" " * n)
        self.set_cursor()

    def seek_word_left(self, line: str) -> None:
        while self.pos:
            self.pos = line.rfind(" ", 0, self.pos - 1) + 1
            if line[self.pos] != " ":
                break
        self.set_cursor()

    def seek_word_right(self, line: str) -> None:
        while self.pos != len(line):
            self.pos = line.find(" ", self.pos + 1)
            if self.pos == -1:
                self.pos = len(line)
            if line[self.pos - 1] != " ":
                break
        self.set_cursor()

    def handle_keypress(self, ch: int | str) -> None:
        line = self.lines[self.index]
        ch = Keycodes.MAPPING.get(ch, ch)
        match ch:
            # Enter key
            case "\n":
                if line and line[0] != " ":
                    line = line.strip()
                    if not self.history or self.history[-1] != line:
                        self.history.append(line)
                self.reset_prompt()
                print("\n" + self.prompt + line)
                run_command(line)
                self.set_cursor()
            # Ctrl+C
            case "\x03":
                self.reset_prompt()

            # Arrow Up/Down keys
            case Keycodes.KEY_UP | Keycodes.KEY_DOWN:
                if ch == Keycodes.KEY_UP and self.index > 0:
                    self.index -= 1
                elif ch == Keycodes.KEY_DOWN and self.index < len(self.lines) - 1:
                    self.index += 1
                else:
                    return
                line = self.lines[self.index]
                self.win.clear()
                self.win.addstr(0, 0, self.prompt + line)
                self.pos = len(line)
            # Arrow Left/Right keys
            case Keycodes.KEY_LEFT | Keycodes.KEY_RIGHT:
                if ch == Keycodes.KEY_LEFT and self.pos > 0:
                    self.pos -= 1
                elif ch == Keycodes.KEY_RIGHT and self.pos < len(line):
                    self.pos += 1
                else:
                    return
                self.set_cursor()

            # Home
            case Keycodes.KEY_HOME:
                self.pos = 0
                self.set_cursor()
            # Key End
            case Keycodes.KEY_END:
                self.pos = len(line)
                self.set_cursor()

            # Ctrl+Left/Alt+Left
            case Keycodes.CTL_LEFT | Keycodes.ALT_LEFT:
                self.seek_word_left(line)
            # Ctrl+Right/Alt+Right
            case Keycodes.CTL_RIGHT | Keycodes.ALT_RIGHT:
                self.seek_word_right(line)

            # Ctrl+Backspace/Alt+Backspace
            case Keycodes.CTL_BKSP | Keycodes.ALT_BKSP:
                pos = self.pos
                self.seek_word_left(line)
                self.cut_length(line, pos - self.pos)
            # Ctrl+Delete/Alt+Delete
            case Keycodes.CTL_DEL | Keycodes.ALT_DEL:
                pos1 = self.pos
                self.seek_word_right(line)
                pos2 = self.pos
                self.pos = pos1
                self.cut_length(line, pos2 - pos1)

            # Backspace/Delete keys
            case Keycodes.KEY_BACKSPACE | Keycodes.KEY_DC:
                if ch == Keycodes.KEY_BACKSPACE:
                    if self.pos == 0:
                        return
                    self.pos -= 1
                elif ch == Keycodes.KEY_DC and self.pos >= len(line):
                    return
                self.cut_length(line, 1)

            # Help shortcut
            case "?" if line[max(self.pos - 1, 0) : self.pos + 1] in ["", " ", "  "]:
                line = line.strip()
                if line:
                    line += " --help"
                else:
                    line = "help"
                print("\n" + self.prompt + line)
                run_command(line)
                self.set_cursor()

            # Unrecognized escape codes (not in Keycodes.MAPPING)
            case str() if ch[0] == "\x1B":
                warning(f"Unrecognized escape sequence: {ch.encode()}")
                return

            # Window resize
            case curses.KEY_RESIZE:
                if self.on_resize:
                    self.on_resize()

            # Any other keys (letters/numbers/etc.)
            case str():
                self.lines[self.index] = line[0 : self.pos] + ch + line[self.pos :]
                self.pos += len(ch)
                self.win.insstr(ch)
                self.win.move(0, len(self.prompt) + self.pos)
            case int():
                info(f"Key event: {ch}")


def main(stdscr: curses.window):
    colors_init()

    def on_resize() -> None:
        stdscr.clear()
        log_window.resize()
        input_window.resize()

    cmd_size = 3
    log_window = LogWindow(stdscr, nlines=-cmd_size, ncols=None, y=0, x=0)
    input_window = InputWindow(stdscr, nlines=cmd_size, ncols=None, y=-cmd_size, x=0)
    input_window.on_resize = on_resize
    input_window.run()


def cli_curses():
    curses.wrapper(main)
