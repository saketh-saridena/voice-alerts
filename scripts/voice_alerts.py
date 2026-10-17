#!/usr/bin/env python3
"""voice-alerts: says a line out loud when your coding agent needs you.

Claude Code runs it from the plugin's hooks (hooks/hooks.json). Other agents get hooks
from `install`, which points them at a copy of this script in ~/.voice-alerts/app:
  voice_alerts.py hook --agent NAME        one hook event: JSON on stdin (or as an argument)
  voice_alerts.py welcome                  Claude Code, first session only: hello + pointer to setup
  voice_alerts.py install AGENT...         codex gemini copilot cursor opencode aider, or all
  voice_alerts.py uninstall AGENT...
  voice_alerts.py agents                   which coding agents are on this machine

By hand, or through the /voice-alerts skill:
  voice_alerts.py voices                   the voices available on this machine, for setup
  voice_alerts.py test [KIND]              say a line with your current settings
  voice_alerts.py say KIND [options]       KIND: permission question plan idle done nag nag2
  voice_alerts.py persona NAME[,NAME]      friend, butler, commentator, intern, trailer (several rotate)
  voice_alerts.py voice NAME[,NAME]        a neural voice such as en-US-AvaNeural (several rotate;
                                           needs edge-tts), or a local voice: auto (each persona's
                                           own), or a name like Zira (Windows) or Samantha (macOS)
  voice_alerts.py mute [MINUTES]           stay quiet for MINUTES, or until unmute
  voice_alerts.py unmute
  voice_alerts.py status                   settings, mute state, who holds the microphone

Settings for every agent live in ~/.voice-alerts/ (or $VOICE_ALERTS_HOME): config.json, plus
personas.json once you customize the lines. The personas.json next to this script is the
default. Everything it decides is logged to state/events.log there.
"""
import argparse
import base64
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
DATA = os.environ.get("VOICE_ALERTS_HOME") or os.path.join(HOME, ".voice-alerts")
CONFIG = os.path.join(DATA, "config.json")
BUNDLED_PERSONAS = os.path.join(HERE, "personas.json")
USER_PERSONAS = os.path.join(DATA, "personas.json")
STATE = os.path.join(DATA, "state")
SESSIONS = os.path.join(STATE, "sessions")
LOG = os.path.join(STATE, "events.log")
MUTE = os.path.join(STATE, "mute.json")
LOCK = os.path.join(STATE, "speak.lock")
DECIDE_LOCK = os.path.join(STATE, "decide.lock")
APP = os.path.join(DATA, "app")  # where `install` puts the runtime other agents call

WINDOWS = os.name == "nt"
MAC = sys.platform == "darwin"
NO_WINDOW = 0x08000000 if WINDOWS else 0
DETACHED = 0x00000008
NEW_GROUP = 0x00000200
BREAKAWAY = 0x01000000

KINDS = ("permission", "question", "plan", "idle", "done", "nag", "nag2", "welcome")
BLOCKERS = {"permission", "question", "plan"}

DEFAULTS = {
    "enabled": True,
    "engine": "local",
    "personas": ["friend"],
    "voice": "auto",
    "volume": 100,
    "done_after_seconds": 180,
    "remind_after_minutes": [3, 10],
    "debounce_seconds": 10,
    "skip_during_calls": True,
    "ignore_mic_apps": [],
    "quiet_hours": None,
    "late_after_hour": 20,
    "aliases": {},
}

# SAPI can reach both the classic desktop voices and the newer OneCore ones
# (Mark lives only in OneCore). Text arrives as SAPI XML in VA_TEXT.
PS_SPEAK = r"""
$ErrorActionPreference = 'Stop'
$v = New-Object -ComObject SAPI.SpVoice
$want = $env:VA_VOICE
if ($want) {
  $cat = New-Object -ComObject SAPI.SpObjectTokenCategory
  $cat.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices', $false)
  $pick = $null
  foreach ($t in $v.GetVoices()) { if (-not $pick -and $t.GetDescription() -like "*$want*") { $pick = $t } }
  foreach ($t in $cat.EnumerateTokens()) { if (-not $pick -and $t.GetDescription() -like "*$want*") { $pick = $t } }
  if ($pick) { $v.Voice = $pick }
}
$v.Volume = [int]$env:VA_VOLUME
$out = $null
if ($env:VA_WAV) {
  $out = New-Object -ComObject SAPI.SpFileStream
  $out.Format.Type = 22
  $out.Open($env:VA_WAV, 3, $false)
  $v.AudioOutputStream = $out
}
[void]$v.Speak($env:VA_TEXT, 8)
if ($out) { $out.Close() }
"""


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def config():
    cfg = dict(DEFAULTS)
    cfg.update(load_json(CONFIG, {}))
    return cfg


def load_personas():
    """Your customized personas.json wins over the one bundled with the plugin."""
    return load_json(USER_PERSONAS, None) or load_json(BUNDLED_PERSONAS, {})


def log(msg):
    try:
        os.makedirs(STATE, exist_ok=True)
        if os.path.exists(LOG) and os.path.getsize(LOG) > 200_000:
            with open(LOG, encoding="utf-8", errors="replace") as f:
                keep = f.readlines()[-500:]
            with open(LOG, "w", encoding="utf-8") as f:
                f.writelines(keep)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except OSError:
        pass


def session_path(sid):
    safe = "".join(c for c in sid if c.isalnum() or c in "-_") or "unknown"
    return os.path.join(SESSIONS, safe + ".json")


def load_session(sid):
    return load_json(session_path(sid), {})


def save_session(sid, st):
    save_json(session_path(sid), st)


def prune_sessions():
    try:
        cutoff = time.time() - 3 * 86400
        for name in os.listdir(SESSIONS):
            p = os.path.join(SESSIONS, name)
            if os.path.getmtime(p) < cutoff:
                os.remove(p)
    except OSError:
        pass


def update_session(sid, **fields):
    """Change a few fields without overwriting what another hook wrote meanwhile."""
    with FileLock(DECIDE_LOCK, wait=10):
        st = load_session(sid)
        st.update(fields)
        save_session(sid, st)


class FileLock:
    """A lock shared by every voice-alerts process on this machine."""

    def __init__(self, path=LOCK, wait=90):
        self.path, self.wait = path, wait

    def __enter__(self):
        os.makedirs(STATE, exist_ok=True)
        self.f = open(self.path, "a+")
        self.held = False
        deadline = time.time() + self.wait
        while time.time() < deadline:
            try:
                self._lock(True)
                self.held = True
                return self
            except OSError:
                time.sleep(0.5)
        return self

    def __exit__(self, *exc):
        if self.held:
            try:
                self._lock(False)
            except OSError:
                pass
        self.f.close()

    def _lock(self, take):
        if WINDOWS:
            import msvcrt

            self.f.seek(0)
            msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK if take else msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.f.fileno(), (fcntl.LOCK_EX | fcntl.LOCK_NB) if take else fcntl.LOCK_UN)


