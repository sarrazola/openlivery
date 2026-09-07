import { setAudioModeAsync } from "expo-audio";

let recordingEnabled = false;
let pendingMode: Promise<void> = Promise.resolve();

function configure(recording: () => boolean): Promise<void> {
  const operation = pendingMode.catch(() => {}).then(async () => {
    const allowsRecording = recording();
    await setAudioModeAsync({ playsInSilentMode: true, allowsRecording, shouldPlayInBackground: false, allowsBackgroundRecording: false });
    recordingEnabled = allowsRecording;
  });
  pendingMode = operation;
  return operation;
}

/** Expo's partial iOS audio modes reset omitted fields, including recording. */
export function prepareAudioPlayback(): Promise<void> {
  return configure(() => recordingEnabled);
}

export function setRecordingMode(enabled: boolean): Promise<void> {
  return configure(() => enabled);
}
