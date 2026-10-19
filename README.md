# voice-alerts

A friendly voice that tells you when your coding agent needs you, and what it needs.

It works with Claude Code, OpenAI Codex CLI, Gemini CLI, GitHub Copilot CLI, Cursor, OpenCode and Aider.

Run a few agents at once, switch to another window, and you will hear things like:

> "Hey! **The login fix session** needs your okay to **run the test suite**. Got a sec?"
>
> "Quick question from **the docs refresh session**. **Which deploy target should I use?**"
>
> "Good news, **the data pipeline session** is finished. Want to have a look?"

It says which session is asking, by the title you see in the app, so you know where to go without looking. Agents without session titles get the project folder's name instead.

## What it announces

- **Permission prompts:** what the agent wants to do ("install package dependencies", "edit settings.json", "open a page on github.com").
- **Questions:** it reads the question out.
- **Plans:** it tells you a plan is ready to review.
- **Long jobs:** "done", when a turn took more than 3 minutes. Quick replies stay quiet.
- **Reminders:** if a prompt sits unanswered, it reminds you after 3 and 10 minutes, a little more dramatically each time, and stops as soon as you respond.
- **Calls:** on Windows it stays quiet while any app is using your microphone (Teams, Zoom, Meet) and reminds you afterwards.

## Supported agents

| Agent | How it's wired | What it announces | Tested |
| --- | --- | --- | --- |
| Claude Code | plugin | permission (with what), questions, plans, done, reminders | live, Windows |
| OpenAI Codex CLI 0.124+ | `install codex` → `~/.codex/hooks.json` | permission (with the command or file), questions, done, reminders | simulated events |
| Gemini CLI 0.26+ | `install gemini` → `~/.gemini/settings.json` | permission (with the command, file or MCP tool), questions, plans, done, reminders | simulated events |
| GitHub Copilot CLI 1.0.18+ | `install copilot` → `~/.copilot/hooks/voice-alerts.json` | permission (general), questions, done | simulated events |
| Cursor 1.7+ | `install cursor` → `~/.cursor/hooks.json` | done (Cursor has no "waiting for approval" event) | simulated events |
| OpenCode 1.x | `install opencode` → `~/.config/opencode/plugins/voice-alerts.js` | permission (with what), questions, plans, done | plugin run against simulated events |
| Aider 0.76+ | `install aider` → `~/.aider.conf.yml` | "your turn" after each reply | simulated events |

"Simulated events" means the hook formats come from each agent's official docs and source code (October 2026), and the test suite feeds those payloads through. If something doesn't fire in your agent, please open an issue with a line from `~/.voice-alerts/state/events.log`.

**Not supported yet:** Windsurf, Cline, Amp and OpenCode 2. Their hooks either can't tell when they're waiting for you, or aren't documented well enough yet.

## Install

**Requirements:** Python 3.8 or later. Nothing else for the built-in voices.

### Claude Code

```
/plugin marketplace add saketh-saridena/voice-alerts
/plugin install voice-alerts@voice-alerts
```

Start a new session. It says hello once; then run `/voice-alerts setup` to pick a character and voice.

### Every other agent

Download this repository (or `git clone https://github.com/saketh-saridena/voice-alerts`), then:

```
python voice-alerts/scripts/voice_alerts.py install codex
python ~/.voice-alerts/app/voice_alerts.py setup
```

- **Which agents:** use `codex`, `gemini`, `copilot`, `cursor`, `opencode` or `aider`, several at once, or `all` for every agent found on your machine.
- **Where it lives:** `install` copies the runtime to `~/.voice-alerts/app/`, so you can delete the download afterwards.
- **Backups:** before changing an agent's config, it saves a copy next to it, ending in `.voice-alerts.bak`.
- **Removing it:** run `python ~/.voice-alerts/app/voice_alerts.py uninstall codex`.
- **Codex:** Codex skips new hooks until you trust them. Run `/hooks` in Codex once and trust the voice-alerts entries.
- **Codex and Copilot plugins:** those agents can also read Claude plugins, but use `install` for them instead, since the plugin's hooks are written for Claude Code's events.

## Controls

In Claude Code, use `/voice-alerts <command>`, or just ask ("mute the voice for an hour"). Everywhere else, run `python ~/.voice-alerts/app/voice_alerts.py <command>`.

