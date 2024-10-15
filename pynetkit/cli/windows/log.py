#  Copyright (c) Kuba Szczodrzyński 2024-10-10.

from pynetkit.util.logging import LoggingHandler

from .base import BaseWindow


class LogWindow(BaseWindow):
    TITLE = "Log console"
    messages: list[tuple[str, int, int]]

    def __post_init__(self):
        self.messages = []
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
        draw_messages = []
        draw_lines = 0
        for message, attr, lines in reversed(self.messages):
            draw_messages.append((message, attr))
            draw_lines += lines
            if draw_lines > y - 2:
                break
        for message, attr in reversed(draw_messages):
            self.win.addstr(message, attr)
        if self.messages:
            self.win.refresh()

    def emit_raw(self, _: str, message: str, color: str, nl: bool) -> None:
        if nl:
            message = f"{message}\n"
        attr = self.color_attr(color)
        self.win.addstr(message, attr)
        self.win.refresh()
        self.messages.append((message, attr, message.count("\n")))
        if len(self.messages) > 1000:
            self.messages = self.messages[-1000:]
