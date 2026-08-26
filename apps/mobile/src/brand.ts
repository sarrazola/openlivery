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
  /** Address to build, with `{workspace}` replaced by what was typed. */
  serverTemplate: string;
  /**
   * What the service calls a customer, when "agency" is wrong for it. Left out
   * of most brand files: the interface already has translated wording for it,
   * and anything set here is one language only.
   */
  workspaceLabel?: string;
  workspacePlaceholder?: string;
};

type Extra = {
  defaultServer?: string;
  primaryColor?: string;
  hosted?: HostedPreset | null;
};

const extra = (Constants.expoConfig?.extra || {}) as Extra;

/**
 * A preset is only usable if it carries every field the screen needs.
 *
 * Checking the shape rather than the presence matters: the native project
 * stores this config in a property list, which has no null, so a brand file
 * without a preset arrives as an empty object. Trusting that would put an empty
 * switcher and an unlabelled field on the sign-in screen of every build that
 * has no hosted service - which is every build from this repository.
 */
function usablePreset(value: HostedPreset | null | undefined): HostedPreset | null {
  if (!value) return null;
  const named = typeof value.label === "string" && value.label.length > 0;
  const addressable = typeof value.serverTemplate === "string" && value.serverTemplate.includes("{workspace}");
  return named && addressable ? value : null;
}

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
export const HOSTED: HostedPreset | null = usablePreset(extra.hosted);

/** Turn what someone typed into the address their workspace lives at. */
export function hostedServerFor(workspace: string): string {
  if (!HOSTED) return "";
  return HOSTED.serverTemplate.replace("{workspace}", workspace.trim().toLowerCase());
}
