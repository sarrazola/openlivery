const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');

function load(relative, mocks = {}, env = {}) {
  const filename = path.join(root, relative);
  const { outputText } = ts.transpileModule(readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  });
  const exports = {};
  const module = { exports };
  vm.runInNewContext(outputText, {
    exports, module, __dirname: path.dirname(filename), URL, AbortController,
    require: (name) => Object.hasOwn(mocks, name) ? mocks[name] : require(name),
    process: { env },
  }, { filename });
  return module.exports;
}

const sample = { server: 'https://inbox.example.com', token: 'session-token' };

test('notification targets cannot switch clients or supply a server identity', () => {
  const { notificationTarget } = load('src/notificationTarget.ts', { './notificationData': load('src/notificationData.ts') });
  assert.equal(notificationTarget({ conversation_id: 'thread-1', client_id: 'client-1' }, 'client-1'), 'thread-1');
  assert.equal(notificationTarget({ conversation_id: 'thread-1', client_id: 'client-2' }, 'client-1'), null);
  assert.equal(notificationTarget({ conversation_id: '', client_id: 'client-1' }, 'client-1'), null);
  assert.equal(notificationTarget({ url: 'https://another-server.test' }, 'client-1'), null);
});

test('system back returns to the contact directory after opening a contact case', () => {
  const { backDestination } = load('src/navigation.ts');
  assert.equal(backDestination('chat', 'contacts'), 'contacts');
  assert.equal(backDestination('chat', 'list'), 'list');
  assert.equal(backDestination('contacts', 'contacts'), 'list');
  assert.equal(backDestination('list', 'contacts'), null);
});

test('overlapping inbox pages replace stale rows and refreshes remove duplicate keys', () => {
  const { mergeConversationPages } = load('src/inbox.ts');
  const previous = [{ id: 'a', preview: 'old' }, { id: 'b', preview: 'old' }];
  const page = [{ id: 'b', preview: 'new' }, { id: 'c', preview: 'third' }];
  const merged = mergeConversationPages(previous, page);
  assert.equal(merged.length, 3);
  assert.equal(merged[1].preview, 'new');
  assert.equal(mergeConversationPages([], [...previous, ...page]).length, 3);
});
function storage({ secure = null, legacy = null, failWrite = false, failRemove = false, os = 'ios' } = {}) {
  const calls = [];
  const api = load('src/session.ts', {
    'react-native': { Platform: { OS: os } },
    '@react-native-async-storage/async-storage': {
      getItem: async () => legacy,
      removeItem: async () => {
        calls.push('remove-legacy');
        if (failRemove) throw new Error('Legacy store unavailable');
        legacy = null;
      },
      setItem: async () => { throw new Error('Plaintext writes are forbidden'); },
    },
    'expo-secure-store': {
      WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
      getItemAsync: async () => secure,
      setItemAsync: async (_key, value, options) => {
        calls.push('secure-write');
        assert.equal(options.keychainAccessible, 6);
        if (failWrite) throw new Error('Keychain unavailable');
        secure = value;
      },
      deleteItemAsync: async () => { calls.push('secure-delete'); secure = null; },
    },
  });
  return { api, calls, read: () => ({ secure, legacy }) };
}

test('legacy sessions migrate to encrypted storage before plaintext is removed', async () => {
  const fixture = storage({ legacy: JSON.stringify(sample) });
  assert.equal((await fixture.api.loadStored()).token, sample.token);
  assert.deepEqual(fixture.calls, ['secure-write', 'remove-legacy']);
  assert.equal(fixture.read().legacy, null);
});

test('failed credential migration preserves the existing login and never writes plaintext', async () => {
  const fixture = storage({ legacy: JSON.stringify(sample), failWrite: true });
  assert.equal(await fixture.api.loadStored(), null);
  assert.deepEqual(fixture.calls, ['secure-write']);
  assert.ok(fixture.read().legacy);
  await assert.rejects(fixture.api.store(sample), /Keychain unavailable/);
});

test('sign-out removes encrypted and legacy credentials', async () => {
  const fixture = storage({ secure: JSON.stringify(sample), legacy: JSON.stringify(sample) });
  await fixture.api.clearStored();
  assert.deepEqual(fixture.read(), { secure: null, legacy: null });
});

test('sign-out reports legacy deletion failures instead of restoring that login on next launch', async () => {
  const fixture = storage({ secure: JSON.stringify(sample), legacy: JSON.stringify(sample), failRemove: true });
  await assert.rejects(fixture.api.clearStored(), /Legacy store unavailable/);
  assert.deepEqual(fixture.calls, ['remove-legacy']);
});

test('browser preview never persists bearer credentials', async () => {
  const fixture = storage({ os: 'web' });
  await fixture.api.store(sample);
  assert.equal((await fixture.api.loadStored()).token, sample.token);
  assert.equal(fixture.read().secure, null);
  await fixture.api.clearStored();
  assert.equal(await fixture.api.loadStored(), null);
});

test('invalid stored addresses cannot restore a credential', async () => {
  const fixture = storage({ secure: JSON.stringify({ ...sample, server: 'javascript:alert(1)' }) });
  assert.equal(await fixture.api.loadStored(), null);
});

