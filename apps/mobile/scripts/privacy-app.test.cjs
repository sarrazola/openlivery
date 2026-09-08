const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync, existsSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { create, act } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;

function deferred() { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; }
const server = 'https://workspace.test';
const makeSession = (user = 'operator-a', version = 'v1') => ({
  token: `token-${user}`, client_id: 'client-a', user_id: user, user_name: user, portal_slug: 'portal', api_version: 3,
  branding: { brand_color: '#3456ab', client_name: 'Workspace' }, push: { enabled: true, provider: 'native' },
  privacy: { version, destinations: [{ kind: 'ai', name: 'Configured service', host: 'processor.workspace.test', capabilities: ['conversation'] }] },
});

async function fixture({ consent = false, initialNotification = false, stopWait } = {}) {
  const root = path.resolve(__dirname, '..');
  const storage = new Map(), cache = new Map(), access = new Map(), appListeners = new Set(), backListeners = new Set();
  const calls = { resume: [], listMounts: [], chatMounts: [], push: [], stopped: [], conversations: [], alerts: [], draftsCleared: 0 };
  let current = makeSession(), responses = [], failRemoval = false, notificationListener;
  const notification = { notification: { request: { identifier: 'notification-a', content: { data: { client_id: 'client-a', conversation_id: 'case-a' } } } } };
  class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
  const native = {
    ...Object.fromEntries(['ActivityIndicator', 'Pressable', 'StatusBar', 'Text', 'View'].map((name) => [name, name])),
    Platform: { OS: 'ios' }, StyleSheet: { create: (value) => value, hairlineWidth: 1 },
    Alert: { alert: (...args) => { calls.alerts.push(args); } },
    AppState: { currentState: 'active', addEventListener: (_event, fn) => { appListeners.add(fn); return { remove: () => appListeners.delete(fn) }; } },
    BackHandler: { addEventListener: (_event, fn) => { backListeners.add(fn); return { remove: () => backListeners.delete(fn) }; } },
  };
  function list(props) {
    React.useEffect(() => { calls.listMounts.push(props.session.token); }, []);
    return React.createElement('Conversations', props);
  }
  function chat(props) {
    React.useEffect(() => { calls.chatMounts.push(props.conversation.id); }, []);
    return React.createElement('Chat', props);
  }
  const api = {
    ApiError,
    setSessionAccess: (session, allowed) => { access.set(session.token, allowed); },
    resumeSession: async (_server, token) => { calls.resume.push(token); return responses.length ? responses.shift() : current; },
    getConversation: async (_server, session, id) => {
      calls.conversations.push({ id, token: session.token, allowed: access.get(session.token) });
      if (!access.get(session.token)) throw new ApiError('Permission required', 428);
      return { id, client_id: session.client_id, channel: 'widget', mode: 'human', status: 'open' };
    },
  };
  const strings = { inbox: { title: 'Inbox', contacts: 'Contacts', signOut: 'Sign out', reconnectTitle: 'Reconnect', reconnectBody: 'Retry connection', retry: 'Retry', notificationUnavailable: 'Unavailable' }, errors: { generic: 'Error' } };
  const mocks = {
    react: React, 'react-native': native, '@expo/vector-icons': { Ionicons: 'Icon' },
    'react-native-safe-area-context': { SafeAreaProvider: 'SafeAreaProvider', SafeAreaView: 'SafeAreaView', useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) },
    'expo-splash-screen': { hide() {} },
    'expo-secure-store': { WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'device', getItemAsync: async (key) => storage.get(key) || null, setItemAsync: async (key, value) => { storage.set(key, value); }, deleteItemAsync: async (key) => { if (failRemoval && key === 'inbox.session.v2') throw new Error('Keychain unavailable'); storage.delete(key); } },
    '@react-native-async-storage/async-storage': { getItem: async () => null, removeItem: async () => {} },
    'expo-notifications': { getLastNotificationResponseAsync: async () => initialNotification ? notification : null, clearLastNotificationResponseAsync: async () => {}, addNotificationResponseReceivedListener: (fn) => { notificationListener = fn; return { remove() {} }; } },
  };
  const files = {
    'src/api.ts': api, 'src/i18n.ts': { useStrings: () => strings }, 'src/workspaceStrings.ts': { workspaceStrings: () => ({ title: 'Workspace' }) },
    'src/theme.ts': { useColors: () => ({}), useIsDark: () => false, readableBrand: (color) => color },
    'src/components/Composer.tsx': { clearComposerDrafts: () => { calls.draftsCleared += 1; } },
    'src/screens/PrivacyScreen.tsx': { PrivacyScreen: (props) => React.createElement('Privacy', props) },
    'src/screens/SignInScreen.tsx': { SignInScreen: (props) => React.createElement('SignIn', props) },
    'src/screens/ConversationsScreen.tsx': { ConversationsScreen: list }, 'src/screens/ChatScreen.tsx': { ChatScreen: chat },
    'src/screens/ContactsScreen.tsx': { ContactsScreen: 'Contacts' }, 'src/screens/WorkspaceScreen.tsx': { WorkspaceScreen: 'Workspace' },
    'src/push.ts': { startPushSession: (_server, session) => {
      calls.push.push({ token: session.token, allowed: access.get(session.token) });
      let stopping;
      return () => stopping ||= (async () => { await stopWait; calls.stopped.push(session.token); })();
    } },
  };
  function load(relative) {
    const filename = path.resolve(root, relative), key = path.relative(root, filename);
    if (files[key]) return files[key];
    if (cache.has(filename)) return cache.get(filename);
    const { outputText } = ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    });
    const module = { exports: {} }; cache.set(filename, module.exports);
    vm.runInNewContext(outputText, { exports: module.exports, module, console, URL, __DEV__: false, require: (name) => {
      if (Object.hasOwn(mocks, name)) return mocks[name];
      if (!name.startsWith('.')) return require(name);
      const base = path.resolve(path.dirname(filename), name);
      return load(['.ts', '.tsx', '.js'].map((extension) => base + extension).find(existsSync));
    } }, { filename });
    return module.exports;
  }
  const sessionStorage = load('src/session.ts'), permissions = load('src/privacyConsent.ts');
  await sessionStorage.store({ server, token: current.token });
  if (consent) await permissions.acceptConsent(server, current);
  const App = load('App.tsx').default;
  let tree;
  return {
    calls, access, storage, permissions,
    get session() { return current; }, set session(value) { current = value; },
    queueResume: (promise) => { responses.push(promise); },
    failCredentialRemoval: () => { failRemoval = true; },
    async mount() { await act(async () => { tree = create(React.createElement(App)); }); },
    async unmount() { await act(async () => tree.unmount()); },
    screen: (name) => tree.root.findAllByType(name)[0],
    async state(value) { await act(async () => { native.AppState.currentState = value; for (const fn of [...appListeners]) fn(value); }); },
    async notify() { await act(async () => notificationListener(notification)); },
    back: () => [...backListeners].reverse().some((fn) => fn()),
  };
}

