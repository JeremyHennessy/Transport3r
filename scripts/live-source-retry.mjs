// Retain transient acquisition failures without retrying data validation failures.
export async function queryLiveSource(query, { requireTotal = false, wait = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
  const attempts = [];
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const slice = await query();
      if (requireTotal && slice.total === null) throw new Error('Source total unavailable');
      attempts.push({ attempt, status: 'PASS' });
      return { slice, attempts };
    } catch (error) {
      attempts.push({ attempt, status: 'FAIL', error: error.message });
      const transient = /request failed:|returned HTTP (429|5\d\d)|^Source total unavailable$|^fetch failed$|^Request timed out after \d+s$|^HTTP (429|5\d\d)$/.test(error.message);
      if (!transient || attempt === 3) {
        error.attempts = attempts;
        throw error;
      }
      await wait(attempt * 1000);
    }
  }
}