| Command | What it does |
| --- | --- |
| `setup` | Pick a character and voice, hearing each one first |
| `status` | Settings, mute state, and what it decided recently |
| `test` | Say a sample line now |
| `mute 30` | Quiet for 30 minutes (`mute` alone stays quiet until you unmute) |
| `unmute` | Talk again |
| `persona friend` | Change the character |
| `voice auto` | Each character's own built-in voice |
| `voice en-US-AvaNeural` | A natural online voice (see below) |
| `agents` | Which coding agents it found on this machine |

## Characters

| Character | Sounds like |
| --- | --- |
| `friend` (default) | "Hey, quick one. api-gateway wants to edit config.yaml. Mind taking a look?" |
| `butler` | "Pardon the interruption. api-gateway wishes to edit config.yaml, and requires your blessing." |
| `commentator` | "And api-gateway has appealed to the umpire! It wants to edit config.yaml. Will you raise the finger?" |
| `intern` | "Um, hi! api-gateway needs your okay to edit config.yaml. I really do not want to get fired." |
| `trailer` | "In a world where api-gateway must edit config.yaml, only you can say yes." |

Pick several, comma-separated, and it rotates between them.

## Voices

**Built-in (default, offline, private):**
- **Windows:** the SAPI voices (Zira, David, Mark, plus any you add under Settings > Time and language > Speech).
- **macOS:** `say` (Samantha, Daniel and others).
- **Linux:** `espeak` or `spd-say`, if installed.

**Natural online voices (optional):** `en-US-AvaNeural`, `en-US-EmmaNeural`, `en-GB-SoniaNeural`, `en-IN-NeerjaExpressiveNeural` and more. `setup` can install what they need, the `edge-tts` package. Before you turn them on:

- **Privacy:** every spoken line goes to Microsoft's online read-aloud service. That includes the project name, what the agent wants to do and the text of any question. Don't use them for work you can't share with a third party.
- **Support:** `edge-tts` is an unofficial client for that service. It can be slow or change without notice. If a line doesn't arrive within 8 seconds, or you're offline, the built-in voice speaks instead.

## Configuration

One settings folder serves every agent: `~/.voice-alerts/config.json`, or `$VOICE_ALERTS_HOME/config.json` if you set that variable. The file only needs the keys you change:

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

`name_by` picks the name it says:
- `session` (default): the session's title in Claude Code, such as "the Fix login bug session". Long titles are shortened to their first part.
- `project`: the project folder's name.
- `both`: "the Fix login bug session in checkout-service".

Other agents always use the project name, since their sessions have no titles it can read.

To change what it says, copy `scripts/personas.json` to `~/.voice-alerts/personas.json` and edit the copy. `{project}`, `{need}` and `{agent}` are filled in when it speaks.

## How it works

- **Translation:** each agent's hook calls `voice_alerts.py hook --agent <name>`. A small adapter turns that agent's event into one of: permission, question, plan, done, or your turn.
- **No waiting:** the hook returns at once and prints nothing. Speech runs in a background process, because several agents wait for their hooks, and some read hook output as instructions or approval decisions.
- **Heard once:** one prompt can fire several hooks at the same moment. A lock and a 10-second window make sure you hear it once.
- **Reminders:** they need the agent's transcript file to notice that you answered. So they only run where the agent provides one (Claude Code, Codex and Gemini), and never nag you about something you already handled.
- **Log:** every decision goes to `~/.voice-alerts/state/events.log`.

## Troubleshooting

- **Silent:** run `status`. It shows whether it's muted, in quiet hours, or holding back because an app is using the microphone. If an app keeps the microphone open all the time, add its name to `ignore_mic_apps`.
- **Nothing in the log for one agent:** that agent's hooks aren't running. Check its config file (listed by `install`), and for Codex, that you trusted the hooks in `/hooks`.
- **No online voice:** check that `python -c "import edge_tts"` works with the Python that `install` used.
- **Hears every reply:** raise `done_after_seconds`.

## Contributing

Run the tests with `python -m unittest discover tests`. They never speak and never touch your real configs.

To support a new agent:
1. Add an `adapt_<agent>` function that maps its payload to the Claude Code event shape.
2. Add an `install_<agent>` function.
3. Add a test with a real payload from that agent's docs.

## License

MIT
