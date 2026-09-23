// Extension points of the agent editor's tools tab.
//
// A deployment that manages some of an agent's tools on its behalf (a
// directory of connectors it provisions, say) keeps those out of the custom
// tools list and renders its own section under it. It does so by replacing
// this file at build time; the core ships it inert, and the editor reads it
// through this one import so nothing else in the page has to change.

import type { ComponentType } from "react";
import type { AgentTool } from "@/types";

export type ManagedToolsSection = ComponentType<{
  agentId: string;
  /** The deployment changed the agent's tools; the editor reloads its list. */
  onToolsChange: () => void;
}>;

export const agentToolsExtensions: {
  /** True for a tool the deployment manages elsewhere: hidden from the custom list, still counted. */
  isManaged: (tool: AgentTool) => boolean;
  /** Rendered under the custom tools list, or nothing. */
  ManagedSection: ManagedToolsSection | null;
} = {
  isManaged: () => false,
  ManagedSection: null,
};
