const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync, existsSync } = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { create, act } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;
const root = path.resolve(__dirname, '..');

function fixture({ replyWait, failSend = false, nativeRecording = true, capturedSeconds = 3.2, resetTimeOnPause = false, conversationOverrides = {}, fileToPick } = {}) {
  const calls = { texts: [], files: [], modes: [], alerts: [], permission: 0, recording: false, paused: false, played: 0, stops: 0 };
  let detail = {
    id: 'case-1', client_id: 'client-1', status: 'open', mode: 'human', channel: 'widget',
    title: 'Customer', contact_name: 'Customer', contact_id: null, created_at: new Date().toISOString(),
    external_chat_id: 'customer', messages: [], team_id: null,
    ...conversationOverrides,
  };
  const session = { client_id: 'client-1', user_id: 'user-1', user_name: 'Agent', slug: 'example', token: 'test', branding: { brand_color: '#3456ab', client_name: 'Example' } };
  const player = { play: () => { calls.played += 1; }, pause() {}, seekTo: async () => {} };
  const recorder = {
    uri: 'file:///original-note.m4a', prepareToRecordAsync: async () => {},
    get isRecording() { return nativeRecording && calls.recording; },
    get currentTime() { return calls.recording || (calls.paused && !resetTimeOnPause) ? capturedSeconds : 0; },
    record: () => { calls.recording = true; calls.paused = false; },
    pause: () => { calls.recording = false; calls.paused = true; },
    stop: async () => { calls.recording = false; calls.paused = false; calls.stops += 1; },
  };
  const api = {
    ApiError: class extends Error {},
    getConversation: async () => detail, markRead: async () => {},
    listCannedReplies: async () => [{ id: 'hello', shortcut: 'hello', content: 'Hello {contact_name}', updated_at: '' }],
    setMode: async (_server, _session, _id, mode) => { detail = { ...detail, mode }; return detail; },
    reply: async (_server, _session, _id, text) => {
      calls.texts.push(text);
      await replyWait;
      if (failSend) throw new Error('Offline');
      return detail;
    },
    replyWithFile: async (_server, _session, _id, file, caption) => { calls.files.push({ file, caption }); return detail; },
    attachmentUrl: () => 'https://example.test/audio', authHeaders: () => ({ Authorization: 'Bearer test' }),
  };
  class FakeFile { exists = true; size = 10; uri = 'file:///incoming.m4a'; }
  class FakeDirectory { exists = true; }
  const audio = {
    AudioModule: { requestRecordingPermissionsAsync: async () => { calls.permission += 1; return { granted: true }; } },
    RecordingPresets: { HIGH_QUALITY: {} },
    useAudioRecorder: () => recorder,
    useAudioRecorderState: () => ({ isRecording: calls.recording, durationMillis: 33000 }),
    useAudioPlayer: () => player,
    useAudioPlayerStatus: () => ({ isLoaded: true, duration: 3.2, playing: false, currentTime: 0 }),
    setAudioModeAsync: async (mode) => { calls.modes.push(mode); },
  };
  const native = {
    ...Object.fromEntries(['ActivityIndicator', 'FlatList', 'KeyboardAvoidingView', 'Pressable', 'Text', 'TextInput', 'View', 'Modal'].map((name) => [name, name])),
    StyleSheet: { create: (styles) => styles, hairlineWidth: 1 }, Platform: { OS: 'ios' },
    Alert: { alert: (title, body) => { calls.alerts.push({ title, body }); } }, AppState: { currentState: 'active', addEventListener: () => ({ remove() {} }) },
    ActionSheetIOS: { showActionSheetWithOptions: (options, callback) => { calls.attachMenu = { ...options, callback }; } }, useColorScheme: () => 'light',
    Animated: { View: 'AnimatedView', Value: class {}, timing() {}, sequence() {}, loop: () => ({ start() {}, stop() {} }) },
  };
  const mocks = {
    react: React, 'react-native': native, '@expo/vector-icons': { Ionicons: 'Icon' },
    'expo-audio': audio, 'expo-image': { Image: 'Image' }, 'expo-image-picker': {},
    'expo-document-picker': { getDocumentAsync: async (options) => { calls.documentTypes = options.type; return fileToPick ? { canceled: false, assets: [fileToPick] } : { canceled: true }; } },
    'expo-file-system': { File: FakeFile, Directory: FakeDirectory, Paths: { cache: '/cache' } }, 'expo-sharing': {},
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0, bottom: 0 }), SafeAreaView: 'SafeAreaView' },
  };
  const cache = new Map();
  function load(relative) {
    const filename = path.resolve(root, relative);
    if (cache.has(filename)) return cache.get(filename);
    if (filename.endsWith('/src/api.ts')) return api;
    if (filename.endsWith('/src/components/ThreadSheets.tsx')) return {
      ThreadSheet: ({ visible, children }) => visible ? React.createElement('Sheet', {}, children) : null,
      ThreadAction: (props) => React.createElement('Action', props), TemplatePicker: () => null,
    };
    if (filename.endsWith('/src/rich.tsx')) return { renderRichText: (value) => value };
    const { outputText } = ts.transpileModule(readFileSync(filename, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
    });
    const module = { exports: {} };
    cache.set(filename, module.exports);
    vm.runInNewContext(outputText, {
      exports: module.exports, module, console, setTimeout, clearTimeout,
      setInterval: () => 1, clearInterval() {}, requestAnimationFrame: () => 1, cancelAnimationFrame() {},
      require: (name) => {
        if (Object.hasOwn(mocks, name)) return mocks[name];
        if (!name.startsWith('.')) return require(name);
        const base = path.resolve(path.dirname(filename), name);
        const resolved = ['.ts', '.tsx', '.js'].map((extension) => base + extension).find(existsSync);
        return load(resolved);
      },
    }, { filename });
    return module.exports;
  }
  const { ChatScreen } = load('src/screens/ChatScreen.tsx');
  let tree;
  return {
    calls, load,
    async mount() { await act(async () => { tree = create(React.createElement(ChatScreen, { server: 'https://example.test', session, conversation: detail, onBack() {} })); }); },
    async mountAudio() {
      const { AttachmentView } = load('src/components/Attachments.tsx');
      await act(async () => { tree = create(React.createElement(AttachmentView, { server: 'https://example.test', session, conversationId: 'case-1', brand: '#3456ab', outgoing: false, attachment: { id: 'audio-1', mime: 'audio/mp4', filename: 'incoming.m4a', kind: 'audio', size: 10 } })); });
    },
    async unmount() { await act(async () => { tree.unmount(); }); },
    input: () => tree.root.findByType('TextInput'),
    text: (value) => tree.root.findAllByType('Text').find((node) => node.children.join('') === value),
    button(label) {
      return tree.root.findAll((node) => (node.type === 'Pressable' || node.type === 'Action') && (node.props.accessibilityLabel === label || node.props.label === label || node.findAllByType('Text').some((text) => text.children.join('') === label)))[0];
    },
    async press(label) { await act(async () => { const button = this.button(label); assert.ok(button, `Button ${label} exists`); assert.ok(!button.props.disabled, `Button ${label} is enabled`); await button.props.onPress(); }); },
    async type(text) { await act(async () => { this.input().props.onChangeText(text); }); },
  };
}