def speak(text, persona, cfg, out=None, voice=None):
    """Say text aloud, or save it to `out` (.mp3 for neural voices).

    Returns the path written, if any."""
    neural = bool(voice) and "Neural" in voice
    if neural or (cfg.get("engine") == "neural" and not voice):
        try:
            return speak_neural(text, persona, cfg, out, voice)
        except Exception as e:
            log(f"  neural voice failed, using the local voice: {e!r}")
    return speak_local(text, persona, cfg, out, None if neural else voice)


def neural_voice(persona):
    v = persona.get("neural_voice") or "en-US-AvaNeural"
    return random.choice(v) if isinstance(v, list) else v


def speak_neural(text, persona, cfg, out=None, voice=None):
    """Microsoft's online neural voices, through edge-tts (pip install edge-tts)."""
    import asyncio

    import edge_tts

    voice = voice or neural_voice(persona)
    os.makedirs(STATE, exist_ok=True)
    mp3 = os.path.join(STATE, f"say-{uuid.uuid4().hex[:8]}.mp3")
    talk = edge_tts.Communicate(text, voice, rate=persona.get("neural_rate", "+0%"),
                                pitch=persona.get("neural_pitch", "+0Hz"))
    try:
        # Live lines give up fast and fall back to the local voice; saved files can wait.
        asyncio.run(asyncio.wait_for(talk.save(mp3), timeout=40 if out else 8))
        if out:
            out = os.path.splitext(os.path.abspath(out))[0] + ".mp3"
            os.replace(mp3, out)
            return out
        with FileLock():
            play_mp3(mp3, cfg["volume"])
    finally:
        try:
            os.remove(mp3)
        except OSError:
            pass


def play_mp3(path, volume):
    """Play an MP3 and block until it ends."""
    if WINDOWS:
        return play_mp3_windows(path, volume)
    if MAC:
        subprocess.run(["afplay", "-v", f"{int(volume) / 100:.2f}", path], check=True)
        return
    for cmd in (["mpg123", "-q", path], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                ["mpv", "--no-video", "--really-quiet", path]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=True)
            return
    raise RuntimeError("no MP3 player found (install mpg123, ffmpeg or mpv)")


def play_mp3_windows(path, volume):
    """The Windows multimedia API (winmm): no PowerShell, so it starts fast."""
    import ctypes

    mci = ctypes.windll.winmm.mciSendStringW
    alias = "valert" + uuid.uuid4().hex[:6]

    def send(cmd):
        err = mci(cmd, None, 0, None)
        if err:
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(err, buf, 256)
            raise RuntimeError(f"{cmd.split()[0]}: {buf.value}")

    send(f'open "{path}" type mpegvideo alias {alias}')
    try:
        send(f"setaudio {alias} volume to {int(volume) * 10}")
        send(f"play {alias} wait")
    finally:
        mci(f"close {alias}", None, 0, None)


def speak_local(text, persona, cfg, out=None, voice=None):
    """The voices that ship with the operating system, offline."""
    try:
        if WINDOWS:
            return speak_sapi(text, persona, cfg, out, voice)
        if MAC:
            return speak_mac(text, persona, cfg, out, voice)
        return speak_linux(text, persona, cfg, out)
    except Exception as e:
        log(f"  speech failed: {e}")
        return None


