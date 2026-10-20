<div align="center">

<img src="assets/banner.svg" width="100%" alt="voice-alerts: a friendly voice that tells you when your coding agent needs you">

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-3776AB.svg)
![Windows | macOS | Linux](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![7 coding agents](https://img.shields.io/badge/agents-7-brightgreen.svg)

Claude Code · OpenAI Codex CLI · Gemini CLI · GitHub Copilot CLI · Cursor · OpenCode · Aider

</div>

---

Run a few agents at once, switch to another window, and stop checking on them. When one needs you, you hear it:

> *"Hey! **The login fix session** needs your okay to **run the test suite**. Got a sec?"*
>
> *"Quick question from **the docs refresh session**. **Which deploy target should I use?**"*
>
> *"Good news, **the data pipeline session** is finished. Want to have a look?"*

It names the session by the title you see in the app, says what it's waiting for, and stays quiet the rest of the time.

## Quick start

**Claude Code**, in any session:

```
/plugin marketplace add saketh-saridena/voice-alerts
/plugin install voice-alerts@voice-alerts
```

Start a new session and it says hello. Then run `/voice-alerts setup` to pick a character and voice.

**Codex, Gemini, Copilot, Cursor, OpenCode or Aider**: download this repo, then:

```
python voice-alerts/scripts/voice_alerts.py install codex
python ~/.voice-alerts/app/voice_alerts.py setup
```

Swap `codex` for your agent, list several, or use `all` for every agent found on your machine. Python 3.8+ is the only requirement.

## What you'll hear

| | When | It says |
| :---: | --- | --- |
| <img src="assets/icons/permission.svg" width="20" height="20" alt=""> | The agent needs permission | what for: *"…needs your okay to install package dependencies"*, *"…to edit settings.json"*, *"…to open a page on github.com"* |
| <img src="assets/icons/question.svg" width="20" height="20" alt=""> | The agent asks you something | the question itself, read out |
| <img src="assets/icons/plan.svg" width="20" height="20" alt=""> | A plan is ready | that it's ready for your review |
| <img src="assets/icons/done.svg" width="20" height="20" alt=""> | A long job finished | *"done"*, but only for turns over 3 minutes; quick replies stay quiet |
| <img src="assets/icons/reminder.svg" width="20" height="20" alt=""> | You haven't answered | a nudge after 3 minutes, a more dramatic one after 10, and nothing once you've responded |

**It's polite about it:**
- **Calls:** on Windows it holds back while any app is using your microphone (Teams, Zoom, Meet) and nudges you afterwards.
- **Several sessions:** they take turns, so voices never talk over each other.
- **Each event once:** when one prompt fires several hooks, you still hear one line.

## Supported agents

| Agent | Permission | Questions | Plans | Done | Reminders |
| --- | :---: | :---: | :---: | :---: | :---: |
| **Claude Code** (plugin) | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> with detail | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> |
| **OpenAI Codex CLI** 0.124+ | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> with detail | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> |
| **Gemini CLI** 0.26+ | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> with detail | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> |
| **GitHub Copilot CLI** 1.0.18+ | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> general | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | |
| **Cursor** 1.7+ | | | | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | |
| **OpenCode** 1.x | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> with detail | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> | |
| **Aider** 0.76+ | | | | <img src="assets/icons/check.svg" width="16" height="16" alt="yes"> after every reply | |

**About the gaps:** the empty cells are events that agent doesn't report. For example, Cursor has no "waiting for your approval" hook, and Copilot doesn't say which tool is asking. Reminders need a transcript file to tell when you've answered, so they only run where the agent provides one. Session titles come from Claude Code; other agents are named by their project folder.

**How it was tested:** Claude Code is used daily on Windows. The other agents are wired from their official docs and source (October 2026) and tested with those payloads. If something doesn't fire for you, please open an issue with a line from `~/.voice-alerts/state/events.log`.

**Not yet:** Windsurf, Cline, Amp and OpenCode 2. Their hooks can't tell when they're waiting for you, or aren't documented well enough yet.

## Characters

Pick one in `setup`, or list several to rotate between them.

| | Character | Sounds like |
| :---: | --- | --- |
| <img src="assets/icons/friend.svg" width="20" height="20" alt=""> | `friend` (default) | *"Hey, quick one. The API session wants to edit config.yaml. Mind taking a look?"* |
| <img src="assets/icons/butler.svg" width="20" height="20" alt=""> | `butler` | *"Pardon the interruption. The API session wishes to edit config.yaml, and requires your blessing."* |
| <img src="assets/icons/commentator.svg" width="20" height="20" alt=""> | `commentator` | *"And the API session has appealed to the umpire! It wants to edit config.yaml. Will you raise the finger?"* |
| <img src="assets/icons/intern.svg" width="20" height="20" alt=""> | `intern` | *"Um, hi! The API session needs your okay to edit config.yaml. I really do not want to get fired."* |
| <img src="assets/icons/trailer.svg" width="20" height="20" alt=""> | `trailer` | *"In a world where the API session must edit config.yaml, only you can say yes."* |

## Voices

**Built-in voices** are the default. They work offline, and nothing leaves your machine:
- **Windows:** SAPI voices (Zira, David, Mark, plus any you add in Settings → Time & language → Speech).
- **macOS:** `say` (Samantha, Daniel and others).
- **Linux:** `espeak` or `spd-say`, if installed.

**Natural online voices** are optional and sound close to a real person: `en-US-AvaNeural`, `en-US-EmmaNeural`, `en-GB-SoniaNeural`, `en-IN-NeerjaExpressiveNeural` and more. `setup` can install the `edge-tts` package they need. Before you turn them on:

> [!IMPORTANT]
> Every spoken line goes to Microsoft's online read-aloud service: the session name, what the agent wants to do and any question text. `edge-tts` is an unofficial client for that service and can be slow or change without notice. If a line doesn't arrive within 8 seconds, or you're offline, the built-in voice speaks instead. Don't use online voices for work you can't share with a third party.

## Commands

In Claude Code, use `/voice-alerts <command>`, or just ask: *"mute the voice for an hour"*. With any other agent, run `python ~/.voice-alerts/app/voice_alerts.py <command>`.

| Command | What it does |
| --- | --- |
| `setup` | Pick a character and voice, hearing each one first |
| `test` | Say a sample line now |
| `mute 30` / `unmute` | Quiet for 30 minutes (or until you unmute) |
| `persona butler` | Change the character |
| `voice en-US-AvaNeural` | Change the voice (`voice auto` for each character's built-in one) |
| `status` | Settings, mute state, and what it decided recently |
| `agents` | Which coding agents it found on this machine |
| `install` / `uninstall <agent>` | Wire an agent up, or remove it again |

<details>
<summary><b>Configuration</b></summary>

<br>

One settings file serves every agent: `~/.voice-alerts/config.json` (or `$VOICE_ALERTS_HOME/config.json`). It only needs the keys you change:

```json
{
  "personas": ["friend"],
  "volume": 80,
  "quiet_hours": ["22:00", "08:00"],
  "done_after_seconds": 180,
  "remind_after_minutes": [3, 10],
  "skip_during_calls": true,
  "name_by": "session",
  "aliases": { "my-very-long-repo-name": "the API" }
}
```

| Key | What it does |
| --- | --- |
| `name_by` | `session` (default) says the session's title, shortened to its first part if long. `project` says the folder name. `both`: *"the Fix login bug session in checkout-service"* |
| `quiet_hours` | No alerts between these times |
| `done_after_seconds` | Only announce "done" for turns at least this long |
| `remind_after_minutes` | When to nudge about an unanswered prompt; `[]` turns nudges off |
| `skip_during_calls` | Hold back while an app uses the microphone (Windows) |
| `ignore_mic_apps` | Apps to leave out of that check, e.g. one that keeps the mic open all day |
| `aliases` | Say a shorter name for a long folder or session title |

To change the wording, copy `scripts/personas.json` to `~/.voice-alerts/personas.json` and edit the copy. `{project}`, `{need}` and `{agent}` are filled in when it speaks.

</details>

<details>
<summary><b>Installing for other agents: the details</b></summary>

<br>

- **Where it lives:** `install` copies the runtime to `~/.voice-alerts/app/`, so you can delete the download afterwards.
- **What it changes:** each agent's own user config: `~/.codex/hooks.json`, `~/.gemini/settings.json`, `~/.copilot/hooks/voice-alerts.json`, `~/.cursor/hooks.json`, `~/.config/opencode/plugins/voice-alerts.js` or `~/.aider.conf.yml`. Before changing an existing file, it saves a copy next to it, ending in `.voice-alerts.bak`.
- **Codex:** Codex skips new hooks until you trust them. Run `/hooks` in Codex once and trust the voice-alerts entries.
- **Codex and Copilot plugins:** both can read Claude plugins too, but use `install` for them, since the plugin's hooks are written for Claude Code's events.
- **Removing it:** `python ~/.voice-alerts/app/voice_alerts.py uninstall <agent>`.

</details>

<details>
<summary><b>How it works</b></summary>

<br>

- **Translation:** each agent's hook runs `voice_alerts.py hook --agent <name>`. A small adapter turns that agent's event into one of: permission, question, plan, done, or your turn.
- **Never blocks:** the hook returns at once and prints nothing. Speech runs in a background process, because several agents wait for their hooks, and some read hook output as instructions or approval decisions.
- **Session names:** in Claude Code the session's title is read from the last few kilobytes of its transcript, so it stays fast even when a transcript grows to hundreds of megabytes.
- **Heard once:** a lock and a 10-second window turn the several hooks one prompt can fire into one line.
- **Log:** every decision goes to `~/.voice-alerts/state/events.log`.

</details>

<details>
<summary><b>Troubleshooting</b></summary>

<br>

- **It's silent:** run `status`. It shows whether it's muted, in quiet hours, or holding back because an app is using the microphone.
- **Nothing in the log for one agent:** that agent's hooks aren't running. Check its config file (listed by `install`), and for Codex, that you trusted the hooks in `/hooks`.
- **No online voice:** check that `python -c "import edge_tts"` works with the Python that `install` used.
- **Too chatty:** raise `done_after_seconds`, set `quiet_hours`, or `mute`.
- **Updating in Claude Code:** run `claude plugin update voice-alerts@voice-alerts` (or use `/plugin`), then restart Claude Code.

</details>

## Contributing

Ideas, new characters and new agents are welcome. Run the tests with `python -m unittest discover tests`. They never speak and never touch your real configs.

To support a new agent:
1. Add an `adapt_<agent>` function that maps its payload to the Claude Code event shape.
2. Add an `install_<agent>` function.
3. Add a test with a real payload from that agent's docs.

## License

[MIT](LICENSE) © Saketh Saridena
