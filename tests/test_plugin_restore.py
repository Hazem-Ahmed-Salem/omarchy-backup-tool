"""Tests for one-by-one plugin restoration and interactive prompt confirmation."""

import json
import tempfile
import unittest
from pathlib import Path

from omarchy_backup.paths import AppPaths
from omarchy_backup.plugins.hyprpm import restore_hyprpm_plugins
from omarchy_backup.plugins.omarchy import restore_omarchy_plugins
from omarchy_backup.plugins.prompt import PluginPromptHandler
from omarchy_backup.restore.executor import RestoreEngine
from omarchy_backup.runner import CommandResult, CommandRunner


class MockRunner(CommandRunner):
    def __init__(self) -> None:
        super().__init__()
        self.executed_commands: list[list[str]] = []

    def run(self, cmd, cwd=None, timeout=None, env=None, capture_output=True, stdin_null=True):
        cmd_list = [str(c) for c in cmd]
        self.executed_commands.append(cmd_list)

        if cmd_list[:3] == ["omarchy", "plugin", "list"]:
            return CommandResult(cmd_list, 0, "[]\n", "")
        if cmd_list[:2] == ["hyprpm", "list"]:
            return CommandResult(cmd_list, 0, "hyprpm v0.1\n", "")
        return CommandResult(cmd_list, 0, "ok\n", "")


class TestPluginPromptHandler(unittest.TestCase):
    def test_auto_confirm_true(self):
        handler = PluginPromptHandler(auto_confirm=True)
        self.assertTrue(handler.should_install("Omarchy", "test-plugin", "https://github.com/test/plugin"))
        self.assertTrue(handler.should_install("Hyprland", "test-hypr", "https://github.com/test/hypr"))

    def test_confirm_yes_and_no(self):
        responses = iter(["y", "n", ""])
        handler = PluginPromptHandler(auto_confirm=False, prompt_fn=lambda _: next(responses))

        # First plugin: 'y' -> True
        self.assertTrue(handler.should_install("Omarchy", "plugin1", "https://repo1"))
        # Second plugin: 'n' -> False
        self.assertFalse(handler.should_install("Omarchy", "plugin2", "https://repo2"))
        # Third plugin: '' (default Enter) -> True
        self.assertTrue(handler.should_install("Omarchy", "plugin3", "https://repo3"))

    def test_confirm_all(self):
        responses = iter(["a"])
        handler = PluginPromptHandler(auto_confirm=False, prompt_fn=lambda _: next(responses))

        # First plugin: 'a' -> True, sets auto_confirm=True
        self.assertTrue(handler.should_install("Omarchy", "plugin1", "https://repo1"))
        self.assertTrue(handler.auto_confirm)

        # Subsequent plugins must not call prompt_fn
        self.assertTrue(handler.should_install("Omarchy", "plugin2", "https://repo2"))
        self.assertTrue(handler.should_install("Hyprland", "plugin3", "https://repo3"))

    def test_skip_all(self):
        responses = iter(["s"])
        handler = PluginPromptHandler(auto_confirm=False, prompt_fn=lambda _: next(responses))

        # First plugin: 's' -> False, sets skip_all=True
        self.assertFalse(handler.should_install("Omarchy", "plugin1", "https://repo1"))
        self.assertTrue(handler.skip_all)

        # Subsequent plugins must not call prompt_fn and return False
        self.assertFalse(handler.should_install("Omarchy", "plugin2", "https://repo2"))
        self.assertFalse(handler.should_install("Hyprland", "plugin3", "https://repo3"))

    def test_invalid_input_retry(self):
        responses = iter(["maybe", "invalid", "yes"])
        handler = PluginPromptHandler(auto_confirm=False, prompt_fn=lambda _: next(responses))
        self.assertTrue(handler.should_install("Omarchy", "plugin1", "https://repo1"))

    def test_eof_handling(self):
        def raise_eof(_):
            raise EOFError()

        handler = PluginPromptHandler(auto_confirm=False, prompt_fn=raise_eof)
        self.assertFalse(handler.should_install("Omarchy", "plugin1", "https://repo1"))
        self.assertTrue(handler.skip_all)


class TestPluginRestorationWorkflows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.paths = AppPaths(home=self.home)
        self.runner = MockRunner()

    def tearDown(self):
        self.tmp.cleanup()

    def test_restore_omarchy_plugins_one_by_one_prompt(self):
        plugins = [
            {"id": "plugin-one", "repository": "https://github.com/user/one.git", "enabled": True},
            {"id": "plugin-two", "repository": "https://github.com/user/two.git", "enabled": True},
        ]

        # User confirms first, rejects second
        responses = iter(["y", "n"])
        prompt_handler = PluginPromptHandler(auto_confirm=False, prompt_fn=lambda _: next(responses))

        actions, warnings = restore_omarchy_plugins(
            recorded_plugins=plugins,
            paths=self.paths,
            runner=self.runner,
            auto_confirm=False,
            prompt_handler=prompt_handler,
        )

        self.assertEqual(len(warnings), 0)
        self.assertIn("Installed plugin plugin-one", actions)
        self.assertIn("Skipped Omarchy plugin plugin-two (user opted not to install)", actions)

        # Check executed commands: only plugin-one was installed
        added = [c for c in self.runner.executed_commands if c[:3] == ["omarchy", "plugin", "add"]]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0][3], "https://github.com/user/one.git")

    def test_restore_hyprpm_plugins_one_by_one_prompt(self):
        plugins = [
            {"name": "hyprbars", "repository": "https://github.com/hyprwm/hyprland-plugins", "enabled": True},
            {"name": "hyprexpo", "repository": "https://github.com/hyprwm/hyprexpo", "enabled": True},
        ]

        # User chooses 'a' (all) on the first one
        responses = iter(["a"])
        prompt_handler = PluginPromptHandler(auto_confirm=False, prompt_fn=lambda _: next(responses))

        actions, warnings = restore_hyprpm_plugins(
            recorded_plugins=plugins,
            runner=self.runner,
            auto_confirm=False,
            prompt_handler=prompt_handler,
        )

        self.assertEqual(len(warnings), 0)
        configured = [a for a in actions if "Configured hyprpm plugin" in a]
        self.assertEqual(len(configured), 2)

    def test_restore_engine_with_plugins_one_by_one(self):
        backup_dir = Path(self.tmp.name) / "backup"
        backup_dir.mkdir()
        (backup_dir / "manifest.json").write_text('{"entries": []}')

        plugins_dir = backup_dir / "plugins"
        plugins_dir.mkdir()
        omarchy_plugins = [
            {"id": "plugin-alpha", "repository": "https://github.com/user/alpha.git", "enabled": True},
            {"id": "plugin-beta", "repository": "https://github.com/user/beta.git", "enabled": True},
        ]
        (plugins_dir / "omarchy-shell.json").write_text(json.dumps(omarchy_plugins))

        responses = iter(["n", "y"])
        engine = RestoreEngine(paths=self.paths, runner=self.runner)
        result = engine.execute(
            backup_dir=backup_dir,
            auto_confirm=False,
            skip_service_reload=True,
            prompt_fn=lambda _: next(responses),
        )

        self.assertTrue(result.success)
        self.assertIn("Skipped Omarchy plugin plugin-alpha (user opted not to install)", result.plugin_actions)
        self.assertIn("Installed plugin plugin-beta", result.plugin_actions)


if __name__ == "__main__":
    unittest.main()
