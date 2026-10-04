// Browsers emit this delivery diagnostic with no Error object when a resize
// notification is deferred to the next frame. It is not an uncaught JS exception.
export function isResizeDeliveryNotice(event: {
  message: string;
  error?: unknown;
}) {
  return (
    event.error == null &&
    (event.message ===
      'ResizeObserver loop completed with undelivered notifications.' ||
      event.message === 'ResizeObserver loop limit exceeded')
  );
}

/** Vinext currently reports native resize delivery notices as JS exceptions. */
export function filterResizeNoticesFromOverlay(code: string, id: string) {
  if (!id.split('?')[0].endsWith('/vinext/dist/client/dev-error-overlay.js'))
    return null;
  const anchor = 'const err = event.error;';
  if (!code.includes(anchor)) return null;
  return code.replace(
    anchor,
    `${anchor}\n\t\tif ((${isResizeDeliveryNotice.toString()})(event)) return;`,
  );
}
