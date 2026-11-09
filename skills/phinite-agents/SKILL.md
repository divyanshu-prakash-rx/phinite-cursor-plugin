---
name: phinite-agents
description: Find and talk to the live Phinite agents in the user's workspace — list them, search for one that can do a task, and send it a message or a follow-up. Use when the user asks to run, invoke, ask or talk to a Phinite agent, asks "what agents do I have", "find an agent that can do X", "ask Phinite …", or brings a question that a workspace agent is built to answer. For building or changing agents, use phinite-design instead.
---
# Using Phinite agents

A Phinite **agent** here is a live agent graph in the signed-in workspace that Phinite exposes for other agents to
call. You act as the signed-in user, so you see and call exactly the agents their account can use. Sign-in is the
plugin's OAuth (`/phinite-login`). Never ask for an API key or token: the old API-key setup is gone.

**If these tools aren't in your tool list** (`list_agents`, `search_agents`, `discover_agent`, `invoke_agent`),
the connected Phinite server doesn't offer them yet. Say so in one line and stop. Don't fall back to `chat` or
`call_trigger` unless the user asks: those test and run graphs by flow, which is a different job.

## Find an agent

| Situation | Tool |
|---|---|
| The user wants an agent for a task and you don't know which | `search_agents(query, limit?, tags?)` |
| The user asks what agents they have, or search found nothing relevant | `list_agents(status?, limit?)` |
| You have an agent's id and need its full record (skills, tools, task URL) | `discover_agent(agent_id)` |

- **Route by capability.** For "review this post" or "analyse these numbers", call `search_agents` with the
  capability in plain words (`"review linkedin posts"`) instead of listing everything. Default `limit` is 5.
- Each result carries `id` (pass it as `agent_id`), `name`, `description`, `flow_id`, `status` (usually `live`),
  and the agent's `skills` and `tools`.

## Talk to an agent

`invoke_agent(agent_id, message, session?)`:
- **New conversation:** leave out `session`. Use this for the first message to an agent, and whenever the user
  changes the subject.
- **Follow-up** ("make it shorter", "now revise it", "explain that last point"): pass the `session` the previous
  answer from **that same agent** returned. One session belongs to one agent; never reuse it for another.

The answer has:
- `answer`: the agent's reply;
- `status`: `input_required` (the conversation is open and the agent waits for the user: not an error),
  `completed` or `failed`;
- `session`: keep it for follow-ups.

## Rules

- When a question matches one agent's description, route it straight there without asking which agent to use. If
  several could fit, pick the closest by description and say which one you used. Ask only when it is a real tie.
- Relay the agent's answer faithfully. Don't summarise, rewrite or add to it unless the user asks; you may add one
  line saying which agent answered.
- For a question inside an agent's domain, ask the agent rather than answering from your own knowledge.
- Send only what the user wants that agent to see. Never put tokens, keys, `.env` values or unrelated private
  data in a message.
- An agent may take actions (send email, update records). Before a message that asks it to change something, check
  that the user meant it.

## Errors

- Not signed in, or the token expired: ask the user to run `/phinite-login`, then retry.
- `failed`: tell the user what the agent reported and offer to retry with a new conversation.
- Other errors: relay the code and message as they are. To see what happened inside the run, `get_logs` with the
  workflow id when the answer includes one (`phinite-debug`).