test('a sent saved reply stays empty after handing back and taking over the case', async () => {
  const f = fixture();
  await f.mount();
  await f.press('Saved replies');
  await f.press('/hello');
  assert.equal(f.input().props.value, 'Hello Customer');
  await f.press('Send');
  assert.deepEqual(f.calls.texts, ['Hello Customer']);
  assert.equal(f.input().props.value, '');
  await f.press('Hand back');
  await f.press('Take over');
  assert.equal(f.input().props.value, '');
  await f.unmount();
});

test('editing an inserted saved reply survives a composer remount without replaying the original insertion', async () => {
  const f = fixture();
  await f.mount();
  await f.press('Saved replies');
  await f.press('/hello');
  await f.type('Personalized, unsent message');
  await f.press('Hand back');
  await f.press('Take over');
  assert.equal(f.input().props.value, 'Personalized, unsent message');
  await f.unmount();
});

test('a successful send that finishes after navigation removes its saved draft', async () => {
  let release;
  const f = fixture({ replyWait: new Promise((resolve) => { release = resolve; }) });
  await f.mount();
  await f.type('Send before leaving');
  let sending;
  await act(async () => { sending = f.button('Send').props.onPress(); });
  await f.unmount();
  await act(async () => { release(); await sending; });
  await f.mount();
  assert.equal(f.input().props.value, '');
  assert.equal(f.calls.texts.length, 1);
  await f.unmount();
});

