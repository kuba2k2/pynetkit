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


class LogWindow(BaseWindow):
    TITLE = "Log console"
    messages: list[tuple[str, int, int]]

    def __post_init__(self):
        self.messages = []
        # hook stdout/stderr and print in the log console
        self.logger.add_emitter(self.emit_raw)
        self.logger.hook_stdout()

    def create(self) -> None:
        super().create()
        self.win.scrollok(True)
        self.win.idlok(True)
        self.win.leaveok(True)
        self.win.refresh()
        y, x = self.win.getmaxyx()
        self.win.move(y - 1, 0)
        draw_messages = []
        draw_lines = 0
        for message, attr, lines in reversed(self.messages):
            draw_messages.append((message, attr))
            draw_lines += lines
            if draw_lines > y - 2:
                break
        for message, attr in reversed(draw_messages):
            self.addstr(message, attr)
        if self.messages:
            self.win.refresh()

    def emit_raw(self, _: str, message: str, color: str, nl: bool) -> None:
        if nl:
            message = f"{message}\n"
        attr = self.color_attr(color)
        self.addstr(message, attr)
        self.win.refresh()
        self.messages.append((message, attr, message.count("\n")))
        if len(self.messages) > 1000:
            self.messages = self.messages[-1000:]

    def _process_color(self, message: str, attr: int, reset: int) -> tuple[str, int]:
        code, _, rest = message[1:].partition("m")
        if code in ANSI_TO_COLOR:
            message = rest
            attr = self.color_attr(ANSI_TO_COLOR[code])
        elif code in ["0", "39"]:
            message = rest
            attr = reset
        return message, attr

    def addstr(self, message: str, attr: int) -> None:
        reset = attr
        if "\x1b" not in message:
            self.win.addstr(message, attr)
            return
        for message in message.split("\x1b"):
            if not message:
                continue
            if len(message) >= 3 and message[0] == "[" and "m" in message[2:4]:
                message, attr = self._process_color(message, attr, reset)
            self.win.addstr(message, attr)
