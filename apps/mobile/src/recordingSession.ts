/** Serializes recording transitions so system foreground events cannot resume a paused microphone. */
export type RecordingDevice = {
  record: () => void;
  isRecording: () => boolean;
  duration: () => number;
  pause: () => void;
  stop: () => Promise<void>;
  uri: () => string | null;
  enable: (value: boolean) => Promise<void>;
};

export class RecordingUnavailableError extends Error {
  constructor() { super("The native microphone did not start."); }
}

export function createRecordingSession(device: RecordingDevice) {
  let active = false;
  let paused = false;
  let revision = 0;
  let finishing: Promise<string | null> | null = null;
  let recordedDuration = 0;

  function retainDuration() {
    const duration = device.duration();
    if (Number.isFinite(duration)) recordedDuration = Math.max(recordedDuration, duration);
  }

  return {
    isActive: () => active,
    isPaused: () => paused,
    duration: () => recordedDuration,
    start() {
      recordedDuration = 0;
      device.record();
      active = true;
      paused = false;
      revision += 1;
      // Expo's status timer can run even when AVAudioRecorder.record() fails.
      // Its direct isRecording property reads the native recorder instead.
      if (!device.isRecording()) throw new RecordingUnavailableError();
    },
    async pause() {
      if (!active || paused) return;
      revision += 1;
      retainDuration();
      device.pause();
      paused = true;
      // Expo's iOS foreground callback resumes paused recorders when this is
      // enabled. A manual pause must disable that path until an explicit resume.
      await device.enable(false);
    },
    async resume(): Promise<boolean> {
      if (!active || !paused) return false;
      const operation = ++revision;
      await device.enable(true);
      if (operation !== revision || !active) {
        await device.enable(false);
        return false;
      }
      device.record();
      paused = false;
      return true;
    },
    finish(): Promise<string | null> {
      if (finishing) return finishing;
      if (!active) return Promise.resolve(null);
      revision += 1;
      active = false;
      paused = false;
      finishing = (async () => {
        try {
          // Read the URI while the recorder is alive. Releasing the screen can
          // free its native object before stop() finishes.
          retainDuration();
          const uri = device.uri();
          await device.stop();
          return uri;
        }
        finally { await device.enable(false); }
      })().finally(() => { finishing = null; });
      return finishing;
    },
  };
}