test('failed sends remain available after navigation for a deliberate retry', async () => {
  const f = fixture({ failSend: true });
  await f.mount();
  await f.type('Keep this draft');
  await f.press('Send');
  await f.unmount();
  await f.mount();
  assert.equal(f.input().props.value, 'Keep this draft');
  await f.unmount();
});

test('a late successful send cannot erase a newer draft from another mount', async () => {
  let release;
  const f = fixture({ replyWait: new Promise((resolve) => { release = resolve; }) });
  await f.mount();
  await f.type('First message');
  let sending;
  await act(async () => { sending = f.button('Send').props.onPress(); });
  await f.unmount();
  await f.mount();
  await f.type('Next message');
  await act(async () => { release(); await sending; });
  await f.unmount();
  await f.mount();
  assert.equal(f.input().props.value, 'Next message');
  await f.unmount();
});

test('the microphone stays next to attach with text and offers playback before sending its caption', async () => {
  const f = fixture();
  await f.mount();
  await f.type('Caption for my audio');
  const attach = f.button('Add an attachment');
  const microphone = f.button('Record audio');
  assert.equal(microphone.parent, attach.parent);
  assert.equal(attach.parent.children.indexOf(microphone), attach.parent.children.indexOf(attach) + 1);
  assert.equal(f.text('Record audio'), undefined);
  await f.press('Record audio');
  assert.equal(f.calls.permission, 1);
  assert.equal(f.calls.recording, true);
  await f.press('Stop and review audio');
  assert.equal(f.calls.recording, false);
  assert.equal(f.calls.files.length, 0);
  assert.equal(f.input().props.value, 'Caption for my audio');
  await f.press('Play voice note');
  assert.equal(f.calls.played, 1);
  await f.press('Send voice note');
  assert.equal(f.calls.files[0].caption, 'Caption for my audio');
  assert.equal(f.calls.files[0].file.uri, 'file:///original-note.m4a');
  assert.equal(f.input().props.value, '');
  await f.unmount();
});

test('a false native recording property stops Expo\'s artificial timer and never stages an attachment', async () => {
  const f = fixture({ nativeRecording: false });
  await f.mount();
  await f.type('Keep my text');
  await f.press('Record audio');
  assert.equal(f.calls.stops, 1);
  assert.equal(f.calls.recording, false);
  assert.equal(f.calls.modes.at(-1).allowsRecording, false);
  assert.equal(f.button('Stop and review audio'), undefined);
  assert.equal(f.button('Send voice note'), undefined);
  assert.equal(f.input().props.value, 'Keep my text');
  assert.match(f.calls.alerts[0].body, /microphone is unavailable/);
  await f.unmount();
});

test('a 33-second status timer cannot turn 139 milliseconds of captured audio into a sendable note', async () => {
  const f = fixture({ capturedSeconds: 0.139 });
  await f.mount();
  await f.type('Keep the caption');
  await f.press('Record audio');
  assert.ok(f.text('0:33'));
  await f.press('Stop and review audio');
  assert.ok(f.text('Recording is too short. Try again.'));
  assert.equal(f.button('Send voice note'), undefined);
  assert.equal(f.calls.files.length, 0);
  assert.equal(f.input().props.value, 'Keep the caption');
  await f.unmount();
});

test('a genuine paused note retains its captured duration even if native time resets before finalization', async () => {
  const f = fixture({ capturedSeconds: 3.2, resetTimeOnPause: true });
  await f.mount();
  await f.press('Record audio');
  await f.press('Pause recording');
  assert.equal(f.calls.recording, false);
  await f.press('Stop and review audio');
  assert.ok(f.button('Play voice note'));
  await f.press('Send voice note');
  assert.equal(f.calls.files[0].file.uri, 'file:///original-note.m4a');
  await f.unmount();
});

