#  Copyright (c) Kuba Szczodrzyński 2024-10-10.

import curses
import curses.panel
from enum import Enum, auto
from logging import info, warning
from typing import Callable

from pynetkit.cli.command import run_command

from .base import BaseWindow
from .input_keycodes import Keycodes


class EscState(Enum):
    NONE = auto()
    ESCAPE = auto()
    FE_SS3 = auto()
    FE_CSI = auto()


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
            if ch == "\x00":
                continue
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
        self.win.refresh()
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