"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, type KeyboardEvent, type TextareaHTMLAttributes } from "react";

type Props = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  /** Lines the field grows to before it scrolls inside. */
  maxRows?: number;
};

/** A chat composer field: one line at rest, grows with the text up to
 * `maxRows`, then scrolls inside. Enter submits the surrounding form and
 * Shift+Enter inserts a line break, the way chat apps do. A caller's own
 * onKeyDown runs first and can claim Enter (a picker, for example) by calling
 * preventDefault. Height is refit on every render as well as on input, so a
 * form reset or a programmatic `value = ""` shrinks it back on the next
 * render. */
export const GrowingTextarea = forwardRef<HTMLTextAreaElement, Props>(function GrowingTextarea({ maxRows = 6, onInput, onKeyDown, style, ...rest }, ref) {
  const inner = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => inner.current as HTMLTextAreaElement);

  const fit = useCallback(() => {
    const el = inner.current;
    if (!el) return;
    const styles = getComputedStyle(el);
    const line = parseFloat(styles.lineHeight) || 20;
    const chrome = parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom) + parseFloat(styles.borderTopWidth) + parseFloat(styles.borderBottomWidth);
    const max = Math.round(line * maxRows + chrome);
    el.style.height = "auto";
    const wanted = el.scrollHeight;
    el.style.height = `${Math.min(wanted, max)}px`;
    const capped = wanted > max;
    el.style.overflowY = capped ? "auto" : "hidden";
    // Styled so the bar stays visible while the text runs past the cap:
    // overlay scrollbars only show while scrolling, which hides the overflow.
    if (capped) el.dataset.overflow = "true"; else delete el.dataset.overflow;
  }, [maxRows]);

  useEffect(fit);

  useEffect(() => {
    const form = inner.current?.form;
    if (!form) return;
    const onReset = () => requestAnimationFrame(fit);
    form.addEventListener("reset", onReset);
    return () => form.removeEventListener("reset", onReset);
  }, [fit]);

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    onKeyDown?.(event);
    if (event.defaultPrevented) return;
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  function handleInput(event: Parameters<NonNullable<Props["onInput"]>>[0]) {
    fit();
    onInput?.(event);
  }

  return <textarea ref={inner} rows={1} {...rest} style={{ ...style, resize: "none" }} onInput={handleInput} onKeyDown={handleKeyDown} />;
});