test('unapproved startup does not mount inbox, start push or open notification content; declining stays closed', async () => {
  const f = await fixture({ initialNotification: true }); await f.mount();
  assert.ok(f.screen('Privacy')); assert.equal(f.back(), true);
  assert.deepEqual([f.calls.listMounts.length, f.calls.push.length, f.calls.conversations.length], [0, 0, 0]);
  await act(async () => f.screen('Privacy').props.onDecline());
  assert.ok(f.screen('SignIn'));
  assert.deepEqual([f.calls.listMounts.length, f.calls.push.length, f.calls.conversations.length], [0, 0, 0]);
  await f.unmount();
});

test('explicit acceptance allows inbox, notification navigation and push for that session', async () => {
  const f = await fixture({ initialNotification: true }); await f.mount();
  await act(async () => f.screen('Privacy').props.onAccept());
  assert.ok(f.screen('Chat')); assert.equal(f.calls.listMounts.length, 1);
  assert.equal(f.calls.push.length, 1); assert.equal(f.calls.push[0].allowed, true);
  assert.equal(f.calls.conversations.length, 1); assert.equal(f.calls.conversations[0].allowed, true);
  assert.equal(await f.permissions.hasConsent(server, f.session), true);
  await f.unmount();
});

test('stored permission restores the matching account and inactive permission dialogs preserve the composer screen', async () => {
  const f = await fixture({ consent: true }); await f.mount();
  assert.ok(f.screen('Conversations')); assert.equal(f.screen('Privacy'), undefined);
  await act(async () => f.screen('Conversations').props.onOpen({ id: 'case-a' }));
  await f.state('inactive'); await f.state('active');
  assert.ok(f.screen('Chat')); assert.equal(f.calls.chatMounts.length, 1);
  assert.equal(f.calls.resume.length, 1); assert.equal(f.access.get(f.session.token), true);
  await f.unmount();
});

