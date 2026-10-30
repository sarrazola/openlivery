# Phone calls

> Leer en español: [phone-calls.md](../es/phone-calls.md)

A **voice agent** answers a client's phone number. ElevenLabs Agents runs each call: it hears the caller, decides when they finished or cut in, thinks with one of its own models and speaks with the agent's voice. OpenLivery is where the agent is configured. It writes the agent's instructions, business details, Q&A, greeting, voice, model and tools into ElevenLabs, and writes them again whenever they change, so a turn of the call never waits on OpenLivery. The number stays at your phone carrier, Twilio or Telnyx, and is pointed at ElevenLabs when you add the line.

Every call becomes a conversation in the inbox, on the **Phone** channel, with its transcript, duration, cost and a summary.

## What you need

Under **Settings**, in **Phone calls**:

- **ElevenLabs**: an API key with write access to Agents, Voices and Webhooks. Saving it checks the key against ElevenLabs and names any permission it lacks. ElevenLabs bills the minutes and the model to that account.
- **Phone carrier**: your **Twilio** Account SID and Auth Token, or a **Telnyx** API key. The numbers you already have there are listed when you add a line. The carrier bills the calls to that account.

OpenLivery must be reachable from the internet over HTTPS, because ElevenLabs calls it back during and after every call. It uses `PHONE_PUBLIC_URL`, or `FRONTEND_URL` when that is empty (see [configuration](configuration.md)).

## The voice agent

Create it from **Agents › New agent** and choose **Voice**. A voice agent has the same instructions, business details, knowledge, contact details to collect and tools as a chat agent, plus:

- **Voice**: paste the ID of any voice from the ElevenLabs voice library (open a voice's menu and choose *Copy voice ID*). The card plays the voice's sample. Without one, the agent speaks with a conversational voice in its language.
- **Greeting**: said word for word as soon as the call is answered.
- **Model**: **Realtime Mini** (the default, the fastest to answer), **Realtime Max** (reasons before answering, for longer instructions) or **Gemini 3.8 Flash**. All run at ElevenLabs next to the voice.
- **Put the call through to a person**: a number, with its country, and when to pass the call. The caller stays on the line while the call is transferred. Left empty, the agent tells the caller someone will call back and hands the case to a person in the inbox.

The agent's working hours, follow-ups and the playground do not apply to calls: the phone is answered at any hour.

## Adding a line

On the client's **Channels**, add a phone number: pick the voice agent and one of the carrier's numbers. OpenLivery creates the line's agent at ElevenLabs, imports the number there (a Twilio number directly, a Telnyx number through a SIP connection it creates), and the line shows **Connected**. If something fails, the line says why and **Connect again** retries.

## During a call

When a call comes in, before the greeting, ElevenLabs asks OpenLivery who is calling. The agent receives what the chat would know about the caller: the client's contact for that number with the details already on file, the details it still has to ask for, and a recap of their last case. Contacts belong to each client, so a number known to one client is a new contact for another. The conversation opens at that moment, so the call is in the inbox while it rings. ElevenLabs documents this callback for Twilio numbers; on a call that does not make it, the agent starts without that context.

During the call the agent can use tools, each one a request from ElevenLabs to OpenLivery:

- **Knowledge**: short documents ride in the agent's prompt. When they add up to more than about 16,000 characters, the agent looks them up with `search_knowledge` instead.
- **Contact details**: `save_contact_field` saves what the caller says (their name, e-mail or one of the client's own fields) on their contact, as in a chat.
- **Hand over to a person**: without a transfer number, `escalate_to_human` leaves the case open for the team, assigned the way escalation assigns chats, and the conversation is not closed when the call ends.
- **The agent's own tools**: its HTTP tools and MCP servers ([custom tools](custom-tools.md)) work on calls too. While a slow tool runs, the voice says something natural so the line is never silent.

Each request carries a secret that ElevenLabs keeps in the workspace's secrets; OpenLivery stores only its hash.

## When the call ends

ElevenLabs reports the finished call, signed with the webhook's secret. The conversation gets the transcript, each turn at the moment it was said, with the tools the agent used, and the call's duration, end reason and summary. The cost (the voice minutes and the model, in USD) is recorded as one usage record with purpose `call`, so [reports](reports.md) list it next to the chat replies. The conversation is closed unless a person has it. A call that never connects closes its conversation with the reason.

Each call is its own conversation, never a reply in an open case. No audio is stored.

## Keeping the line in step

A change to anything the line carries is written into ElevenLabs on its own: the agent's instructions, business details, voice, greeting, model and transfer number, the client's name and timezone, and, a couple of seconds after the last edit, its documents, Q&A, tools, contact details and escalation rules. A tool that did not change is not written again.

## Limits

- One ElevenLabs account and one account per carrier per agency.
- Inbound calls only.
- The agent's working hours do not apply to calls.