def speak_sapi(text, persona, cfg, out=None, voice=None):
    voice = voice or (persona.get("voice", "") if cfg["voice"] == "auto" else cfg["voice"])
    xml = '<rate absspeed="{}"><pitch absmiddle="{}">{}</pitch></rate>'.format(
        int(persona.get("rate", 0)), int(persona.get("pitch", 0)),
        # escaped by hand: xml.sax.saxutils would pull in urllib and add most of a second to every hook
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    env = dict(os.environ, VA_TEXT=xml, VA_VOICE=voice, VA_VOLUME=str(int(cfg["volume"])))
    env.pop("VA_WAV", None)
    if out:
        # SAPI cannot open long paths, so render into the state folder and move it.
        env["VA_WAV"] = os.path.join(STATE, "render.wav")
        os.makedirs(STATE, exist_ok=True)
    encoded = base64.b64encode(PS_SPEAK.encode("utf-16-le")).decode()
    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    with FileLock():
        r = subprocess.run(cmd, env=env, capture_output=True, timeout=90, creationflags=NO_WINDOW)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace").strip()[-300:])
    if out:
        out = os.path.splitext(os.path.abspath(out))[0] + ".wav"
        os.replace(env["VA_WAV"], out)
        return out


def speak_mac(text, persona, cfg, out=None, voice=None):
    voice = voice or (persona.get("mac_voice", "") if cfg["voice"] == "auto" else cfg["voice"])
    wpm = 185 + 15 * int(persona.get("rate", 0))
    spoken = f"[[volm {int(cfg['volume']) / 100:.2f}]] {text}"
    target = os.path.splitext(os.path.abspath(out))[0] + ".aiff" if out else None
    for v in ([voice] if voice else []) + [None]:  # an uninstalled voice falls back to the default
        cmd = ["say", "-r", str(wpm)] + (["-v", v] if v else []) + (["-o", target] if target else [])
        with FileLock():
            r = subprocess.run(cmd + [spoken], capture_output=True)
        if r.returncode == 0:
            return target
    raise RuntimeError(r.stderr.decode(errors="replace").strip()[-300:])


def speak_linux(text, persona, cfg, out=None):
    target = os.path.splitext(os.path.abspath(out))[0] + ".wav" if out else None
    if shutil.which("espeak"):
        cmd = ["espeak", "-a", str(int(cfg["volume"]) * 2)] + (["-w", target] if target else []) + [text]
    elif shutil.which("spd-say") and not target:
        cmd = ["spd-say", "-w", text]
    else:
        raise RuntimeError("no speech program found (install espeak or speech-dispatcher)")
    with FileLock():
        subprocess.run(cmd, check=True, capture_output=True)
    return target


def choose_persona(cfg, personas):
    names = [n for n in cfg["personas"] if n in personas] or list(personas)[:1]
    name = random.choice(names)
    return name, personas[name]


def make_line(persona, kind, project, cfg, need="", avoid=None, agent="your agent"):
    lines = persona["lines"]
    pool = lines.get(kind) or lines["permission"]
    # Lines with {need} say what the session wants; use them whenever we know.
    with_need = [t for t in pool if "{need}" in t]
    plain = [t for t in pool if "{need}" not in t]
    pool = with_need if need and with_need else (plain or pool)
    template = random.choice([t for t in pool if t != avoid] or pool)
    text = template.replace("{project}", project).replace("{need}", need).replace("{agent}", agent)
    text = text.replace("?.", "?").replace("!.", "!").replace("..", ".")
    hour = datetime.now().hour
    late = hour >= cfg["late_after_hour"] or hour < 5
    if late and kind != "done" and lines.get("late") and random.random() < 0.5:
        text += " " + random.choice(lines["late"])
    return template, text


def project_name(cwd, cfg):
    path = (cwd or "").replace("\\", "/").rstrip("/")
    low = path.lower()
    marker = "/.claude/worktrees/"
    if marker in low:
        path = path[: low.index(marker)]
    aliases = {k.lower(): v for k, v in cfg["aliases"].items()}
    if "scratch-workspaces" in low:
        return aliases.get("scratch", "your scratch session")
    name = path.split("/")[-1] or "your session"
    if name.lower() in aliases:
        return aliases[name.lower()]
    return spoken_words(name)


def shorten(text, words=22):
    parts = " ".join(str(text).split()).split(" ")
    return " ".join(parts[:words]) + (" ..." if len(parts) > words else "")


def spoken_words(name):
    return " ".join(name.replace("_", " ").replace("-", " ").split())


def lower_first(text):
    text = text.strip().rstrip(".")
    if len(text) > 1 and text[1].isupper():
        return text  # an acronym like "SAP" or "API"
    return text[:1].lower() + text[1:]


def describe_tool(tool, ti):
    """A short spoken phrase for what a tool call wants to do: '... needs your okay to <phrase>'."""
    desc = ti.get("description") if isinstance(ti, dict) else None
    ti = ti if isinstance(ti, dict) else {}

    def file_of(key="file_path"):
        p = str(ti.get(key) or ti.get("notebook_path") or "").replace("\\", "/")
        return p.rstrip("/").split("/")[-1] or "a file"

    if tool.lower() in ("bash", "powershell", "shell", "run_shell_command"):
        if desc:
            return shorten(lower_first(desc), 14)
        cmd = str(ti.get("command", ""))
        # "bash -lc 'npm test'" and friends: say the inner command
        inner = re.match(r"^\s*(?:\S*[/\\])?(?:bash|sh|zsh|pwsh|powershell)(?:\.exe)?\s+(?:-lc|-c|-Command)\s+(.+)$", cmd, re.I)
        if inner:
            cmd = inner.group(1).strip().strip("\"'")
        words = [w for w in cmd.split() if not w.startswith("-")][:3]
        return "run " + (" ".join(w.strip("\"'").replace("\\", "/").split("/")[-1] for w in words) or "a command")
    if tool in ("Edit", "MultiEdit"):
        return "edit " + file_of()
    if tool == "Write":
        return "write " + file_of()
    if tool == "NotebookEdit":
        return "edit the notebook " + file_of()
    if tool == "Read":
        return "read " + file_of()
    if tool == "WebFetch":
        from urllib.parse import urlparse
        host = urlparse(str(ti.get("url", ""))).hostname or "the web"
        return "open a page on " + (host[4:] if host.startswith("www.") else host)
    if tool == "WebSearch":
        return "search the web for " + shorten(ti.get("query", "something"), 10)
    if tool in ("Agent", "Task"):
        return "send a helper agent to " + shorten(lower_first(desc), 10) if desc else "start a helper agent"
    if tool == "Skill":
        return "use the " + spoken_words(str(ti.get("skill", "")).split(":")[-1]) + " skill"
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        server, action = (parts[1] if len(parts) > 2 else ""), parts[-1]
        looks_like_id = sum(c.isdigit() for c in server) > 6
        where = "" if not server or looks_like_id else " in " + spoken_words(server)
        return "use " + spoken_words(action) + where
    return "use " + spoken_words(tool) if tool else ""


def describe_need(data, kind):
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    if kind == "question":
        if tool == "AskUserQuestion" and isinstance(ti, dict):
            qs = ti.get("questions") or []
            if qs and isinstance(qs[0], dict):
                return shorten(qs[0].get("question", ""), 25)
        if data.get("hook_event_name") == "Notification":
            return shorten(data.get("message") or "", 25)
        return ""
    if kind != "permission":
        return ""
    if tool:
        return describe_tool(tool, ti)
    msg = data.get("message") or ""
    marker = "permission to use "
    if marker in msg:
        return "use " + spoken_words(msg.split(marker, 1)[1].strip(" ."))
    return ""


def mic_users(cfg):
    """Apps holding the microphone right now (a call, a meeting, dictation). Windows only."""
    if not WINDOWS:
        return []
    import winreg

    base = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
    found = []

    def scan(path):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            return
        with key:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                if name == "NonPackaged":
                    scan(path + "\\NonPackaged")
                    continue
                try:
                    with winreg.OpenKey(key, name) as sub:
                        start = winreg.QueryValueEx(sub, "LastUsedTimeStart")[0]
                        stop = winreg.QueryValueEx(sub, "LastUsedTimeStop")[0]
                except OSError:
                    continue
                if start and stop == 0:
                    found.append(name)

    scan(base)
    ignore = [x.lower() for x in cfg["ignore_mic_apps"]]
    return [n for n in found if not any(x in n.lower() for x in ignore)]


def muted():
    m = load_json(MUTE, None)
    if not m:
        return False
    until = m.get("until", 0)
    if until == 0 or until > time.time():
        return True
    try:
        os.remove(MUTE)
    except OSError:
        pass
    return False


def in_quiet_hours(cfg):
    q = cfg.get("quiet_hours")
    if not q:
        return False
    start, end = (datetime.strptime(x, "%H:%M").time() for x in q)
    now = datetime.now().time()
    return start <= now < end if start < end else (now >= start or now < end)


def silenced(cfg):
    """Why it must stay quiet right now, or '' if it may talk."""
    if not cfg["enabled"]:
        return "disabled"
    if muted():
        return "muted"
    if in_quiet_hours(cfg):
        return "quiet hours"
    if cfg["skip_during_calls"]:
        users = mic_users(cfg)
        if users:
            return "mic in use by " + ", ".join(users)
    return ""


def announce(kind, project, cfg, avoid=None, need="", agent="your agent"):
    """Pick a line, say it, and return its template so the next one can differ."""
    name, persona = choose_persona(cfg, load_personas())
    template, text = make_line(persona, kind, project, cfg, need=need, avoid=avoid, agent=agent)
    log(f"  say [{name}] {text}")
    speak(text, persona, cfg)
    return template


def spawn_reminder(sid, token):
    spawn_detached("remind", sid, token)


def spawn_detached(*cmd):
    """Run this script again in the background, outliving the hook that started it."""
    args = [sys.executable, os.path.abspath(__file__), *cmd]
    quiet = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if not WINDOWS:
        subprocess.Popen(args, start_new_session=True, **quiet)
        return
    base = DETACHED | NEW_GROUP | NO_WINDOW
    for flags in (base | BREAKAWAY, base):
        try:
            subprocess.Popen(args, creationflags=flags, **quiet)
            return
        except OSError:
            continue


def classify(data, st, cfg):
    event = data.get("hook_event_name", "")
    if event == "Notification":
        nt = data.get("notification_type") or ""
        msg = (data.get("message") or "").lower()
        if nt == "permission_prompt" or (not nt and "permission" in msg):
            return "permission"
        if nt == "idle_prompt" or (not nt and "waiting for your input" in msg):
            return "idle"
        if nt == "elicitation_dialog":
            return "question"
        return None
    if event == "PermissionRequest":
        # The desktop app routes questions and plan reviews through permission requests too.
        return {"AskUserQuestion": "question", "ExitPlanMode": "plan"}.get(data.get("tool_name"), "permission")
    if event == "PreToolUse":
        return {"AskUserQuestion": "question", "ExitPlanMode": "plan"}.get(data.get("tool_name"))
    if event == "Stop":
        start = st.get("turn_start")
        st["turn_start"] = None
        if start and time.time() - start >= cfg["done_after_seconds"]:
            return "done"
    return None


# Each coding agent reports events its own way. An adapter turns one agent's payload
# into the Claude Code shape handle_hook() reads (hook_event_name, session_id, cwd,
# transcript_path, tool_name, tool_input, notification_type, message), or None to ignore it.
def adapt_claude(data):
    if "cursor_version" in data or os.environ.get("CURSOR_VERSION"):
        return adapt_cursor(data)  # Cursor runs Claude Code hooks too, with its own payloads
    return {**data, "session_id": data.get("session_id") or data.get("sessionId")}


def _base(data, agent, **extra):
    return {"session_id": data.get("session_id") or data.get("sessionId"), "cwd": data.get("cwd"),
            "transcript_path": data.get("transcript_path"), "_agent": agent, **extra}


def _question(base, questions=None):
    return {**base, "hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
            "tool_input": {"questions": questions or []}}


def adapt_codex(data):
    base = _base(data, "codex")
    event, tool = data.get("hook_event_name"), data.get("tool_name") or ""
    ti = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    if event in ("UserPromptSubmit", "Stop"):
        return {**base, "hook_event_name": event}
    if event == "PreToolUse" and tool.startswith("request_user_input"):
        return _question(base, ti.get("questions"))
    if event != "PermissionRequest":
        return None
    perm = {**base, "hook_event_name": "PermissionRequest"}
    if tool == "apply_patch":
        files = re.findall(r"\*\*\* (?:Update|Add|Delete) File: (.+)", str(ti.get("command") or ti.get("input") or ""))
        return {**perm, "tool_name": "Edit", "tool_input": {"file_path": files[0].strip() if files else ""}}
    cmd = ti.get("command")
    if isinstance(cmd, list):  # argv form, often ["bash", "-lc", "<script>"]
        cmd = cmd[-1] if len(cmd) >= 3 and cmd[-2] in ("-lc", "-c") else " ".join(map(str, cmd))
    if cmd is not None:
        # Codex's description is an approval reason, not an action, so say the command itself
        return {**perm, "tool_name": "Bash", "tool_input": {"command": str(cmd)}}
    return {**perm, "tool_name": tool, "tool_input": ti}


def adapt_gemini(data):
    base = _base(data, "gemini")
    base["session_id"] = base["session_id"] or os.environ.get("GEMINI_SESSION_ID")
    base["cwd"] = base["cwd"] or os.environ.get("GEMINI_CWD")
    event, tool = data.get("hook_event_name"), data.get("tool_name")
    if event == "BeforeAgent":
        return {**base, "hook_event_name": "UserPromptSubmit"}
    if event == "AfterAgent":
        return {**base, "hook_event_name": "Stop"}
    if event == "BeforeTool" and tool == "ask_user":
        return _question(base, (data.get("tool_input") or {}).get("questions"))
    if event == "BeforeTool" and tool == "exit_plan_mode":
        return {**base, "hook_event_name": "PreToolUse", "tool_name": "ExitPlanMode"}
    if event != "Notification" or data.get("notification_type") != "ToolPermission":
        return None
    d = data.get("details") or {}
    kind = d.get("type")
    if kind == "ask_user":
        return _question(base)
    if kind == "exit_plan_mode":
        return {**base, "hook_event_name": "PreToolUse", "tool_name": "ExitPlanMode"}
    perm = {**base, "hook_event_name": "PermissionRequest", "tool_name": "", "tool_input": {}}
    if kind == "exec":
        return {**perm, "tool_name": "Bash", "tool_input": {"command": d.get("command") or d.get("rootCommand") or ""}}
    if kind == "edit":
        return {**perm, "tool_name": "Edit", "tool_input": {"file_path": d.get("filePath") or d.get("fileName") or ""}}
    if kind == "mcp":
        return {**perm, "tool_name": f"mcp__{d.get('serverName', '')}__{d.get('toolName') or 'tool'}"}
    if kind == "info" and d.get("urls"):
        return {**perm, "tool_name": "WebFetch", "tool_input": {"url": d["urls"][0]}}
    return perm


def adapt_copilot(data):
    base = _base(data, "copilot")
    event = data.get("hook_event_name")
    if event in ("UserPromptSubmit", "Stop"):
        return {**base, "hook_event_name": event}
    if event == "Notification":
        nt = data.get("notification_type")
        if nt == "permission_prompt":  # no tool details here; the line stays general
            return {**base, "hook_event_name": "PermissionRequest", "tool_name": "", "tool_input": {}}
        if nt == "elicitation_dialog":
            return _question(base)
    return None


def adapt_cursor(data):
    roots = data.get("workspace_roots") or []
    base = _base(data, "cursor")
    base["session_id"] = data.get("conversation_id") or base["session_id"]
    base["cwd"] = base["cwd"] or (roots[0] if roots else os.environ.get("CURSOR_PROJECT_DIR"))
    event = data.get("hook_event_name")
    if event in ("beforeSubmitPrompt", "UserPromptSubmit"):
        return {**base, "hook_event_name": "UserPromptSubmit"}
    if event in ("stop", "Stop") and data.get("status", "completed") == "completed":
        return {**base, "hook_event_name": "Stop"}
    return None  # Cursor has no event for "waiting for your approval"


def adapt_opencode(data):
    # The OpenCode plugin (scripts/opencode-plugin.js) already sends Claude-shaped events.
    base = _base(data, "opencode")
    event = data.get("hook_event_name")
    if event in ("UserPromptSubmit", "Stop"):
        return {**base, "hook_event_name": event}
    if event == "Question":
        qs = data.get("questions") or []
        if any(isinstance(q, dict) and q.get("header") == "Build Agent" for q in qs):
            return {**base, "hook_event_name": "PreToolUse", "tool_name": "ExitPlanMode"}
        return _question(base, qs)
    if event != "PermissionRequest":
        return None
    tool = (data.get("tool_name") or "").lower()
    ti = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    perm = {**base, "hook_event_name": "PermissionRequest"}
    if tool in ("bash", "shell") or meta.get("command"):
        return {**perm, "tool_name": "Bash",
                "tool_input": {"command": ti.get("command") or meta.get("command", ""), "description": ti.get("description")}}
    if tool in ("edit", "write", "patch", "apply_patch", "multiedit"):
        return {**perm, "tool_name": "Edit", "tool_input": {"file_path": ti.get("filePath") or meta.get("filepath", "")}}
    if tool == "webfetch":
        return {**perm, "tool_name": "WebFetch", "tool_input": {"url": ti.get("url") or meta.get("url", "")}}
    if tool == "task":
        return {**perm, "tool_name": "Agent", "tool_input": {"description": ti.get("description") or meta.get("description")}}
    if tool in ("read", "external_directory"):
        return {**perm, "tool_name": "Read", "tool_input": {"file_path": ti.get("filePath") or meta.get("filepath", "")}}
    return {**perm, "tool_name": data.get("tool_name") or "", "tool_input": {}}


def adapt_aider(_data):
    # Aider's notifications command gets no payload: it just means "Aider is waiting for you".
    cwd = os.getcwd()
    return {"hook_event_name": "Notification", "notification_type": "idle_prompt", "cwd": cwd,
            "session_id": "aider-" + hashlib.sha1(cwd.encode()).hexdigest()[:12], "_agent": "aider"}


ADAPTERS = {"claude": adapt_claude, "codex": adapt_codex, "gemini": adapt_gemini, "copilot": adapt_copilot,
            "cursor": adapt_cursor, "opencode": adapt_opencode, "aider": adapt_aider}
AGENT_NAMES = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini", "copilot": "Copilot",
               "cursor": "Cursor", "opencode": "OpenCode", "aider": "Aider"}
