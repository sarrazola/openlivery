import assert from "node:assert/strict";
import { test } from "node:test";
import { createRecordingSession, type RecordingDevice } from "../src/recordingSession";

function fixture() {
  let enabled = true;
  let recording = false;
  let recordCalls = 0;
  let stopCalls = 0;
  const device: RecordingDevice = {
    record: () => { assert.equal(enabled, true); recording = true; recordCalls += 1; },
    isRecording: () => recording,
    duration: () => 3.2,
    pause: () => { recording = false; },
    stop: async () => { recording = false; stopCalls += 1; },
    uri: () => "file:///recordings/original.m4a",
    enable: async (value) => { enabled = value; },
  };
  return { device, session: createRecordingSession(device), state: () => ({ enabled, recording, recordCalls, stopCalls }) };
}

test("a manual pause disables native foreground auto-resume until explicitly resumed", async () => {
  const { session, state } = fixture();
  session.start();
  await session.pause();
  assert.deepEqual(state(), { enabled: false, recording: false, recordCalls: 1, stopCalls: 0 });
  assert.equal(session.isPaused(), true);
  assert.equal(await session.resume(), true);
  assert.deepEqual(state(), { enabled: true, recording: true, recordCalls: 2, stopCalls: 0 });
});

test("an interrupted paused note is finalized once and retains its original file", async () => {
  const { session, state } = fixture();
  session.start();
  await session.pause();
  const results = await Promise.all([session.finish(), session.finish()]);
  assert.deepEqual(results, ["file:///recordings/original.m4a", "file:///recordings/original.m4a"]);
  assert.deepEqual(state(), { enabled: false, recording: false, recordCalls: 1, stopCalls: 1 });
  assert.equal(session.isActive(), false);
  assert.equal(await session.resume(), false);
});

test("background finalization cancels an in-flight resume before it can reopen the microphone", async () => {
  const { device, session, state } = fixture();
  session.start();
  await session.pause();
  const enable = device.enable;
  let release!: () => void;
  device.enable = async (value) => {
    if (value) await new Promise<void>((resolve) => { release = resolve; });
    await enable(value);
  };
  const resume = session.resume();
  assert.equal(await session.finish(), "file:///recordings/original.m4a");
  release();
  assert.equal(await resume, false);
  assert.deepEqual(state(), { enabled: false, recording: false, recordCalls: 1, stopCalls: 1 });
});

test("finalization disables recording even when the native stop fails", async () => {
  const { device, session, state } = fixture();
  session.start();
  device.stop = async () => { throw new Error("Audio interruption"); };
  await assert.rejects(session.finish(), /Audio interruption/);
  assert.equal(state().enabled, false);
  assert.equal(session.isActive(), false);
});

test("finalizing an idle recorder does not create a draft or touch the native object", async () => {
  const { device, session, state } = fixture();
  device.uri = () => { throw new Error("Native object already released"); };
  assert.equal(await session.finish(), null);
  assert.equal(state().stopCalls, 0);
});

test("an unavailable native file still disables recording during interruption", async () => {
  const { device, session, state } = fixture();
  session.start();
  device.uri = () => { throw new Error("Native object already released"); };
  await assert.rejects(session.finish(), /Native object already released/);
  assert.equal(state().enabled, false);
  assert.equal(session.isActive(), false);
});
