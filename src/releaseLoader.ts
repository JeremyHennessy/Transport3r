import {validateRelease,type ReleaseInfo} from './integrityModel';

/** Release provenance has its own deadline, separate from warehouse availability. */
export async function loadRelease(url:string,signal:AbortSignal):Promise<ReleaseInfo> {
  const requestSignal=AbortSignal.any([signal,AbortSignal.timeout(15000)]);
  const response=await fetch(url,{signal:requestSignal,credentials:'omit',cache:'no-store',headers:{Accept:'application/json'}});
  if(!response.ok)throw new Error(`Release metadata returned HTTP ${response.status}`);
  const text=await response.text();
  if(text.length>256*1024)throw new Error('Release metadata exceeds its size limit');
  return validateRelease(JSON.parse(text));
}
