#  Copyright (c) Kuba Szczodrzyński 2024-10-10.

import curses
import curses.panel
import signal
from enum import Enum, auto
from logging import exception, info, warning
from os.path import commonprefix
from typing import Callable

from pynetkit.cli.command import run_command, run_completion

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
    on_scroll: Callable[[int], None] = None
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
        curses.mousemask(-1)
        signal.signal(signal.SIGINT, self.handle_sigint)
        self.redraw_prompt()

    def run(self) -> None:
        while True:
            try:
                ch = self.win.get_wch()
                if ch == "\x00":
                    continue
                ch = self.handle_escape(ch)
                if ch:
                    self.handle_keypress(ch)
            except Exception as e:  # does not catch SystemExit
                if str(e) == "no input":
                    # special case for Ctrl+C in curses
                    continue
                exception("Input handler failed", exc_info=e)

    def handle_sigint(self, sig: int, frame) -> None:
        self.handle_keypress("\x03")

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

    def run_command(self, line: str) -> None:
        line, _, comment = line.strip().partition("#")
        line = line.strip()
        comment = comment.strip()
        if not line and comment:
            self.logger.emit_string(
                log_prefix="",
                message="\n# " + comment,
                color="bright_black",
            )
            return
        self.logger.emit_string(
            log_prefix="",
            message="\n" + self.prompt + line,
            color="bright_cyan",
        )
        run_command(line)
        self.set_cursor()

    def handle_keypress(self, ch: int | str) -> None:
        line = self.lines[self.index]
        ch = Keycodes.MAPPING.get(ch, ch)
        match ch:
            # Enter key
            case "\n":
                if line and line[0] != " ":
                    line = line.lstrip()
                    if not self.history or self.history[-1] != line:
                        self.history.append(line)
                self.reset_prompt()
                self.run_command(line)
            # Ctrl+C
            case "\x03":
                self.logger.emit_string(
                    log_prefix="",
                    message="\n" + self.prompt + self.lines[self.index] + "^C",
                    color="bright_cyan",
                )
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

            # PgUp/Shift+PgUp
            case Keycodes.KEY_PPAGE | Keycodes.KEY_SPREVIOUS:
                if not self.on_scroll:
                    return
                self.on_scroll(10)
            # PgDn/Shift+PgDn
            case Keycodes.KEY_NPAGE | Keycodes.KEY_SNEXT:
                if not self.on_scroll:
                    return
                self.on_scroll(-10)
            # Ctrl+PgUp/Ctrl+PgDn
            case Keycodes.CTL_PGUP | Keycodes.CTL_PGDN:
                if not self.on_scroll:
                    return
                self.on_scroll(1 if ch == Keycodes.CTL_PGUP else -1)

            # Mouse events (Windows)
            case curses.KEY_MOUSE:
                id, x, y, z, bstate = curses.getmouse()
                if not self.on_scroll:
                    return
                # info(f"{id=}, {x=}, {y=}, {z=}, {bstate=}")
                if bstate == curses.BUTTON4_PRESSED:
                    # Scroll Up
                    self.on_scroll(3)
                elif bstate == curses.BUTTON5_PRESSED:
                    # Scroll Down
                    self.on_scroll(-3)
            # Mouse events (Linux)
            case str() if "\x1b[<" in ch and ch[-1:] in "mM":
                if ch[3:].startswith("64;"):
                    # Scroll Up
                    self.on_scroll(3)
                elif ch[3:].startswith("65;"):
                    # Scroll Down
                    self.on_scroll(-3)

            # Help shortcut
            case "?" if not line[max(self.pos - 1, 0) : self.pos + 1].strip():
                line = line[0 : self.pos].strip()
                if line:
                    line += " --help"
                else:
                    line = "help"
                self.run_command(line)

            # Completion shortcut
            case "\x09":
                line_part = line[0 : self.pos]
                completions = run_completion(line_part)
                if completions is None:
                    # completion is not valid, do nothing
                    return
                completions = sorted(completions)
                completion = ""
                _, _, incomplete = line_part.rpartition(" ")
                if len(completions) > 1:
                    # completion returned multiple items
                    comp = "\t".join(completions)
                    # fill in the common prefix of all completions
                    completion = commonprefix(completions)[len(incomplete) :]
                    self.logger.emit_string(
                        log_prefix="",
                        message="\n" + self.prompt + line_part + completion,
                        color="magenta",
                    )
                    self.logger.emit_string(log_prefix="", message=comp)
                elif len(completions) == 0:
                    # completion is at word boundary, add a whitespace
                    if line_part[-1:].strip():
                        # only add it if not there already
                        completion = " "
                else:
                    # completion returned one valid item, use it
                    completion = completions[0][len(incomplete) :] + " "
                if not completion:
                    return
                # add the completion to the command
                self.lines[self.index] = line_part + completion + line[self.pos :]
                self.pos += len(completion)
                self.win.insstr(completion)
                self.set_cursor()

            # Unrecognized escape codes (not in Keycodes.MAPPING)
            case str() if ch[0] == "\x1b":
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
                self.set_cursor()
            case int():
                info(f"Key event: {ch}")
