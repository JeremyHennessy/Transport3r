import {validateRelease,type ReleaseInfo} from './integrityModel';

/** Release provenance has its own deadline, separate from warehouse availability. */
export async function loadRelease(url:string,signal:AbortSignal):Promise<ReleaseInfo> {
  // Do not require AbortSignal.any/timeout: older supported browsers lack them.
  if(signal.aborted)throw new DOMException('Release request cancelled','AbortError');
  const controller=new AbortController();
  const cancel=()=>controller.abort();
  signal.addEventListener('abort',cancel,{once:true});
  const deadline=setTimeout(()=>controller.abort(),15000);
  try {
    const response=await fetch(url,{signal:controller.signal,credentials:'omit',cache:'no-store',headers:{Accept:'application/json'}});
    if(!response.ok)throw new Error(`Release metadata returned HTTP ${response.status}`);
    const text=await response.text();
    if(text.length>256*1024)throw new Error('Release metadata exceeds its size limit');
    return validateRelease(JSON.parse(text));
  } finally {
    clearTimeout(deadline);
    signal.removeEventListener('abort',cancel);
  }
}