test('foreground validation blocks access and a changed disclosure requires new consent', async () => {
  const f = await fixture({ consent: true }); await f.mount();
  const pending = deferred(); f.queueResume(pending.promise);
  await f.state('background'); await f.state('active');
  assert.equal(f.screen('Conversations'), undefined); assert.equal(f.access.get(f.session.token), false);
  await f.notify(); assert.equal(f.calls.conversations.length, 0);
  await act(async () => pending.resolve(makeSession('operator-a', 'v2')));
  assert.ok(f.screen('Privacy')); assert.equal(f.screen('Privacy').props.accepted, false);
  assert.equal(f.access.get(f.session.token), false); assert.equal(f.calls.push.length, 1);
  await f.unmount();
});

test('a stale foreground response cannot reopen access after another background transition', async () => {
  const f = await fixture({ consent: true }); await f.mount();
  const pending = deferred(); f.queueResume(pending.promise);
  await f.state('background'); await f.state('active'); await f.state('background');
  await act(async () => pending.resolve(f.session));
  assert.equal(f.access.get(f.session.token), false);
  assert.equal(f.screen('Conversations'), undefined);
  await f.unmount();
});

test('withdrawing consent cannot restore access when credential removal fails', async () => {
  const f = await fixture({ consent: true }); await f.mount();
  await act(async () => f.screen('Conversations').props.onPrivacy());
  f.failCredentialRemoval();
  await act(async () => f.screen('Privacy').props.onDecline());
  assert.equal(await f.permissions.hasConsent(server, f.session), false);
  assert.equal(f.access.get(f.session.token), false);
  assert.equal(f.screen('Conversations'), undefined);
  await f.unmount();
});

test('old push cleanup finishes before a different account can register and new account needs its own consent', async () => {
  const stopped = deferred(), f = await fixture({ consent: true, stopWait: stopped.promise }); await f.mount();
  await act(async () => f.screen('Conversations').props.onSignOut());
  assert.equal(f.screen('SignIn'), undefined); assert.equal(f.access.get(f.session.token), false);
  await act(async () => stopped.resolve());
  assert.ok(f.screen('SignIn')); assert.deepEqual(f.calls.stopped, ['token-operator-a']);
  f.session = makeSession('operator-b');
  await act(async () => f.screen('SignIn').props.onSignedIn(server, f.session));
  assert.ok(f.screen('Privacy')); assert.equal(f.calls.push.length, 1);
  await act(async () => f.screen('Privacy').props.onAccept());
  assert.ok(f.screen('Conversations')); assert.equal(f.calls.push.length, 2);
  assert.equal(f.calls.push[1].token, 'token-operator-b'); assert.equal(f.calls.push[1].allowed, true);
  await f.unmount();
});