test('brand identity is explicit and release builds reject embedded development credentials', () => {
  const config = (env) => load('app.config.ts', {}, env).default();
  assert.throws(() => config({}), /BRAND is not set/);
  assert.throws(() => config({ BRAND: '../example' }), /filename/);
  assert.throws(() => config({ BRAND: 'example', NODE_ENV: 'production', EXPO_PUBLIC_DEV_PASSWORD: 'fixture' }), /must not contain/);
  assert.throws(() => config({ BRAND: 'example', APP_VARIANT: 'production', EXPO_PUBLIC_DEV_SERVER: 'http:\/\/localhost' }), /must not contain/);
  assert.throws(() => config({ BRAND: 'example', EAS_BUILD_PROFILE: 'production', APP_VARIANT: 'development' }), /network policy/);
  const resolved = config({ BRAND: 'example', NODE_ENV: 'production' });
  assert.equal(resolved.ios.bundleIdentifier, 'com.example.inbox');
  assert.ok(resolved.plugins.some((plugin) => Array.isArray(plugin) && plugin[0] === 'expo-secure-store'));
  assert.ok(resolved.plugins.some((plugin) => Array.isArray(plugin) && plugin[0] === 'expo-splash-screen'));
  assert.equal(resolved.plugins.find((plugin) => Array.isArray(plugin) && plugin[0] === 'expo-notifications')[1].mode, 'production');
  assert.equal(resolved.ios.entitlements['aps-environment'], 'production');
  assert.equal(config({ BRAND: 'example', APP_VARIANT: 'development' }).plugins.find((plugin) => Array.isArray(plugin) && plugin[0] === 'expo-notifications')[1].mode, 'development');
  assert.equal(config({ BRAND: 'example', APP_VARIANT: 'development' }).ios.entitlements['aps-environment'], 'development');
  const mixedEnvironment = config({ BRAND: 'example', NODE_ENV: 'production', APP_VARIANT: 'development' });
  assert.equal(mixedEnvironment.plugins.find((plugin) => Array.isArray(plugin) && plugin[0] === './plugins/withNetworkPolicy')[1].allowLocalHttp, false);
});

test('native Xcode app versions follow the selected identity without changing another target or signing', () => {
  const application = { PRODUCT_BUNDLE_IDENTIFIER: '"com.example.inbox"', MARKETING_VERSION: '0.1', CURRENT_PROJECT_VERSION: '2', DEVELOPMENT_TEAM: 'TEAMKEEP' };
  const tests = { PRODUCT_BUNDLE_IDENTIFIER: 'com.example.inbox.tests', MARKETING_VERSION: '0.1', CURRENT_PROJECT_VERSION: '2' };
  const plugin = load('plugins/withIosBuildIdentity.js', {
    'expo/config-plugins': {
      withXcodeProject: (config, action) => action({
        ...config,
        modResults: { pbxXCBuildConfigurationSection: () => ({ app: { buildSettings: application }, app_comment: 'Release', tests: { buildSettings: tests } }) },
      }),
    },
  });
  plugin({ version: '1.2.3', ios: { bundleIdentifier: 'com.example.inbox', buildNumber: '7' } });
  assert.equal(application.MARKETING_VERSION, '1.2.3');
  assert.equal(application.CURRENT_PROJECT_VERSION, '7');
  assert.equal(application.DEVELOPMENT_TEAM, 'TEAMKEEP');
  assert.equal(tests.MARKETING_VERSION, '0.1');
  assert.equal(tests.CURRENT_PROJECT_VERSION, '2');
});

test('publishers can opt into native plugins and invalid plugin lists fail configuration', () => {
  const brand = JSON.parse(readFileSync(path.join(root, 'brands/example.json'), 'utf8'));
  const config = (nativePlugins) => load('app.config.ts', {
    'node:fs': { readFileSync: () => JSON.stringify({ ...brand, nativePlugins }) },
  }, { BRAND: 'example' }).default();
  assert.ok(config(['./plugins/withPublisherNotifications']).plugins.includes('./plugins/withPublisherNotifications'));
  assert.throws(() => config('./plugins/withPublisherNotifications'), /nativePlugins/);
  assert.throws(() => config([null]), /nativePlugins/);
  assert.throws(() => config(null), /nativePlugins/);
});

test('native release network policy disables the template HTTP exceptions on both platforms', () => {
  const plugin = load('plugins/withNetworkPolicy.js', {
    'expo/config-plugins': {
      AndroidConfig: { Manifest: { getMainApplicationOrThrow: (manifest) => manifest.application } },
      withAndroidManifest: (config, action) => {
        const mod = action({ modResults: { application: { $: {} } } });
        config.androidPolicy = mod.modResults.application.$['android:usesCleartextTraffic'];
        return config;
      },
      withInfoPlist: (config, action) => {
        const mod = action({ modResults: { NSAppTransportSecurity: { NSAllowsArbitraryLoads: true, NSExceptionDomains: { localhost: {} } } } });
        config.iosPolicy = mod.modResults.NSAppTransportSecurity;
        return config;
      },
    },
  });
  const release = plugin({});
  assert.equal(release.androidPolicy, 'false');
  assert.equal(release.iosPolicy.NSAllowsArbitraryLoads, false);
  assert.equal(release.iosPolicy.NSAllowsLocalNetworking, false);
  assert.equal(release.iosPolicy.NSExceptionDomains.localhost, undefined);
  const development = plugin({}, { allowLocalHttp: true });
  assert.equal(development.androidPolicy, 'true');
  assert.equal(development.iosPolicy.NSAllowsArbitraryLoads, true);
});

