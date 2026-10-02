// Extension points of the app shell.
//
// A deployment may put something of its own where the sidebar names the
// workspace: a notice, a menu. It does so by replacing this file at build
// time; the core ships it inert, and the shell reads it through this one
// import so nothing else in it has to change.

import type { ComponentType, ReactNode } from "react";
import type { User } from "@/types";

export type WorkspaceLabel = ComponentType<{
  user: User;
  /** The label the shell would have drawn, to render as is or wrap. */
  children: ReactNode;
}>;

export const appShellExtensions: {
  /** Rendered in place of the sidebar's workspace label, or nothing. */
  WorkspaceLabel: WorkspaceLabel | null;
} = {
  WorkspaceLabel: null,
};