NO_STDIN = {"aider"}  # Aider passes no payload, and its stdin is your terminal


def compact(event):
    """Only what handle_hook reads, small enough to pass on a command line."""
    keep = ("hook_event_name", "session_id", "cwd", "transcript_path", "tool_name",
            "notification_type", "message", "_agent")
    out = {k: event[k] for k in keep if event.get(k) is not None}
    ti = event.get("tool_input")
    if isinstance(ti, dict):
        small = {k: str(ti[k])[:400] for k in ("command", "description", "file_path", "notebook_path",
                                               "url", "query", "skill") if ti.get(k)}
        qs = ti.get("questions")
        if isinstance(qs, list) and qs and isinstance(qs[0], dict):
            small["questions"] = [{"question": str(qs[0].get("question", ""))[:300]}]
        out["tool_input"] = small
    if isinstance(out.get("message"), str):
        out["message"] = out["message"][:300]
    return out


def handle_hook(data):
    cfg = config()
    event = data.get("hook_event_name", "?")
    sid = data.get("session_id") or "unknown"
    now = time.time()
    detail = data.get("notification_type") or data.get("tool_name") or ""
    log(f"{event} {detail} session={sid[:8]} ({data.get('_agent', 'claude')})")

    # Several hooks can fire for one prompt at once; decide under a lock so only one speaks.
    with FileLock(DECIDE_LOCK, wait=10):
        st = load_session(sid)
        if event == "UserPromptSubmit":
            st.update(turn_start=now, token=None)
            save_session(sid, st)
            prune_sessions()
            return
        kind = classify(data, st, cfg)
        if kind and now - st.get("last_spoken", 0) < cfg["debounce_seconds"]:
            log(f"  skip {kind}: just spoke")
            kind = None
        if not kind:
            save_session(sid, st)
            return
        project = project_name(data.get("cwd"), cfg)
        need = describe_need(data, kind)
        agent = AGENT_NAMES.get(data.get("_agent", "claude"), "your agent")
        token = uuid.uuid4().hex
        transcript = data.get("transcript_path")
        st.update(last_spoken=now, token=token, kind=kind, project=project, need=need, agent=agent,
                  transcript=transcript)
        save_session(sid, st)

    # Reminders need the transcript to notice that you answered; without one they would nag wrongly.
    if kind in BLOCKERS and cfg["remind_after_minutes"] and cfg["enabled"] and mtime(transcript):
        spawn_reminder(sid, token)
    why = silenced(cfg)
    if why:
        log(f"  skip {kind}: {why}")
        return
    template = announce(kind, project, cfg, avoid=st.get("last_template"), need=need, agent=agent)
    update_session(sid, last_template=template)


