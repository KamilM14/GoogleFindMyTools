#
#  GoogleFindMyTools - A set of tools to interact with the Google Find My API
#  Copyright © 2024 Leon Böttger. All rights reserved.
#

import os
import re
import sys

_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _enable_windows_ansi() -> bool:
    """Windows 10+ understands ANSI colors, but only after switching the console mode on."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def _detect_ansi(stream) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.name == "nt":
        return _enable_windows_ansi()
    return True


def visible_len(text: str) -> int:
    return len(_ANSI_PATTERN.sub("", text))


def truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[:width - 1] + "…"


class Console:
    """Input/output for the menu. Tests pass their own input function and output stream."""

    def __init__(self, input_func=input, output=None, ansi=None):
        self._input = input_func
        self._output = output if output is not None else sys.stdout
        self.ansi = _detect_ansi(self._output) if ansi is None else ansi

    # --- output -----------------------------------------------------------------

    def print(self, text: str = "") -> None:
        print(text, file=self._output)

    def _style(self, code: str, text: str) -> str:
        if not self.ansi or not text:
            return text
        return f"\x1b[{code}m{text}\x1b[0m"

    def bold(self, text: str) -> str:
        return self._style("1", text)

    def dim(self, text: str) -> str:
        return self._style("2", text)

    def red(self, text: str) -> str:
        return self._style("31", text)

    def green(self, text: str) -> str:
        return self._style("32", text)

    def yellow(self, text: str) -> str:
        return self._style("33", text)

    def cyan(self, text: str) -> str:
        return self._style("36", text)

    def clear(self) -> None:
        # Without ANSI support (e.g. output redirected to a file) the screen is simply not cleared
        if self.ansi:
            self._output.write("\x1b[2J\x1b[H")
            self._output.flush()

    def title(self, text: str, right: str = "") -> None:
        width = max(60, visible_len(text) + visible_len(right) + 6)
        self.print(self.cyan("═" * width))
        gap = width - visible_len(text) - visible_len(right) - 2
        self.print(" " + self.bold(text) + " " * max(gap, 1) + self.dim(right))
        self.print(self.cyan("═" * width))

    def section(self, text: str) -> None:
        self.print("")
        self.print(self.bold(text))
        self.print(self.dim("─" * max(40, len(text))))

    def info(self, text: str) -> None:
        self.print(self.cyan(text))

    def success(self, text: str) -> None:
        self.print(self.green(text))

    def warning(self, text: str) -> None:
        self.print(self.yellow(text))

    def error(self, text: str) -> None:
        self.print(self.red(text))

    def table(self, headers, rows, align=None) -> None:
        """Prints a simple table. Cells may already contain colors; widths ignore them."""
        align = align or ["<"] * len(headers)
        widths = [visible_len(header) for header in headers]
        for row in rows:
            for index, cell in enumerate(row):
                widths[index] = max(widths[index], visible_len(cell))

        def format_row(cells):
            parts = []
            for index, cell in enumerate(cells):
                padding = " " * (widths[index] - visible_len(cell))
                parts.append(padding + cell if align[index] == ">" else cell + padding)
            return " " + "  ".join(parts).rstrip()

        self.print(self.dim(format_row(headers)))
        for row in rows:
            self.print(format_row(row))

    def menu(self, entries, columns: int = 2) -> None:
        """Prints menu entries (key, description) in columns."""
        key_width = max((len(key) for key, _ in entries), default=0)
        cells = [f"{self.bold(self.yellow(key.rjust(key_width)))}  {description}" for key, description in entries]
        width = max((visible_len(cell) for cell in cells), default=0) + 3
        for start in range(0, len(cells), columns):
            line = ""
            for cell in cells[start:start + columns]:
                line += cell + " " * (width - visible_len(cell))
            self.print(" " + line.rstrip())

    # --- input ------------------------------------------------------------------

    def ask(self, prompt: str) -> str:
        """Reads one line. EOF (closed input) behaves like Ctrl+C, so the program ends cleanly."""
        try:
            return self._input(self.bold(prompt) + " ").strip()
        except EOFError:
            raise KeyboardInterrupt

    def confirm(self, prompt: str, default: bool = False) -> bool:
        hint = "[A/n]" if default else "[a/N]"
        answer = self.ask(f"{prompt} {hint}").lower()
        if not answer:
            return default
        return answer in ("a", "ano", "y", "yes")

    def pause(self) -> None:
        self.ask(self.dim("Pokračuj klávesou Enter…"))
