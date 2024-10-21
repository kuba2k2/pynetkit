#  Copyright (c) Kuba Szczodrzyński 2024-10-10.


from .base import BaseWindow

ANSI_TO_COLOR = {
    "30": "black",
    "31": "red",
    "33": "yellow",
    "32": "green",
    "34": "blue",
    "35": "magenta",
    "36": "cyan",
    "37": "white",
    "90": "bright_black",
    "91": "bright_red",
    "92": "bright_green",
    "93": "bright_yellow",
    "94": "bright_blue",
    "95": "bright_magenta",
    "96": "bright_cyan",
    "97": "bright_white",
}


TokenType = tuple[str, int] | None
LineType = list[TokenType]


class LogWindow(BaseWindow):
    TITLE = "Log console"
    lines: list[LineType]
    scroll: int = 0

    def __post_init__(self):
        self.lines = []
        self.scroll = 0
        # hook stdout/stderr and print in the log console
        self.logger.add_emitter(self.emit_raw)
        self.logger.hook_stdout()

    def create(self) -> None:
        super().create()
        self.win.scrollok(True)
        self.win.idlok(True)
        self.win.leaveok(True)
        self.win.refresh()
        self._redraw_log()

    def emit_raw(self, _: str, message: str, color: str, nl: bool) -> None:
        if nl:
            message = f"{message}\n"
        attr = self.color_attr(color)
        reset = attr

        if not self.lines or None in self.lines[-1]:
            # no lines, or last line terminated with \n
            line = []
            self.lines.append(line)
        else:
            line = self.lines[-1]

        if "\x1b" not in message:
            self._add_message(line, message, attr)
            self.win.refresh()
            return
        for message in message.split("\x1b"):
            if not message:
                continue
            if len(message) >= 3 and message[0] == "[" and "m" in message[2:4]:
                message, attr = self._process_color(message, attr, reset)
            line = self._add_message(line, message, attr)
        self.win.refresh()

    def _add_message(
        self,
        line: LineType,
        message: str,
        attr: int,
    ) -> LineType:
        if self.scroll == 0:
            # print the message directly if not scrolled
            self.win.addstr(message, attr)
        if "\n" not in message:
            line.append((message, attr))
            return line
        delim = "\n"
        while delim:
            # repeat until there are no more \n
            token, delim, message = message.partition(delim)
            if token:
                line.append((token, attr))
            if delim:
                line.append(None)
                line = []
                self.lines.append(line)
                if self.scroll != 0:
                    # new line added - update the scroll line count and indicator
                    self.scroll += 1
                    self._show_scroll()
        return line

    def _redraw_log(self) -> None:
        y, x = self.win.getmaxyx()
        self.win.clear()
        self.win.move(y - 1, 0)
        if self.scroll:
            lines = self.lines[-y - self.scroll - 1 : -self.scroll - 1]
        else:
            lines = self.lines[-y:]
        for line in lines:
            for token in line:
                if token is None:
                    self.win.addstr("\n")
                    break
                message, attr = token
                self.win.addstr(message, attr)
        if self.scroll:
            self._show_scroll()
        if lines:
            self.win.refresh()

    def _show_scroll(self) -> None:
        y, x = self.win.getmaxyx()
        self.win.move(y - 1, 0)
        self.win.addstr(
            (
                f"... 1 more line ..."
                if self.scroll == 1
                else f"... {self.scroll} more lines ..."
            ),
            self.color_attr("bright_black"),
        )

    def on_scroll(self, lines: int) -> None:
        y, x = self.win.getmaxyx()
        # allow at least 0 and at most 'y' scroll lines
        scroll = self.scroll
        self.scroll = max(0, min(len(self.lines) - y, self.scroll + lines))
        if self.scroll != scroll:
            # only redraw if scroll changed
            self._redraw_log()

    def _process_color(self, message: str, attr: int, reset: int) -> tuple[str, int]:
        code, _, rest = message[1:].partition("m")
        if code in ANSI_TO_COLOR:
            message = rest
            attr = self.color_attr(ANSI_TO_COLOR[code])
        elif code in ["0", "39"]:
            message = rest
            attr = reset
        elif code.isnumeric():
            message = rest
        return message, attr
