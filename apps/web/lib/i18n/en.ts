// English dictionary (source of truth), composed from per-area modules under
// ./dicts. `es.ts` mirrors this exact shape. Access with dotted paths, e.g.
// t("nav.clients"), t("clients.list.title").
import { core } from "./dicts/core";
import { home } from "./dicts/home";
import { clients } from "./dicts/clients";
import { agents } from "./dicts/agents";
import { channels } from "./dicts/channels";
import { social } from "./dicts/social";
import { settings } from "./dicts/settings";
import { playground } from "./dicts/playground";
import { portal } from "./dicts/portal";
import { inbox } from "./dicts/inbox";
import { tools } from "./dicts/tools";

export const en = {
  ...core.en,
  home: home.en,
  clients: clients.en,
  agents: agents.en,
  channels: channels.en,
  social: social.en,
  settings: settings.en,
  playground: playground.en,
  portal: portal.en,
  inbox: inbox.en,
  tools: tools.en,
};

export type Dictionary = typeof en;
