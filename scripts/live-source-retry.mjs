// Retry only identified transient source failures, retaining every rejected attempt.
export function transientSourceFailure(message) {
  if(typeof message!=='string')return false;
  const status=/\bHTTP (\d{3})\b/.exec(message);
  if(status)return ['429','500','502','503','504'].includes(status[1]);
  return /(?:^|: )(?:fetch failed|Failed to fetch|NetworkError|Request timed out after \d+s|Source total unavailable)$/.test(message);
}
export function sourceRetryDelay(messages, attempt) {
  const root=messages.filter(message=>!/^(Parent inspections unavailable;|Legacy carrier\/docket bridge unavailable;)/.test(message));
  if(!root.length||root.some(message=>!transientSourceFailure(message)))return null;
  const waits=root.map(message=>Number(/\(retry-after (\d+)ms\)/.exec(message)?.[1]??0));
  if(waits.some(delay=>!Number.isSafeInteger(delay)||delay>60000))return null;
  return Math.max(attempt*1000,...waits);
}
export async function queryLiveSource(query, { requireTotal = false, wait = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
  const attempts = [];
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const slice = await query();
      if (requireTotal && slice.total === null) throw new Error('Source total unavailable');
      attempts.push({ attempt, status: 'PASS' });
      return { slice, attempts };
    } catch (error) {
      const message=error instanceof Error?error.message:String(error);
      const delay=sourceRetryDelay([message],attempt);
      attempts.push({ attempt, status: 'FAIL', error: message, retry_after_ms: attempt<3?delay:null });
      if (delay===null || attempt === 3) {
        const failure=error instanceof Error?error:new Error(message);failure.attempts = attempts;throw failure;
      }
      await wait(delay);
    }
  }
}
