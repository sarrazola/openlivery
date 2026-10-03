// Extension points of the app shell.
//
// A deployment may put something of its own where the sidebar names the
// workspace: a notice, a menu. It does so by replacing this file at build
// time; the core ships it inert, and the shell reads it through this one
// import so nothing else in it has to change.

import type { ComponentType, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import type { Lang } from "@/lib/i18n";
import type { User } from "@/types";

export type WorkspaceLabel = ComponentType<{
  user: User;
  /** The label the shell would have drawn, to render as is or wrap. */
  children: ReactNode;
}>;

/** A sidebar entry a deployment adds, after the core's and before Settings. */
export type ExtraNavEntry = { href: string; label: string; icon: LucideIcon };

export const appShellExtensions: {
  /** Rendered in place of the sidebar's workspace label, or nothing. */
  WorkspaceLabel: WorkspaceLabel | null;
  /** Sidebar entries for the deployment's own pages, in the given language
   * (NEXT_PUBLIC_EXTRA_NAV does the same without code, in one language). */
  extraNav: ((lang: Lang) => ExtraNavEntry[]) | null;
} = {
  WorkspaceLabel: null,
  extraNav: null,
};
