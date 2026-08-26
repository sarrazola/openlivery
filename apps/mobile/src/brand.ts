/**
 * The identity this build was compiled with.
 *
 * `app.config.ts` reads a file from `brands/` at build time and puts the parts
 * the running app needs into `expo.extra`. Nothing here is fetched or
 * configurable at runtime - an app's identity is decided when it is built.
 */

import Constants from "expo-constants";

export type HostedPreset = {
  /** What to call the service on the sign-in screen, e.g. "Acme Cloud". */
  label: string;
  /** Field label for the part of the address that identifies the customer. */
  workspaceLabel: string;
  workspacePlaceholder: string;
  /** Address to build, with `{workspace}` replaced by what was typed. */
  serverTemplate: string;
  /** What to call the alternative, e.g. "Another server". */
  otherLabel: string;
};

type Extra = {
  defaultServer?: string;
  primaryColor?: string;
  hosted?: HostedPreset | null;
};

const extra = (Constants.expoConfig?.extra || {}) as Extra;

export const DEFAULT_SERVER = extra.defaultServer || "";
export const BRAND_COLOR = extra.primaryColor || "#2f3a4a";

/**
 * A preset for a service whoever published this build runs.
 *
 * There is none in this repository, on purpose: an open-source build should not
 * point at somebody's hosted product. A build that has one offers it as a
 * choice alongside typing an address; a build that does not just asks for the
 * address, which is what a self-hosted install wants anyway.
 */
export const HOSTED: HostedPreset | null = extra.hosted || null;

/** Turn what someone typed into the address their workspace lives at. */
export function hostedServerFor(workspace: string): string {
  if (!HOSTED) return "";
  return HOSTED.serverTemplate.replace("{workspace}", workspace.trim().toLowerCase());
}
