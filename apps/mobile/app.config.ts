import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ExpoConfig } from "expo/config";

/**
 * Builds the app identity from a brand file.
 *
 * The same source produces the official app and an agency's own build. Which
 * one comes out is decided by BRAND at build time:
 *
 *   BRAND=example  npx expo start
 *   BRAND=myagency eas build --platform ios
 *
 * There is deliberately no default: forgetting to pick a brand fails the
 * build instead of quietly compiling another publisher's identity.
 */

type HostedPreset = {
  label: string;
  workspaceLabel: string;
  workspacePlaceholder: string;
  serverTemplate: string;
  otherLabel: string;
};

type Brand = {
  name: string;
  slug: string;
  scheme: string;
  iosBundleIdentifier: string;
  androidPackage: string;
  primaryColor: string;
  defaultServer?: string;
  version?: string;
  iosBuildNumber?: string;
  iosAppleTeamId?: string;
  androidVersionCode?: number;
  androidGoogleServicesFile?: string;
  easProjectId?: string;
  owner?: string;
  nativePlugins?: string[];
  /**
   * A preset for a service whoever publishes this build runs, offered on the
   * sign-in screen alongside typing an address. No brand file here has one:
   * an open-source build should not point at somebody's hosted product.
   */
  hosted?: HostedPreset;
};

function loadBrand(): Brand {
  const name = process.env.BRAND;
  if (!name) {
    throw new Error(
      "BRAND is not set. Pick a brand file from brands/, e.g. BRAND=example npx expo start.\n" +
        "Publishing your own app? Copy brands/example.json and use your own identifiers.",
    );
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(name)) throw new Error("BRAND must be a filename from brands/.");
  const path = join(__dirname, "brands", `${name}.json`);
  let raw: string;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    throw new Error(`No brand file at brands/${name}.json`);
  }
  const brand = JSON.parse(raw) as Brand;
  for (const key of ["name", "slug", "scheme", "iosBundleIdentifier", "androidPackage", "primaryColor"] as const) {
    if (typeof brand[key] !== "string" || !brand[key].trim()) throw new Error(`brands/${name}.json is missing "${key}"`);
  }
  if (!/^#[0-9a-f]{6}$/i.test(brand.primaryColor)) throw new Error("primaryColor must be a six-digit hex color.");
  if (brand.nativePlugins !== undefined && (!Array.isArray(brand.nativePlugins) || brand.nativePlugins.some((plugin) => typeof plugin !== "string" || !plugin.trim()))) {
    throw new Error("nativePlugins must be a list of Expo config plugin paths.");
  }
  if (brand.hosted && (!brand.hosted.label || !/^https:\/\/[^/]*\{workspace\}[^/]+$/.test(brand.hosted.serverTemplate))) {
    throw new Error("hosted must have a label and an HTTPS serverTemplate containing {workspace}.");
  }
  return brand;
}

export default (): ExpoConfig => {
  if (process.env.EAS_BUILD_PROFILE === "production" && process.env.APP_VARIANT === "development") {
    throw new Error("The production profile cannot enable the development network policy.");
  }
  const release = process.env.NODE_ENV === "production" || process.env.APP_VARIANT === "production" || process.env.EAS_BUILD_PROFILE === "production";
  if (release && Object.keys(process.env).some((key) => key.startsWith("EXPO_PUBLIC_DEV_") && process.env[key])) {
    throw new Error("Release builds must not contain EXPO_PUBLIC_DEV_* credentials. Remove development variables before building.");
  }
  const brand = loadBrand();
  return {
    name: brand.name,
    slug: brand.slug,
    scheme: brand.scheme,
    version: brand.version || "0.2.0",
    ...(brand.owner ? { owner: brand.owner } : {}),
    orientation: "portrait",
    icon: "./assets/icon.png",
    // Follow the phone. An app that stays white while the system is dark is
    // the first thing that reads as a web page in a wrapper.
    userInterfaceStyle: "automatic",
    ios: {
      supportsTablet: true,
      bundleIdentifier: brand.iosBundleIdentifier,
      buildNumber: brand.iosBuildNumber || "1",
      entitlements: { "aps-environment": release ? "production" : "development" },
      ...(brand.iosAppleTeamId || process.env.APPLE_TEAM_ID ? { appleTeamId: brand.iosAppleTeamId || process.env.APPLE_TEAM_ID } : {}),
      config: { usesNonExemptEncryption: false },
    },
    android: {
      package: brand.androidPackage,
      versionCode: brand.androidVersionCode || 1,
      ...(process.env.GOOGLE_SERVICES_JSON || brand.androidGoogleServicesFile
        ? { googleServicesFile: process.env.GOOGLE_SERVICES_JSON || brand.androidGoogleServicesFile }
        : {}),
      softwareKeyboardLayoutMode: "resize",
      adaptiveIcon: {
        backgroundColor: brand.primaryColor,
        foregroundImage: "./assets/android-icon-foreground.png",
        backgroundImage: "./assets/android-icon-background.png",
        monochromeImage: "./assets/android-icon-monochrome.png",
      },
      predictiveBackGestureEnabled: false,
    },
    web: { favicon: "./assets/favicon.png" },
    // Notifications are optional and server-driven: the app only asks for a
    // token when the server it is pointed at says it can deliver one (see
    // src/push.ts). The plugin is still declared here because the entitlement
    // and the notification icon have to be baked into the build either way.
    plugins: [
      ["expo-dev-client", { toolsButton: false, showMenuAtLaunch: false }],
      ["expo-notifications", { color: brand.primaryColor, defaultChannel: "messages", mode: release ? "production" : "development" }],
      ["expo-secure-store", { configureAndroidBackup: true, faceIDPermission: false }],
      "expo-sharing",
      "expo-image",
      ["./plugins/withNetworkPolicy", { allowLocalHttp: !release && process.env.APP_VARIANT === "development" }],
      "./plugins/withIosBuildIdentity",
      ["expo-splash-screen", {
        image: "./assets/splash-icon.png",
        imageWidth: 180,
        backgroundColor: "#ffffff",
        dark: { backgroundColor: "#111827" },
      }],
      // iOS refuses to show a permission prompt without a reason string, and
      // rejects a build that asks for these without one.
      [
        "expo-image-picker",
        {
          photosPermission: "Lets you send a photo from your library into a conversation.",
          cameraPermission: "Lets you take a photo to send into a conversation.",
        },
      ],
      [
        "expo-audio",
        {
          microphonePermission: "Lets you record a voice note to send into a conversation.",
          enableBackgroundRecording: false,
          enableBackgroundPlayback: false,
        },
      ],
      ...(brand.nativePlugins || []),
    ],
    extra: {
      // Pre-fills the server field. The colour here only covers the sign-in
      // screen; once signed in the agency's own colour arrives with the session.
      defaultServer: brand.defaultServer || "",
      primaryColor: brand.primaryColor,
      // Absent unless a brand file adds one, in which case sign-in offers it as
      // a choice instead of only asking for an address.
      hosted: brand.hosted || null,
      ...(brand.easProjectId ? { eas: { projectId: brand.easProjectId } } : {}),
    },
  };
};
