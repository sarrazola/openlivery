const { AndroidConfig, withAndroidManifest, withInfoPlist } = require("expo/config-plugins");

/** Only a development binary may send credentials over a local HTTP connection. */
module.exports = function withNetworkPolicy(config, { allowLocalHttp = false } = {}) {
  config = withInfoPlist(config, (mod) => {
    const ats = mod.modResults.NSAppTransportSecurity || {};
    ats.NSAllowsArbitraryLoads = allowLocalHttp;
    ats.NSAllowsLocalNetworking = allowLocalHttp;
    if (!allowLocalHttp && ats.NSExceptionDomains) delete ats.NSExceptionDomains.localhost;
    mod.modResults.NSAppTransportSecurity = ats;
    return mod;
  });
  return withAndroidManifest(config, (mod) => {
    const application = AndroidConfig.Manifest.getMainApplicationOrThrow(mod.modResults);
    application.$["android:usesCleartextTraffic"] = allowLocalHttp ? "true" : "false";
    return mod;
  });
};