test('playing received audio on a cold session enables playback in silent mode', async () => {
  const f = fixture();
  await f.mountAudio();
  await f.press('Play voice note');
  assert.equal(f.calls.played, 1);
  assert.equal(f.calls.modes.length, 1);
  assert.equal(f.calls.modes[0].playsInSilentMode, true);
  assert.equal(f.calls.modes[0].allowsRecording, false);
  await f.unmount();
});

test('preparing playback preserves an active recorder even when mode requests overlap', async () => {
  const f = fixture();
  const { setRecordingMode, prepareAudioPlayback } = f.load('src/audioSession.ts');
  await Promise.all([setRecordingMode(true), prepareAudioPlayback()]);
  assert.deepEqual(f.calls.modes.map((mode) => mode.allowsRecording), [true, true]);
  await Promise.all([setRecordingMode(false), prepareAudioPlayback()]);
  assert.deepEqual(f.calls.modes.map((mode) => mode.allowsRecording), [true, true, false, false]);
});

const socialThread = {
  channel: 'instagram', reply_window_open: false, reply_window_until: '2000-01-01T00:00:00Z',
  human_reply_window_open: true, human_reply_window_until: '2999-01-01T00:00:00Z', reply_block_reason: null,
  channel_capabilities: { text: true, image: true, audio: true, video: true, file: true, quotes: false, reactions: false, templates: false },
};

test('Instagram human support window shows its policy and sends a manual reply without templates', async () => {
  const f = fixture({ conversationOverrides: socialThread });
  await f.mount();
  assert.ok(f.text('Human replies only'));
  assert.equal(f.button('Send template'), undefined);
  await f.type('A person is answering this request.');
  await f.press('Send');
  assert.deepEqual(f.calls.texts, ['A person is answering this request.']);
  await f.unmount();
});

test('closed Messenger policy exposes neither a composer nor a template reopening action', async () => {
  const f = fixture({ conversationOverrides: { ...socialThread, channel: 'messenger', human_reply_window_open: false } });
  await f.mount();
  assert.ok(f.text('Replies unavailable'));
  assert.equal(f.button('Send template'), undefined);
  assert.equal(f.button('Add an attachment'), undefined);
  assert.equal(f.button('Record audio'), undefined);
  assert.equal(f.button('Send'), undefined);
  assert.equal(f.calls.texts.length, 0);
  await f.unmount();
});

test('a revoked social account shows the authorization recovery hint despite a future human window', async () => {
  const f = fixture({ conversationOverrides: { ...socialThread, reply_block_reason: 'authorization_expired' } });
  await f.mount();
  assert.ok(f.text('Authorize this account again from the channel settings on the web.'));
  assert.equal(f.button('Record audio'), undefined);
  await f.unmount();
});

test('capability-disabled microphone cannot request permission even through a stale native callback', async () => {
  const f = fixture({ conversationOverrides: { ...socialThread, channel_capabilities: { text: true } } });
  await f.mount();
  assert.equal(f.button('Record audio').props.disabled, true);
  assert.equal(f.button('Add an attachment').props.disabled, true);
  await act(async () => { await f.button('Record audio').props.onPress(); });
  assert.equal(f.calls.permission, 0);
  await f.type('Text is still supported.');
  await f.press('Send');
  assert.deepEqual(f.calls.texts, ['Text is still supported.']);
  await f.unmount();
});

test('Instagram rejects a non-PDF document returned by the native picker without uploading it', async () => {
  const f = fixture({ conversationOverrides: socialThread, fileToPick: { uri: 'file:///report.doc', name: 'report.doc', mimeType: 'application/msword' } });
  await f.mount();
  await f.press('Add an attachment');
  await act(async () => { f.calls.attachMenu.callback(f.calls.attachMenu.options.indexOf('Choose a file')); });
  assert.ok(f.calls.documentTypes.includes('application/pdf'));
  assert.equal(f.calls.documentTypes.includes('*/*'), false);
  assert.ok(f.text('This channel does not support this attachment. Instagram documents must be PDF files.'));
  assert.equal(f.button('Remove attachment'), undefined);
  assert.equal(f.calls.files.length, 0);
  await f.unmount();
});
