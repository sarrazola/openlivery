# Dashboard

> Leer en español: [dashboard.md](../es/dashboard.md)

The dashboard is your agency's home screen — the first thing you see after signing in. It summarises activity across every client, agent and channel in one place, and adapts to a date range you pick.

## Date range

A selector in the top-right controls the window used by the charts and counters. The options are **7, 14, 30 and 90 days**, defaulting to 14. Changing it refetches the metrics for the new window.

## Next steps

Until your workspace is set up, an onboarding checklist walks you through the first tasks: create a client, create an agent, and connect a channel. The first two steps tick themselves off automatically once you have at least one client and one agent.

## Headline metrics

Four cards sit at the top, each showing a total plus a secondary line:

- **Clients** — total clients, with how many are active.
- **Agents** — total agents, with how many are active.
- **Conversations** — total conversations across all channels.
- **Channels** — total WhatsApp channels, with how many are connected.

## Activity

The activity panel plots **new conversations per day** over the selected window as a bar chart (zero-filled, so every day appears even with no traffic). Alongside it, two counters cover the same window: total **messages**, and conversations **handled by a human** — those switched to human mode so an operator answers from the inbox. See [Inbox](inbox.md).

## Top agents

A ranked list shows your busiest agents by conversation count for the window, up to five. Each row links straight to that agent. See [Agents](agents.md).

## Token usage by model

This panel breaks down consumption by model over the window, up to six models, sorted by total tokens. Each row shows the model name and a bar for its total, and the panel header shows aggregate **input** (↓) and **output** (↑) tokens for the whole window. This reflects real usage recorded per request, so it stays empty until your agents start replying.

## Recent agents

At the bottom, the five most recently created agents are listed with their client and status, plus a link to the full [Agents](agents.md) list.