def mtime(path):
    try:
        return os.path.getmtime(path)
    except (OSError, TypeError):
        return None


def remind(sid, token):
    """Nag again later if the session is still stuck on the same question."""
    cfg = config()
    time.sleep(15)  # let the transcript settle before taking a baseline
    st = load_session(sid)
    baseline = mtime(st.get("transcript"))
    start = st.get("last_spoken", time.time())
    for level, minutes in enumerate(cfg["remind_after_minutes"], start=1):
        wait = start + minutes * 60 - time.time()
        if wait > 0:
            time.sleep(wait)
        st = load_session(sid)
        if st.get("token") != token:
            return  # you replied, or a newer callout took over
        if mtime(st.get("transcript")) != baseline:
            return  # the session moved on
        why = silenced(cfg)
        if why:
            log(f"  skip reminder {level}: {why}")
            continue
        log(f"reminder {level} session={sid[:8]}")
        # Nag lines phrase {need} as an action, so only permissions carry it.
        need = st.get("need", "") if st.get("kind") == "permission" else ""
        template = announce("nag" if level == 1 else "nag2", st.get("project", "your session"), cfg,
                            avoid=st.get("last_template"), need=need, agent=st.get("agent", "your agent"))
        update_session(sid, last_template=template)


NEURAL_CHOICES = [
    ("en-US-AvaNeural", "Ava, US, warm and expressive"),
    ("en-US-EmmaNeural", "Emma, US, cheerful"),
    ("en-US-AndrewNeural", "Andrew, US, relaxed"),
    ("en-GB-SoniaNeural", "Sonia, British"),
    ("en-GB-RyanNeural", "Ryan, British"),
    ("en-IN-NeerjaExpressiveNeural", "Neerja, Indian English"),
    ("en-IN-PrabhatNeural", "Prabhat, Indian English"),
    ("en-AU-NatashaNeural", "Natasha, Australian"),
]

PS_VOICES = r"""
$v = New-Object -ComObject SAPI.SpVoice
$cat = New-Object -ComObject SAPI.SpObjectTokenCategory
$cat.SetId('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices', $false)
$seen = @{}
foreach ($t in @($v.GetVoices()) + @($cat.EnumerateTokens())) {
  $d = $t.GetDescription()
  $name = ($d -replace '^Microsoft ', '' -replace ' Desktop', '' -replace ' - .*$', '').Trim()
  if (-not $seen.ContainsKey($name)) { $seen[$name] = 1; "$name|$d" }
}
"""


def local_voices():
    """[(name, description)] of the offline voices this machine has."""
    if WINDOWS:
        encoded = base64.b64encode(PS_VOICES.encode("utf-16-le")).decode()
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                           capture_output=True, timeout=60, creationflags=NO_WINDOW)
        rows = [line.split("|", 1) for line in r.stdout.decode(errors="replace").splitlines() if "|" in line]
        return [(n, d) for n, d in rows]
    if MAC:
        r = subprocess.run(["say", "-v", "?"], capture_output=True, text=True)
        out = []
        for line in r.stdout.splitlines():
            parts = line.split("#", 1)[0].split()
            if len(parts) >= 2 and parts[-1].startswith("en"):
                out.append((" ".join(parts[:-1]), parts[-1]))
        return out
    return [("espeak", "espeak")] if shutil.which("espeak") else []


