import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ExpoConfig } from "expo/config";

/**
 * Builds the app identity from a brand file.
 *
 * The same source produces the official app and an agency's own build. Which
 * one comes out is decided by BRAND at build time:
 *
 *   BRAND=openlivery npx expo start
 *   BRAND=myagency  eas build --platform ios
 *
 * There is deliberately no default. An agency publishing to the stores must
 * ship its own name, bundle identifier and icon - a build that is a copy of
 * another one with a different colour is what store review rejects - so
 * forgetting to pick a brand fails the build instead of quietly producing a
 * duplicate.
 */

type Brand = {
  name: string;
  slug: string;
  scheme: string;
  iosBundleIdentifier: string;
  androidPackage: string;
  primaryColor: string;
  defaultServer?: string;
};

function loadBrand(): Brand {
  const name = process.env.BRAND;
  if (!name) {
    throw new Error(
      "BRAND is not set. Pick a brand file from brands/, e.g. BRAND=openlivery npx expo start.\n" +
        "Publishing your own app? Copy brands/_template.json and use your own identifiers.",
    );
  }
  const path = join(__dirname, "brands", `${name}.json`);
  let raw: string;
  try {
    raw = readFileSync(path, "utf8");
  } catch {
    throw new Error(`No brand file at brands/${name}.json`);
  }
  const brand = JSON.parse(raw) as Brand;
  for (const key of ["name", "slug", "scheme", "iosBundleIdentifier", "androidPackage", "primaryColor"] as const) {
    if (!brand[key]) throw new Error(`brands/${name}.json is missing "${key}"`);
  }
  return brand;
}

export default (): ExpoConfig => {
  const brand = loadBrand();
  return {
    name: brand.name,
    slug: brand.slug,
    scheme: brand.scheme,
    version: "0.1.0",
    orientation: "portrait",
    icon: "./assets/icon.png",
    userInterfaceStyle: "light",
    ios: {
      supportsTablet: true,
      bundleIdentifier: brand.iosBundleIdentifier,
    },
    android: {
      package: brand.androidPackage,
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
    plugins: [["expo-notifications", { color: brand.primaryColor }]],
    extra: {
      // Pre-fills the server field. The colour here only covers the sign-in
      // screen; once signed in the agency's own colour arrives with the session.
      defaultServer: brand.defaultServer || "",
      primaryColor: brand.primaryColor,
    },
  };
};
