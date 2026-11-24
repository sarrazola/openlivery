"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** What a settings section hands the page that saves it: one call that
 * validates and stores the section and says whether it went through. A section
 * that fails shows its own error and scrolls into view. */
export type SectionHandle = { save: () => Promise<boolean> };

/** Whether an editor's state differs from what was last loaded or saved.
 * `key` is that state serialized; `markSaved()` adopts the state of the next
 * render as the saved one. `onChange` hears every flip, and a last `false`
 * when the editor goes away. */
export function useUnsaved(key: string, ready: boolean, onChange?: (dirty: boolean) => void) {
  const [baseline, setBaseline] = useState<string | null>(null);
  const notify = useRef(onChange);
  useEffect(() => { notify.current = onChange; });
  useEffect(() => { if (ready && baseline === null) setBaseline(key); }, [ready, baseline, key]);
  const dirty = ready && baseline !== null && baseline !== key;
  useEffect(() => { notify.current?.(dirty); }, [dirty]);
  useEffect(() => () => notify.current?.(false), []);
  const markSaved = useCallback(() => setBaseline(null), []);
  return { dirty, markSaved };
}