def cmd_voices():
    print("Characters:")
    for name, persona in load_personas().items():
        sample = persona["lines"]["permission"][0].replace("{project}", "your project").replace("{need}", "run the tests")
        print(f"  {name}: \"{sample}\"")
    print("\nBuilt-in voices on this machine (offline, private):")
    voices = local_voices()
    for name, desc in voices:
        print(f"  {name}  ({desc})")
    if not voices:
        print("  none found" + ("" if WINDOWS or MAC else " (install espeak)"))
    try:
        import edge_tts  # noqa: F401
        state = "installed"
    except ImportError:
        state = "not installed: needs `python -m pip install edge-tts`"
    print(f"\nNatural online voices (edge-tts {state}). Each spoken line is sent to Microsoft's")
    print("online read-aloud service, and edge-tts is an unofficial client for it:")
    for vid, desc in NEURAL_CHOICES:
        print(f"  {vid}  ({desc})")


def pick(prompt, options, default=1):
    """Ask for one of `options` by number in the terminal; returns the index."""
    for i, label in enumerate(options, start=1):
        print(f"  {i}. {label}")
    while True:
        raw = input(f"{prompt} [{default}]: ").strip() or str(default)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"  Type a number from 1 to {len(options)}.")


def cmd_setup(cfg):
    """The terminal version of setup, for agents without a Claude Code skill."""
    personas = load_personas()
    names = list(personas)
    print("Which character should talk to you?")
    labels = [f"{n}: \"{personas[n]['lines']['permission'][0]}\"".replace("{project}", "my-app")
              .replace("{need}", "run the tests") for n in names]
    persona_name = names[pick("Character", labels, names.index("friend") + 1 if "friend" in names else 1)]
    persona = personas[persona_name]

    try:
        import edge_tts  # noqa: F401
        have_neural = True
    except ImportError:
        have_neural = False
    local = local_voices()
    choices = [("auto", f"{persona_name}'s own built-in voice (offline)")]
    choices += [(n, f"{n}, built in (offline)") for n, _ in local]
    choices += [(v, f"{d}, online") for v, d in NEURAL_CHOICES]
    print("\nWhich voice? Online voices send each spoken line to Microsoft's read-aloud service,")
    print("through edge-tts, an unofficial client" + ("." if have_neural else " that is not installed yet."))
    while True:
        voice = choices[pick("Voice", [label for _, label in choices])][0]
        if "Neural" in voice and not have_neural:
            if input("Install edge-tts now? [y/N]: ").strip().lower() != "y":
                continue
            subprocess.run([sys.executable, "-m", "pip", "install", "edge-tts"])
            try:
                import edge_tts  # noqa: F401,F811
                have_neural = True
            except ImportError:
                print("edge-tts did not install; pick a built-in voice for now.")
                continue
        sample = make_line(persona, "permission", "my-app", cfg, need="run the tests")[1]
        speak(sample, persona, cfg, voice=None if voice == "auto" else voice)
        if input("Keep this one? [Y/n]: ").strip().lower() in ("", "y", "yes"):
            break

    saved = load_json(CONFIG, {})
    saved["personas"] = [persona_name]
    if "Neural" in voice:
        personas[persona_name]["neural_voice"] = voice
        save_json(USER_PERSONAS, personas)
        saved["engine"], saved["voice"] = "neural", "auto"
    else:
        saved["engine"], saved["voice"] = "local", voice if voice == "auto" else voice.capitalize()
    save_json(CONFIG, saved)
    print(f"\nSaved: {persona_name}, {voice}. Settings are in {CONFIG}.")


def cmd_welcome():
    """SessionStart, first time only: say hello so people know the sound works."""
    marker = os.path.join(STATE, "welcomed")
    if os.path.exists(CONFIG) or os.path.exists(marker):
        return
    os.makedirs(STATE, exist_ok=True)
    open(marker, "w").close()
    print(json.dumps({"systemMessage": "voice-alerts is on. Run /voice-alerts setup to pick its character and voice."}))
    spawn_detached("test", "welcome")


def cmd_status(cfg):
    personas = load_personas()
    print("settings folder:", DATA)
    print("personas:", ", ".join(cfg["personas"]), "| engine:", cfg["engine"], "| volume:", cfg["volume"])
    local_key = "voice" if WINDOWS else "mac_voice"
    for pname in cfg["personas"]:
        if pname in personas:
            pers = personas[pname]
            nv = pers.get("neural_voice", "-")
            local = pers.get(local_key) if cfg["voice"] == "auto" else cfg["voice"]
            print(f"  {pname}: neural voice {', '.join(nv) if isinstance(nv, list) else nv}; local voice {local}")
    print("available personas:", ", ".join(personas))
    m = load_json(MUTE, None)
    if muted():
        until = m.get("until", 0)
        print("muted", "until unmute" if not until else f"until {datetime.fromtimestamp(until):%H:%M}")
    else:
        print("not muted")
    print("quiet hours:", cfg["quiet_hours"] or "none")
    if WINDOWS:
        users = mic_users(cfg)
        print("microphone in use by:", ", ".join(users) if users else "nobody")
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8", errors="replace") as f:
            tail = f.readlines()[-8:]
        print("recent:")
        print("".join(tail).rstrip())


# ---- Wiring up other coding agents ---------------------------------------------------
# Claude Code gets the plugin. Every other agent gets hooks in its own user config,
# pointing at a copy of this script in ~/.voice-alerts/app so the download can move.

MARK = "voice_alerts.py"  # how our hook entries are recognized again on uninstall


def short_path(path):
    """On Windows, the 8.3 form of a path with spaces, so commands need no quoting."""
    if not WINDOWS or " " not in path:
        return path
    import ctypes

    buf = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024) and " " not in buf.value:
        return buf.value
    return path


def runtime(home):
    """Copy the runtime to a stable folder; return (python, script) for hooks to call."""
    app = os.path.join(os.environ.get("VOICE_ALERTS_HOME") or os.path.join(home, ".voice-alerts"), "app")
    os.makedirs(app, exist_ok=True)
    for name in ("voice_alerts.py", "personas.json"):
        src, dst = os.path.join(HERE, name), os.path.join(app, name)
        if os.path.normcase(os.path.abspath(src)) != os.path.normcase(os.path.abspath(dst)):
            shutil.copyfile(src, dst)
    return sys.executable, os.path.join(app, "voice_alerts.py")


