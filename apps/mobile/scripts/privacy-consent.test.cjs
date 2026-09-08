const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function fixture({ failure = false, os = 'ios' } = {}) {
  let saved = null;
  let deletes = 0;
  const module = { exports: {} };
  const source = ts.transpileModule(readFileSync(path.join(__dirname, '../src/privacyConsent.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInNewContext(source, { module, exports: module.exports, URL, require: (name) => {
    if (name === 'react-native') return { Platform: { OS: os } };
    if (name === 'expo-secure-store') return {
      WHEN_UNLOCKED_THIS_DEVICE_ONLY: 6,
      getItemAsync: async () => saved,
      setItemAsync: async (_key, value, options) => { assert.equal(options.keychainAccessible, 6); if (failure) throw Error('Keychain unavailable'); saved = value; },
      deleteItemAsync: async () => { saved = null; deletes += 1; },
    };
    throw Error(`Unexpected module ${name}`);
  } });
  return { api: module.exports, saved: () => saved, deletes: () => deletes };
}
const server = 'https://inbox.example.test';
const session = { token: 'token', client_id: 'client-1', user_id: 'operator-1', privacy: { version: '1:revision', destinations: [{ kind: 'ai', name: 'OpenAI', host: 'api.openai.com', capabilities: ['conversation', 'audio'] }] } };

test('permission is scoped to account, workspace, policy and actual destinations', async () => {
  const f = fixture();
  assert.equal(await f.api.hasConsent(server, session), false);
  await f.api.acceptConsent(server, session);
  assert.equal(await f.api.hasConsent(server + '/', { ...session, token: 'rotated-token' }), true);
  for (const other of [{ ...session, client_id: 'client-2' }, { ...session, user_id: 'operator-2' }, { ...session, privacy: { ...session.privacy, version: '2:revision' } }, { ...session, privacy: { ...session.privacy, destinations: [{ ...session.privacy.destinations[0], host: 'another.example.test' }] } }]) {
    assert.equal(await f.api.hasConsent(server, other), false);
  }
  assert.equal(await f.api.hasConsent('https://other.example.test', session), false);
  assert.ok(!f.saved().includes('token'));
});

test('withdrawal and failed secure storage never leave permission enabled', async () => {
  const f = fixture();
  await f.api.acceptConsent(server, session);
  await f.api.withdrawConsent();
  assert.equal(await f.api.hasConsent(server, session), false);
  assert.equal(f.deletes(), 1);
  const broken = fixture({ failure: true });
  await assert.rejects(broken.api.acceptConsent(server, session), /Keychain unavailable/);
  assert.equal(await broken.api.hasConsent(server, session), false);
});

test('old servers and malformed disclosure cannot be accepted', async () => {
  const f = fixture();
  for (const privacy of [undefined, { version: '', destinations: [] }, { version: '1', destinations: [{}] }]) {
    const old = { ...session, privacy };
    assert.equal(await f.api.hasConsent(server, old), false);
    await assert.rejects(f.api.acceptConsent(server, old));
  }
});

test('browser preview permission is memory only', async () => {
  const f = fixture({ os: 'web' });
  await f.api.acceptConsent(server, session);
  assert.equal(await f.api.hasConsent(server, session), true);
  assert.equal(f.saved(), null);
  await f.api.withdrawConsent();
  assert.equal(await f.api.hasConsent(server, session), false);
});
