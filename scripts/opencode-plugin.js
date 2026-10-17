// voice-alerts for OpenCode 1.x: tells the voice-alerts script when OpenCode needs you.
// `voice_alerts.py install opencode` copies this file into OpenCode's plugins folder and
// fills in the two paths below.
import { spawn } from "node:child_process"

const PYTHON = __PYTHON__
const SCRIPT = __SCRIPT__

// Hand an event to voice-alerts and move on: never awaited, so OpenCode never waits on speech.
function send(payload) {
  try {
    const child = spawn(PYTHON, [SCRIPT, "hook", "--agent", "opencode"], {
      stdio: ["pipe", "ignore", "ignore"],
      detached: true,
      windowsHide: true,
    })
    child.on("error", () => {})
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify(payload))
    child.unref()
  } catch {}
}

// OpenCode treats every export as a plugin, so this file exports only this function.
export const VoiceAlerts = async ({ directory, client }) => {
  const calls = new Map() // callID -> { tool, args }, to say what a permission is for
  const busy = new Set() // sessions in the middle of a turn; "idle" can arrive twice
  const aborted = new Set() // turns stopped with Esc stay quiet
  const parents = new Map() // sessionID -> parentID; subagent sessions stay quiet

  const isSubagent = async (id) => {
    if (!parents.has(id)) {
      const res = await client?.session?.get?.({ path: { id } }).catch(() => undefined)
      parents.set(id, res?.data?.parentID ?? null)
    }
    return Boolean(parents.get(id))
  }
  const base = (event, sessionID) => ({ hook_event_name: event, session_id: sessionID, cwd: directory })

  const idle = async (id) => {
    if (!id || !busy.delete(id)) return
    if (aborted.delete(id)) return
    if (await isSubagent(id)) return
    send(base("Stop", id))
  }

  return {
    "chat.message": async (input) => {
      send(base("UserPromptSubmit", input.sessionID))
    },
    "tool.execute.before": async (input, output) => {
      calls.set(input.callID, { tool: input.tool, args: output.args })
    },
    "tool.execute.after": async (input) => {
      calls.delete(input.callID)
    },
    event: async ({ event }) => {
      const p = event.properties || {}
      switch (event.type) {
        case "session.created":
        case "session.updated":
          if (p.info?.id) parents.set(p.info.id, p.info.parentID ?? null)
          break
        case "session.status":
          if (p.status?.type === "busy") busy.add(p.sessionID)
          else if (p.status?.type === "idle") await idle(p.sessionID)
          break
        case "session.idle":
          await idle(p.sessionID)
          break
        case "session.error":
          if (p.sessionID && p.error?.name === "MessageAbortedError") aborted.add(p.sessionID)
          break
        case "permission.asked": {
          const call = p.tool?.callID ? calls.get(p.tool.callID) : undefined
          send({
            ...base("PermissionRequest", p.sessionID),
            tool_name: call?.tool ?? p.permission,
            tool_input: call?.args ?? {},
            metadata: p.metadata ?? {},
          })
          break
        }
        case "question.asked":
          send({ ...base("Question", p.sessionID), questions: p.questions ?? [] })
          break
      }
    },
  }
}