function push({ os = 'android', device = true, granted = true, permissionWait, registerWait } = {}) {
  const calls = [];
  let rotate;
  const api = load('src/push.ts', {
    'react-native': { Platform: { OS: os } },
    'expo-device': { isDevice: device },
    './api': {
      registerDevice: async (_server, _session, value) => { calls.push(`register:${value.token}`); await registerWait; },
      forgetDevice: async (_server, _session, token) => { calls.push(`forget:${token}`); },
    },
    './i18n': { strings: () => ({ notifications: { channelName: 'Messages' } }) },
    'expo-notifications': {
      setNotificationHandler: () => {},
      AndroidImportance: { HIGH: 4 },
      IosAuthorizationStatus: { PROVISIONAL: 3, EPHEMERAL: 4 },
      getPermissionsAsync: async () => { calls.push('permission'); await permissionWait; return { granted, canAskAgain: false }; },
      getDevicePushTokenAsync: async () => { calls.push('native-token'); return { data: 'first' }; },
      setNotificationChannelAsync: async () => { calls.push('channel'); },
      addPushTokenListener: (listener) => { rotate = listener; return { remove: () => { calls.push('unsubscribe'); } }; },
    },
  });
  return { api, calls, rotate: (token) => rotate({ data: token }) };
}
const session = { push: { enabled: true, provider: 'webhook' } };

test('Android creates its channel before permission and token requests', async () => {
  const fixture = push();
  const result = await fixture.api.enablePush(sample.server, session);
  assert.equal(result.status, 'registered');
  assert.deepEqual(fixture.calls, ['channel', 'permission', 'native-token', 'register:first']);
});

test('disabled push and simulators do not prompt or register', async () => {
  const fixture = push({ device: false });
  assert.equal((await fixture.api.enablePush(sample.server, session)).status, 'unavailable');
  assert.deepEqual(fixture.calls, []);
  assert.equal((await fixture.api.enablePush(sample.server, { push: { enabled: false } })).status, 'off');
});

test('denied notifications do not register the device', async () => {
  const fixture = push({ granted: false });
  assert.equal((await fixture.api.enablePush(sample.server, session)).status, 'denied');
  assert.deepEqual(fixture.calls, ['channel', 'permission']);
});

test('token rotation registers the new native token and listener cleans up', async () => {
  const fixture = push();
  const registered = [];
  const cleanup = fixture.api.watchPushToken(sample.server, session, (token) => registered.push(token));
  fixture.rotate('rotated');
  await new Promise(setImmediate);
  assert.deepEqual(registered, ['rotated']);
  await cleanup();
  assert.deepEqual(fixture.calls, ['register:rotated', 'unsubscribe', 'forget:rotated']);
});

test('sign-out cancels a pending permission dialog without late server registration', async () => {
  let finishPermission;
  const permissionWait = new Promise((resolve) => { finishPermission = resolve; });
  const fixture = push({ os: 'ios', permissionWait });
  const stop = fixture.api.startPushSession(sample.server, session);
  await new Promise(setImmediate);
  await stop();
  finishPermission();
  await new Promise(setImmediate);
  assert.equal(fixture.calls.some((call) => call.startsWith('register:')), false);
});

test('push cleanup waits for in-flight registration before removing the old account token', async () => {
  let finishRegistration;
  const registerWait = new Promise((resolve) => { finishRegistration = resolve; });
  const fixture = push({ registerWait });
  const stop = fixture.api.startPushSession(sample.server, session);
  await new Promise(setImmediate);
  let stopped = false;
  const stopping = stop().then(() => { stopped = true; });
  await new Promise(setImmediate);
  assert.equal(stopped, false);
  assert.ok(fixture.calls.includes('register:first'));
  assert.equal(fixture.calls.includes('forget:first'), false);
  finishRegistration();
  await stopping;
  assert.equal(fixture.calls.at(-1), 'forget:first');
  await stop();
  assert.equal(fixture.calls.filter((call) => call === 'forget:first').length, 1);
});

test('push cleanup unregisters every rotated token before a new session can start', async () => {
  const fixture = push();
  const stop = fixture.api.startPushSession(sample.server, session);
  await new Promise(setImmediate);
  fixture.rotate('second');
  fixture.rotate('third');
  await stop();
  assert.ok(fixture.calls.includes('forget:first'));
  assert.ok(fixture.calls.includes('forget:second'));
  assert.ok(fixture.calls.includes('forget:third'));
});