def hook_command(agent, home, shell):
    """The hook command line for `shell`: posix, cmd (cmd.exe) or powershell."""
    py, script = (short_path(p) for p in runtime(home))
    args = ["hook", "--agent", agent]
    if not WINDOWS or shell == "posix":
        return " ".join(shlex.quote(x) for x in [py, script, *args])
    if shell == "powershell":
        quoted = [f"'{p}'" if " " in p else p for p in (py, script)]
        return ("& " if " " in py else "") + " ".join(quoted + args)
    return " ".join(f'"{p}"' if " " in p else p for p in (py, script)) + " " + " ".join(args)


def read_config(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text) if text.strip() else {}
    except ValueError as e:
        raise RuntimeError(f"can't read {path} ({e}); it may contain comments. Add the hooks by hand.")


def write_config(path, data):
    if os.path.exists(path):
        shutil.copyfile(path, path + ".voice-alerts.bak")
    save_json(path, data)


def strip_ours(hooks):
    """Remove voice-alerts entries from an agent's hooks table, in place."""
    for event in list(hooks):
        kept = []
        for group in hooks[event] or []:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                inner = [h for h in group["hooks"] if MARK not in json.dumps(h)]
                if inner:
                    kept.append({**group, "hooks": inner})
            elif MARK not in json.dumps(group):
                kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]


def env_dir(var, home, *default):
    """An agent's config folder: its environment override, for the real home only."""
    if home == HOME and os.environ.get(var):
        return os.environ[var]
    return os.path.join(home, *default)


def install_codex(home, remove=False):
    path = os.path.join(env_dir("CODEX_HOME", home, ".codex"), "hooks.json")
    data = read_config(path)
    hooks = data.setdefault("hooks", {})
    strip_ours(hooks)
    if not remove:
        entry = {"type": "command", "command": hook_command("codex", home, "cmd"), "timeout": 30}
        for event in ("UserPromptSubmit", "PermissionRequest", "Stop"):
            hooks.setdefault(event, []).append({"hooks": [entry]})
        hooks.setdefault("PreToolUse", []).append({"matcher": "^request_user_input(_async)?$", "hooks": [entry]})
    write_config(path, data)
    return path, "In Codex, run /hooks and trust the voice-alerts hooks. Codex skips new hooks until you do."


def install_gemini(home, remove=False):
    path = os.path.join(home, ".gemini", "settings.json")
    data = read_config(path)
    hooks = data.setdefault("hooks", {})
    strip_ours(hooks)
    if not remove:
        entry = {"name": "voice-alerts", "type": "command",
                 "command": hook_command("gemini", home, "powershell"), "timeout": 10000}
        for event in ("BeforeAgent", "AfterAgent", "Notification"):
            hooks.setdefault(event, []).append({"hooks": [entry]})
        hooks.setdefault("BeforeTool", []).append({"matcher": "ask_user|exit_plan_mode", "hooks": [entry]})
    write_config(path, data)
    return path, ""


def install_copilot(home, remove=False):
    path = os.path.join(env_dir("COPILOT_HOME", home, ".copilot"), "hooks", "voice-alerts.json")
    if remove:
        if os.path.exists(path):
            os.remove(path)
        return path, ""

    def entry(**extra):
        return {"type": "command", "bash": hook_command("copilot", home, "posix"),
                "powershell": hook_command("copilot", home, "powershell"), "timeoutSec": 10, **extra}

    save_json(path, {"version": 1, "hooks": {
        "UserPromptSubmit": [entry()], "Stop": [entry()],
        "Notification": [entry(matcher="permission_prompt|elicitation_dialog")]}})
    return path, "Copilot's permission prompts don't say which tool is asking, so those lines stay general."


def install_cursor(home, remove=False):
    path = os.path.join(home, ".cursor", "hooks.json")
    data = read_config(path)
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    strip_ours(hooks)
    if not remove:
        for event in ("beforeSubmitPrompt", "stop"):
            hooks.setdefault(event, []).append({"command": hook_command("cursor", home, "cmd"), "timeout": 10})
    write_config(path, data)
    return path, ("Cursor has no event for 'waiting for your approval', so it only announces finished turns. "
                  "If Cursor also imports your Claude Code hooks, each turn is still announced once.")


def install_opencode(home, remove=False):
    path = os.path.join(env_dir("XDG_CONFIG_HOME", home, ".config"), "opencode", "plugins", "voice-alerts.js")
    if remove:
        if os.path.exists(path):
            os.remove(path)
        return path, ""
    py, script = runtime(home)
    with open(os.path.join(HERE, "opencode-plugin.js"), encoding="utf-8") as f:
        code = f.read().replace("__PYTHON__", json.dumps(py)).replace("__SCRIPT__", json.dumps(script))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(code)
    return path, "This is an OpenCode 1.x plugin. OpenCode 2 changed its plugin system and isn't supported yet."


def install_aider(home, remove=False):
    path = os.path.join(home, ".aider.conf.yml")
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    lines = [ln for ln in text.splitlines() if "# voice-alerts" not in ln]
    if not remove:
        if any(re.match(r"\s*notifications([-_]command)?\s*:", ln) for ln in lines):
            raise RuntimeError(f"{path} already sets notifications; point notifications-command at "
                               f"{hook_command('aider', home, 'cmd')}")
        cmd = hook_command("aider", home, "cmd").replace("'", "''")
        lines += ["notifications: true  # voice-alerts", f"notifications-command: '{cmd}'  # voice-alerts"]
    if os.path.exists(path):
        shutil.copyfile(path, path + ".voice-alerts.bak")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return path, "Aider says only that it's waiting for you, so every line is a 'your turn' line."


def install_claude(home, remove=False):
    raise RuntimeError("Claude Code uses the plugin instead: /plugin marketplace add saketh-saridena/voice-alerts, then "
                       "/plugin install voice-alerts@voice-alerts" if not remove else
                       "remove the plugin with /plugin in Claude Code")


INSTALLERS = {"codex": install_codex, "gemini": install_gemini, "copilot": install_copilot,
              "cursor": install_cursor, "opencode": install_opencode, "aider": install_aider,
              "claude": install_claude}
DETECT = {"claude": ("claude", ".claude"), "codex": ("codex", ".codex"), "gemini": ("gemini", ".gemini"),
          "copilot": ("copilot", ".copilot"), "cursor": ("cursor-agent", ".cursor"),
          "opencode": ("opencode", os.path.join(".config", "opencode")), "aider": ("aider", ".aider.conf.yml")}


def detected(agent, home):
    exe, folder = DETECT[agent]
    return bool(shutil.which(exe)) or os.path.exists(os.path.join(home, folder))


def expand(agents, home):
    if "all" in agents:
        return [a for a in INSTALLERS if a != "claude" and detected(a, home)]
    return list(dict.fromkeys(agents))


def cmd_install(agents, home, cfg):
    failed = 0
    for agent in expand(agents, home):
        try:
            path, note = INSTALLERS[agent](home)
            print(f"{agent}: hooks added to {path}" + (f"\n  {note}" if note else ""))
        except Exception as e:
            failed += 1
            print(f"{agent}: not installed. {e}")
    if failed < len(expand(agents, home)) and not silenced(cfg):
        announce("welcome", "your project", cfg)
    if os.path.exists(CONFIG):
        print("Settings:", CONFIG)
    else:
        print("Pick a character and voice: python \"%s\" setup" % runtime(home)[1])
    return 1 if failed else 0


