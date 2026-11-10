/** Bounded GET retries. Rate-limit recovery never changes query scope or data validation. */
export function retryAfterMilliseconds(value: string | null, now = Date.now()): number | null {
  if (value === null) return null;
  const text = value.trim();
  if (/^[0-9]+$/.test(text)) {
    const seconds = Number(text);
    return Number.isSafeInteger(seconds) && seconds <= Number.MAX_SAFE_INTEGER / 1000 ? seconds * 1000 : null;
  }
  // Do not interpret malformed numeric delays as arbitrary calendar dates.
  if (!/^[A-Za-z]{3}, \d{2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2} GMT$/.test(text)) return null;
  const date = Date.parse(text);
  return Number.isFinite(date) ? Math.max(0, date - now) : null;
}

function pause(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException('Request cancelled', 'AbortError')); return; }
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); reject(new DOMException('Request cancelled', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, milliseconds);
    signal.addEventListener('abort', abort, {once: true});
  });
}

export async function sourceJson(url: string, init: RequestInit = {}, timeoutMs = 9000): Promise<unknown> {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new Error('Positive request deadline required');
  const parent = init.signal;
  if (parent?.aborted) throw new DOMException('Request cancelled', 'AbortError');
  const controller = new AbortController();
  const cancel = () => controller.abort();
  parent?.addEventListener('abort', cancel, {once: true});
  const deadline = Date.now() + timeoutMs;
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  const retryableMethod = (init.method ?? 'GET').toUpperCase() === 'GET';
  try {
    for (let attempt = 0; ; attempt++) {
      const response = await fetch(url, {...init, signal: controller.signal});
      if (response.ok) return await response.json();
      const retryAfter = retryAfterMilliseconds(response.headers.get('retry-after'));
      const message = `HTTP ${response.status}${retryAfter === null ? '' : ` (retry-after ${retryAfter}ms)`}`;
      await response.body?.cancel();
      const delay = Math.max(retryAfter ?? 0, 500 * 2 ** attempt);
      if (!retryableMethod || ![429, 502, 503, 504].includes(response.status) || attempt >= 2 ||
          Date.now() + delay >= deadline) throw new Error(message);
      await pause(delay, controller.signal);
    }
  } catch (error) {
    if (parent?.aborted) throw new DOMException('Request cancelled', 'AbortError');
    if (timedOut) throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    throw error;
  } finally {
    clearTimeout(timer);
    parent?.removeEventListener('abort', cancel);
    controller.abort();
  }
}

export async function mapLimited<T, R>(items: T[], work: (item: T) => Promise<R>, concurrency = 4): Promise<R[]> {
  if (!Number.isSafeInteger(concurrency) || concurrency < 1) throw new Error('Positive concurrency required');
  const result: R[] = new Array(items.length);
  let next = 0;
  await Promise.all(Array.from({length: Math.min(concurrency, items.length)}, async () => {
    for (;;) {
      const index = next++;
      if (index >= items.length) return;
      result[index] = await work(items[index]);
    }
  }));
  return result;
}
