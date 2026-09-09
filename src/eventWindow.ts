export type EventWindow = { start: string; end: string };

export function validateEventWindow(window: EventWindow): EventWindow {
  for (const value of [window.start, window.end]) {
    if (!/^20\d{2}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0,10) !== value) throw new Error('Enter valid calendar dates between 2000 and 2099.');
  }
  if (window.start > window.end) throw new Error('Start date must be on or before end date.');
  if (Date.parse(window.end)-Date.parse(window.start)>1096*86400000) throw new Error('Choose a window of three years or less.');
  return { start: window.start, end: window.end };
}

// These two daily files publish YYYYMMDD text. SMS uses a different date encoding.
export const DAILY_DATE_FIELDS: Record<string,string> = { 'fx4q-ay7w':'insp_date', 'aayw-vxb3':'report_date' };