def cmd_uninstall(agents, home):
    for agent in expand(agents, home):
        try:
            path, _ = INSTALLERS[agent](home, remove=True)
            print(f"{agent}: hooks removed from {path}")
        except Exception as e:
            print(f"{agent}: {e}")
    return 0


def cmd_agents(home):
    for agent in INSTALLERS:
        found = "found" if detected(agent, home) else "not found"
        print(f"  {agent:9s} {found}")


def main():
    p = argparse.ArgumentParser(description="voice-alerts: a voice that tells you when your coding agent needs you")
    sub = p.add_subparsers(dest="cmd")
    h = sub.add_parser("hook")
    h.add_argument("--agent", default="claude", choices=sorted(ADAPTERS))
    h.add_argument("payload", nargs="?", help="event JSON, for agents that pass it as an argument")
    r = sub.add_parser("remind")
    r.add_argument("sid")
    r.add_argument("token")
    hd = sub.add_parser("handle")
    hd.add_argument("payload")
    for name in ("install", "uninstall"):
        ins = sub.add_parser(name, help=f"{name} the hooks for one or more agents")
        ins.add_argument("agents", nargs="+", choices=sorted(INSTALLERS) + ["all"])
        ins.add_argument("--home", default=HOME, help=argparse.SUPPRESS)  # a fake home, for testing
    ag = sub.add_parser("agents", help="which coding agents are installed and wired up")
    ag.add_argument("--home", default=HOME, help=argparse.SUPPRESS)
    sub.add_parser("welcome")
    sub.add_parser("voices")
    sub.add_parser("install-neural")
    sub.add_parser("setup", help="pick a character and voice, in the terminal")
    t = sub.add_parser("test")
    t.add_argument("kind", nargs="?", default="permission", choices=KINDS)
    s = sub.add_parser("say")
    s.add_argument("kind", choices=KINDS)
    s.add_argument("--persona")
    s.add_argument("--voice")
    s.add_argument("--project", default="your project")
    s.add_argument("--need", default="")
    s.add_argument("--text")
    s.add_argument("--out", help="save to this file instead of speaking")
    pe = sub.add_parser("persona")
    pe.add_argument("names")
    vo = sub.add_parser("voice")
    vo.add_argument("name")
    mu = sub.add_parser("mute")
    mu.add_argument("minutes", nargs="?", type=float)
    sub.add_parser("unmute")
    sub.add_parser("status")
    a = p.parse_args()
    cfg = config()

    if a.cmd == "hook":
        # Print nothing: some agents read hook output as instructions or approval decisions.
        try:
            if a.payload is not None:
                raw = a.payload
            elif a.agent in NO_STDIN or sys.stdin is None or sys.stdin.isatty():
                raw = "{}"
            else:
                raw = sys.stdin.buffer.read().decode("utf-8", "replace")
            event = ADAPTERS[a.agent](json.loads(raw or "{}"))
            if event:
                event = {"_agent": a.agent, **event}
                if a.agent == "claude" and event["_agent"] == "claude":
                    handle_hook(event)  # Claude Code already runs this hook in the background
                else:
                    # Other agents wait for the hook to finish, so hand off and return at once.
                    spawn_detached("handle", json.dumps(compact(event)))
        except Exception as e:  # a broken voice alert must never break a session
            log(f"error ({a.agent}): {e!r}")
    elif a.cmd == "handle":
        try:
            handle_hook(json.loads(a.payload))
        except Exception as e:
            log(f"error: {e!r}")
    elif a.cmd == "install":
        sys.exit(cmd_install(a.agents, a.home, cfg))
    elif a.cmd == "uninstall":
        sys.exit(cmd_uninstall(a.agents, a.home))
    elif a.cmd == "agents":
        cmd_agents(a.home)
    elif a.cmd == "welcome":
        try:
            cmd_welcome()
        except Exception as e:
            log(f"welcome error: {e!r}")
    elif a.cmd == "voices":
        cmd_voices()
    elif a.cmd == "install-neural":
        # Same interpreter the hooks use, so the package is where they look for it.
        sys.exit(subprocess.run([sys.executable, "-m", "pip", "install", "edge-tts"]).returncode)
    elif a.cmd == "setup":
        cmd_setup(cfg)
    elif a.cmd == "remind":
        try:
            remind(a.sid, a.token)
        except Exception as e:
            log(f"reminder error: {e!r}")
    elif a.cmd == "test":
        if a.kind == "welcome" and silenced(cfg):
            return  # the install hello keeps to mute, quiet hours and calls
        announce(a.kind, project_name(os.getcwd(), cfg), cfg)
    elif a.cmd == "say":
        personas = load_personas()
        persona = personas[a.persona] if a.persona else choose_persona(cfg, personas)[1]
        text = a.text or make_line(persona, a.kind, a.project, cfg, need=a.need)[1]
        written = speak(text, persona, cfg, out=a.out, voice=a.voice)
        print(written or text)
    elif a.cmd == "persona":
        personas = load_personas()
        names = [n.strip().lower() for n in a.names.split(",") if n.strip()]
        if names == ["all"]:
            names = list(personas)
        bad = [n for n in names if n not in personas]
        if bad:
            sys.exit("unknown persona: " + ", ".join(bad) + " (have: " + ", ".join(personas) + ")")
        saved = load_json(CONFIG, {})
        saved["personas"] = names
        save_json(CONFIG, saved)
        print("personas:", ", ".join(names))
    elif a.cmd == "voice":
        saved = load_json(CONFIG, {})
        if "Neural" in a.name:
            # Neural voices belong to the active personas; several rotate.
            names = [n.strip() for n in a.name.split(",") if n.strip()]
            personas = load_personas()
            for pname in cfg["personas"]:
                personas[pname]["neural_voice"] = names if len(names) > 1 else names[0]
            save_json(USER_PERSONAS, personas)
            saved["engine"] = "neural"
            print("neural voice for", ", ".join(cfg["personas"]) + ":", ", ".join(names))
            try:
                import edge_tts  # noqa: F401
            except ImportError:
                print("note: neural voices need edge-tts (pip install edge-tts); until then the local voice speaks")
        else:
            saved["engine"] = "local"
            saved["voice"] = "auto" if a.name.lower() == "auto" else a.name.capitalize()
            print("local voice:", saved["voice"])
        save_json(CONFIG, saved)
    elif a.cmd == "mute":
        until = time.time() + a.minutes * 60 if a.minutes else 0
        save_json(MUTE, {"until": until})
        print("muted", f"for {a.minutes:g} minutes" if a.minutes else "until unmute")
    elif a.cmd == "unmute":
        try:
            os.remove(MUTE)
        except OSError:
            pass
        print("unmuted")
    else:
        cmd_status(cfg)


if __name__ == "__main__":
    main()
