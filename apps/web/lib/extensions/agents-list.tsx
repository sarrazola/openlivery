// Extension point of the agency's agents list.
//
// A deployment may keep some clients' agents out of the list until asked, for
// instance a client the deployment itself runs, whose many agents would crowd
// the real ones, by replacing this file at build time. The core ships it inert,
// and the list reads it through this one import.

import type { ReactNode } from "react";

export type AgentsListScope = {
  /** Clients whose agents the list leaves out while no client is picked. */
  hiddenClientIds: string[];
  /** False while the scope is still loading: the list waits for it, so the
   * hidden agents never show for a moment. */
  ready: boolean;
  /** Shown beside the client filter, to bring the hidden agents back. */
  control: ReactNode;
};

const EVERYTHING: AgentsListScope = { hiddenClientIds: [], ready: true, control: null };

export const agentsListExtensions: {
  useScope: () => AgentsListScope;
} = {
  useScope: () => EVERYTHING,
};
