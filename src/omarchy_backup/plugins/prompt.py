"""Interactive prompt handler for confirming plugin installations one by one."""

from __future__ import annotations

import os
import sys
from typing import Callable


class PluginPromptHandler:
    """Manages one-by-one user confirmation for plugin installation during restore.

    Options:
      - y / yes / [Enter]: Confirm installing this plugin
      - n / no: Skip this plugin
      - a / all: Confirm installing this and all subsequent plugins without asking again
      - s / skip: Skip this and all subsequent plugins without asking again
    """

    def __init__(
        self,
        auto_confirm: bool = False,
        prompt_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.auto_confirm = auto_confirm
        self.skip_all = False
        self.prompt_fn = prompt_fn

    def should_install(
        self,
        plugin_type: str,
        plugin_name: str,
        repository: str = "",
    ) -> bool:
        """Ask whether to install a plugin.

        Returns True to proceed with installation, or False to skip.
        """
        if self.skip_all:
            return False
        if self.auto_confirm:
            return True

        use_color = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
        bold_start = "\033[1m" if use_color else ""
        cyan_start = "\033[36m" if use_color else ""
        reset = "\033[0m" if use_color else ""
        dim_start = "\033[2m" if use_color else ""

        prompt_str = f"\n{bold_start}Install {plugin_type} plugin {cyan_start}'{plugin_name}'{reset}"
        if repository:
            prompt_str += f" {dim_start}({repository}){reset}"
        prompt_str += f"{bold_start}? [y/n/a/s]{reset} (default: y): "

        ask = self.prompt_fn if self.prompt_fn is not None else input

        while True:
            try:
                ans = ask(prompt_str).strip().lower()
            except (EOFError, KeyboardInterrupt):
                self.skip_all = True
                return False

            if ans in ("", "y", "yes"):
                return True
            if ans in ("n", "no"):
                return False
            if ans in ("a", "all"):
                self.auto_confirm = True
                return True
            if ans in ("s", "skip"):
                self.skip_all = True
                return False

            print("Please enter 'y' (yes), 'n' (no), 'a' (all), or 's' (skip remaining).")
