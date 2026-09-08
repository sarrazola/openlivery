const { withXcodeProject } = require("expo/config-plugins");

// Keep Xcode's displayed app versions aligned with Expo's generated Info.plist.
module.exports = function withIosBuildIdentity(config) {
  return withXcodeProject(config, (mod) => {
    const configurations = mod.modResults.pbxXCBuildConfigurationSection();
    for (const value of Object.values(configurations)) {
      const settings = value?.buildSettings;
      if (!settings) continue;
      const bundleId = String(settings.PRODUCT_BUNDLE_IDENTIFIER || "").replace(/^"|"$/g, "");
      if (bundleId !== config.ios?.bundleIdentifier) continue;
      settings.MARKETING_VERSION = config.version;
      settings.CURRENT_PROJECT_VERSION = config.ios.buildNumber;
    }
    return mod;
  });
};
