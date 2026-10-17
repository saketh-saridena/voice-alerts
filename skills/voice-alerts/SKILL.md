---
name: voice-alerts
description: Set up and control voice-alerts, the voice that speaks up when a coding agent needs you (permission prompts, questions, plans, long jobs finishing). Use when the user wants to set it up or pick its character or voice, mute or unmute it, test it, check its status, or change quiet hours, volume or reminders.
argument-hint: "setup | mute [minutes] | unmute | test | status | persona NAME | voice NAME"
---

# voice-alerts

Everything goes through one launcher. Run it with the Bash tool:

```bash
"${CLAUDE_PLUGIN_ROOT}/hooks/run.cmd" <arguments>
```

If `CLAUDE_PLUGIN_ROOT` is empty in your shell, the plugin root is two folders above this skill's base directory: run `"<base directory>/../../hooks/run.cmd" <arguments>`.

With no arguments, run `status`. For anything except `setup`, report the result in one short line.

## Setup

When the user asks to set it up (`setup`), or asks to change how it sounds, walk them through it:

1. Run `voices`. It lists the characters with a sample line each, the built-in voices on this machine, and the natural online voices.
2. Ask which character they want: friend, butler, commentator, intern or trailer. Show each one's sample line. If they pick several, they rotate. Use the AskUserQuestion tool when you have it.
3. Ask which voice: one of the built-in voices (offline and private), or a natural online voice such as `en-US-AvaNeural`.
   - Online voices send every spoken line, including the project name, what the agent wants to do and any question text, to Microsoft's online read-aloud service. `edge-tts`, the package that reaches it, is an unofficial client. Say both before they choose.
   - If they choose an online voice and `voices` said edge-tts is not installed, ask for their OK, then run `install-neural`. It installs edge-tts into the same Python the launcher uses.
4. Let them hear a choice before saving it: `say permission --persona <name> --voice <voice> --project "<this folder's name>" --need "run the tests"`. Offer another listen if they're unsure.
5. Save it: `persona <name>` (comma-separate several), then `voice <voice>`, or `voice auto` for each character's own built-in voice.
6. Ask whether they want quiet hours, and set them in the config file (below) if so.
7. Run `test`, then tell them `mute 30` and `unmute` exist.

## Commands

| Arguments | What it does |
| --- | --- |
| `status` | Settings, mute state, which app holds the microphone, recent decisions |
| `voices` | Characters, built-in voices on this machine, online voices |
| `test [permission\|question\|plan\|done]` | Say a sample line now |
| `say KIND --persona P --voice V --project NAME --need TEXT` | Preview a specific combination |
| `mute [minutes]` | Stay quiet for that long, or until `unmute` |
| `unmute` | Talk again |
| `persona friend` | Pick the character. Several, comma-separated, rotate. |
| `voice auto` | Each character's own built-in voice, offline |
| `voice Zira` | One built-in voice for every character |
| `voice en-US-AvaNeural` | A natural online voice. Several, comma-separated, rotate. |
| `install-neural` | Install edge-tts for online voices (only with the user's OK) |

## Settings without a command

They live in `~/.voice-alerts/config.json` (shared by every coding agent), or `$VOICE_ALERTS_HOME/config.json` if that is set. Create the file if it is missing; it only needs the keys being changed. Edit it directly when the user asks:

- `quiet_hours`: `["22:00", "08:00"]`, or `null` for none
- `volume`: 0 to 100
- `done_after_seconds`: announce "done" only for turns at least this long (default 180)
- `remind_after_minutes`: when to nag about an unanswered prompt (default `[3, 10]`; `[]` turns reminders off)
- `skip_during_calls`: stay quiet while any app uses the microphone (Windows; default `true`)
- `ignore_mic_apps`: app names to leave out of that check
- `aliases`: `{"long-folder-name": "short spoken name"}`

To change the wording, copy the plugin's `scripts/personas.json` to `personas.json` in that same folder and edit the copy. `{project}`, `{need}` and `{agent}` are filled in when it speaks.
