const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { create, act } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;

function fixture({ accepted = false, disclosed = true, language = 'en', acceptWait } = {}) {
  const calls = { accept: 0, decline: 0, back: 0, links: [], alerts: [] };
  const mocks = {
    react: React,
    'react-native': {
      ...Object.fromEntries(['ActivityIndicator', 'Pressable', 'ScrollView', 'Text', 'View'].map((name) => [name, name])),
      StyleSheet: { create: (value) => value, hairlineWidth: 1 },
      Linking: { openURL: async (url) => { calls.links.push(url); } },
      Alert: { alert: (...args) => { calls.alerts.push(args); } },
    },
    '@expo/vector-icons': { Ionicons: 'Icon' },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) },
    'expo-localization': { getLocales: () => [{ languageCode: language }] },
    '../theme': { contrastOn: () => '#fff', readableBrand: (color) => color, useColors: () => ({}), useIsDark: () => false },
    '../privacy': { privacyUrl: () => 'https://workspace.test/privacy', supportUrl: () => 'https://workspace.test/support' },
  };
  function load(relative) {
    const filename = path.resolve(__dirname, '..', relative);
    const { outputText } = ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    });
    const module = { exports: {} };
    vm.runInNewContext(outputText, { exports: module.exports, module, console, URL, require: (name) => {
      if (Object.hasOwn(mocks, name)) return mocks[name];
      if (name === '../privacyStrings') return load('src/privacyStrings.ts');
      return require(name);
    } }, { filename });
    return module.exports;
  }
  const { PrivacyScreen } = load('src/screens/PrivacyScreen.tsx');
  const session = {
    branding: { brand_color: '#3456ab', client_name: 'Workspace' },
    ...(disclosed ? { privacy: { version: 'v1', destinations: [{ kind: 'ai', name: 'Configured provider', host: 'processor.workspace.test', capabilities: ['conversation', 'image', 'audio'] }] } } : {}),
  };
  let tree;
  return {
    calls,
    async mount() { await act(async () => { tree = create(React.createElement(PrivacyScreen, {
      session, accepted, server: 'https://workspace.test',
      onAccept: async () => { calls.accept += 1; await acceptWait; },
      onDecline: async () => { calls.decline += 1; }, onBack: () => { calls.back += 1; },
    })); }); },
    button: (id) => tree.root.findAllByType('Pressable').find((node) => node.props.testID === id),
    texts: () => tree.root.findAllByType('Text').map((node) => node.children.join('')),
    links: () => tree.root.findAllByType('Pressable').filter((node) => node.props.accessibilityRole === 'link'),
    async unmount() { await act(async () => tree.unmount()); },
  };
}

test('privacy acceptance is explicit, shows server destinations, and cannot be submitted twice', async () => {
  let finish;
  const f = fixture({ acceptWait: new Promise((resolve) => { finish = resolve; }) });
  await f.mount();
  assert.equal(f.calls.accept, 0);
  assert.ok(f.texts().includes('Configured provider'));
  assert.ok(f.texts().includes('processor.workspace.test'));
  assert.ok(f.texts().some((text) => text.includes('Conversation text and history') && text.includes('Photos') && text.includes('Audio')));
  const onPress = f.button('privacy-accept').props.onPress;
  await act(async () => { onPress(); onPress(); });
  assert.equal(f.calls.accept, 1);
  assert.equal(f.button('privacy-decline').props.disabled, true);
  await act(async () => { finish(); });
  await f.unmount();
});

test('a server without a privacy disclosure cannot be accepted, but support and sign-out remain available', async () => {
  const f = fixture({ disclosed: false, language: 'es' });
  await f.mount();
  assert.equal(f.button('privacy-accept').props.disabled, true);
  await act(async () => { f.button('privacy-accept').props.onPress(); });
  assert.equal(f.calls.accept, 0);
  assert.ok(f.texts().some((text) => text.includes('Pide a tu administrador que lo actualice')));
  await act(async () => { await f.links()[1].props.onPress(); });
  assert.deepEqual(f.calls.links, ['https://workspace.test/support']);
  await act(async () => { f.button('privacy-decline').props.onPress(); });
  assert.equal(f.calls.decline, 1);
  await f.unmount();
});

test('reviewing accepted privacy information offers withdrawal without reaccepting or silently signing out', async () => {
  const f = fixture({ accepted: true });
  await f.mount();
  assert.equal(f.button('privacy-accept'), undefined);
  await act(async () => { f.button('privacy-decline').props.onPress(); });
  assert.equal(f.calls.decline, 0);
  const buttons = f.calls.alerts[0][2];
  assert.equal(buttons[0].style, 'cancel');
  await act(async () => { buttons[1].onPress(); });
  assert.equal(f.calls.decline, 1);
  assert.equal(f.calls.accept, 0);
  await f.unmount();
});
