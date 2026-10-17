"""Tests for voice-alerts: python -m unittest discover tests

They never speak and never touch your real agent configs: settings and installs go to
temporary folders.
"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "voice_alerts.py")


def slurp(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load(home):
    os.environ["VOICE_ALERTS_HOME"] = os.path.join(home, ".voice-alerts")
    spec = importlib.util.spec_from_file_location("voice_alerts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="va-test-")
        self.va = load(self.home)
        self.cfg = self.va.config()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def kind_and_need(self, agent, payload):
        event = self.va.ADAPTERS[agent](payload)
        if event is None:
            return None, None
        event = self.va.compact({"_agent": agent, **event})
        kind = self.va.classify(event, {}, self.cfg)
        return kind, self.va.describe_need(event, kind) if kind else None


class Adapters(Base):
    def test_claude_permission_uses_description(self):
        kind, need = self.kind_and_need("claude", {
            "hook_event_name": "PermissionRequest", "session_id": "s", "tool_name": "Bash",
            "tool_input": {"command": "npm test", "description": "Run the test suite"}})
        self.assertEqual((kind, need), ("permission", "run the test suite"))

    def test_claude_question_reads_the_question(self):
        kind, need = self.kind_and_need("claude", {
            "hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
            "tool_input": {"questions": [{"question": "Which deploy target?"}]}})
        self.assertEqual((kind, need), ("question", "Which deploy target?"))

    def test_cursor_payload_through_claude_hooks(self):
        event = self.va.ADAPTERS["claude"]({"hook_event_name": "stop", "status": "completed",
                                            "conversation_id": "c1", "cursor_version": "2.5",
                                            "workspace_roots": ["/Users/sam/app"]})
        self.assertEqual((event["hook_event_name"], event["_agent"], event["session_id"]), ("Stop", "cursor", "c1"))

    def test_codex_shell_argv(self):
        kind, need = self.kind_and_need("codex", {
            "hook_event_name": "PermissionRequest", "session_id": "s", "tool_name": "Bash",
            "tool_input": {"command": ["bash", "-lc", "npm install"], "description": "Allow install?"}})
        self.assertEqual((kind, need), ("permission", "run npm install"))

    def test_codex_apply_patch(self):
        kind, need = self.kind_and_need("codex", {
            "hook_event_name": "PermissionRequest", "tool_name": "apply_patch",
            "tool_input": {"command": "*** Begin Patch\n*** Update File: src/app.py\n@@"}})
        self.assertEqual((kind, need), ("permission", "edit app.py"))

    def test_codex_question(self):
        kind, need = self.kind_and_need("codex", {
            "hook_event_name": "PreToolUse", "tool_name": "request_user_input",
            "tool_input": {"questions": [{"id": "q", "question": "Ship it now?"}]}})
        self.assertEqual((kind, need), ("question", "Ship it now?"))

    def test_gemini_exec_permission(self):
        kind, need = self.kind_and_need("gemini", {
            "hook_event_name": "Notification", "notification_type": "ToolPermission",
            "message": "Tool Shell requires execution",
            "details": {"type": "exec", "title": "Shell", "command": "git push", "rootCommand": "git"}})
        self.assertEqual((kind, need), ("permission", "run git push"))

    def test_gemini_edit_and_plan(self):
        self.assertEqual(self.kind_and_need("gemini", {
            "hook_event_name": "Notification", "notification_type": "ToolPermission",
            "details": {"type": "edit", "filePath": "/w/app/main.go", "newContent": "x" * 9000}}),
            ("permission", "edit main.go"))
        self.assertEqual(self.kind_and_need("gemini", {
            "hook_event_name": "Notification", "notification_type": "ToolPermission",
            "details": {"type": "exit_plan_mode", "title": "Plan Approval"}})[0], "plan")

    def test_gemini_turn_events(self):
        self.assertEqual(self.va.ADAPTERS["gemini"]({"hook_event_name": "BeforeAgent"})["hook_event_name"],
                         "UserPromptSubmit")
        self.assertEqual(self.va.ADAPTERS["gemini"]({"hook_event_name": "AfterAgent"})["hook_event_name"], "Stop")

    def test_copilot_notification(self):
        kind, need = self.kind_and_need("copilot", {
            "hook_event_name": "Notification", "notification_type": "permission_prompt",
            "sessionId": "s1", "message": "The agent requests permission to execute a tool"})
        self.assertEqual((kind, need), ("permission", ""))

    def test_opencode_permission_and_plan(self):
        self.assertEqual(self.kind_and_need("opencode", {
            "hook_event_name": "PermissionRequest", "session_id": "s", "tool_name": "bash",
            "tool_input": {"command": "rm -rf build", "description": "Clean the build folder"}}),
            ("permission", "clean the build folder"))
        self.assertEqual(self.kind_and_need("opencode", {
            "hook_event_name": "Question", "questions": [{"header": "Build Agent", "question": "Switch?"}]})[0],
            "plan")

    def test_aider_is_your_turn(self):
        self.assertEqual(self.kind_and_need("aider", {})[0], "idle")

    def test_unknown_events_are_ignored(self):
        self.assertIsNone(self.va.ADAPTERS["cursor"]({"hook_event_name": "afterFileEdit"}))
        self.assertIsNone(self.va.ADAPTERS["gemini"]({"hook_event_name": "BeforeModel"}))


class Lines(Base):
    def test_every_persona_has_every_kind(self):
        for name, persona in self.va.load_personas().items():
            for kind in self.va.KINDS:
                _, text = self.va.make_line(persona, kind, "my app", self.cfg, need="run the tests", agent="Codex")
                self.assertNotIn("{", text, f"{name}/{kind}: {text}")

    def test_project_names(self):
        self.assertEqual(self.va.project_name("C:\\work\\checkout_service", self.cfg), "checkout service")
        self.assertEqual(self.va.project_name("/r/api/.claude/worktrees/feat-x", self.cfg), "api")


class Installers(Base):
    def read(self, *parts):
        with open(os.path.join(self.home, *parts), encoding="utf-8") as f:
            return f.read()

    def test_install_keeps_existing_hooks_and_is_repeatable(self):
        os.makedirs(os.path.join(self.home, ".codex"))
        other = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "my-own-hook"}]}]}}
        with open(os.path.join(self.home, ".codex", "hooks.json"), "w") as f:
            json.dump(other, f)
        for _ in range(2):
            self.va.install_codex(self.home)
        data = json.loads(self.read(".codex", "hooks.json"))
        stop = json.dumps(data["hooks"]["Stop"])
        self.assertIn("my-own-hook", stop)
        self.assertEqual(stop.count("voice_alerts.py"), 1)
        self.va.install_codex(self.home, remove=True)
        data = json.loads(self.read(".codex", "hooks.json"))
        self.assertNotIn("voice_alerts.py", json.dumps(data))
        self.assertIn("my-own-hook", json.dumps(data))

    def test_every_installer_round_trips(self):
        for agent, install in self.va.INSTALLERS.items():
            if agent == "claude":
                continue
            path, _ = install(self.home)
            self.assertIn("voice_alerts.py", slurp(path), agent)
            install(self.home, remove=True)
            if os.path.exists(path):
                self.assertNotIn("voice_alerts.py", slurp(path), agent)

    def test_opencode_plugin_paths_are_filled_in(self):
        path, _ = self.va.install_opencode(self.home)
        code = slurp(path)
        self.assertNotIn("__PYTHON__", code)
        self.assertNotIn("__SCRIPT__", code)

    def test_gemini_keeps_other_settings(self):
        os.makedirs(os.path.join(self.home, ".gemini"))
        with open(os.path.join(self.home, ".gemini", "settings.json"), "w") as f:
            json.dump({"theme": "Dracula"}, f)
        self.va.install_gemini(self.home)
        data = json.loads(self.read(".gemini", "settings.json"))
        self.assertEqual(data["theme"], "Dracula")
        self.assertEqual(set(data["hooks"]), {"BeforeAgent", "AfterAgent", "Notification", "BeforeTool"})


if __name__ == "__main__":
    unittest.main()
