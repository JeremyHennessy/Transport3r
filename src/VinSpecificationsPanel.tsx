import { useEffect,useRef,useState } from 'react';
import { loadVinSpecifications } from './vinSpecifications';

export function VinSpecifications({vin}:{vin:string}) {
  const [result,setResult]=useState<Awaited<ReturnType<typeof loadVinSpecifications>>|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const generation=useRef(0);
  useEffect(()=>()=>{generation.current++;},[vin]);
  async function load() {
    const request=++generation.current;setResult(null);setError('');setBusy(true);
    try{const value=await loadVinSpecifications(vin);if(request===generation.current)setResult(value);}
    catch(cause){if(request===generation.current)setError(cause instanceof Error?cause.message:String(cause));}
    finally{if(request===generation.current)setBusy(false);}
  }
  return <section className="t3-window-panel" data-testid="vin-specifications"><h3>Vehicle specifications · NHTSA</h3><p>Decode this observed VIN using manufacturer-submitted NHTSA vPIC information.</p><button className="t3-button secondary" type="button" onClick={()=>void load()}>{busy?'Loading — retry lookup':'Load NHTSA specifications'}</button>{busy&&<p role="status">Contacting NHTSA…</p>}{error&&<p role="alert">Specifications unavailable: {error}</p>}
    {result&&result.vin===vin.trim().toUpperCase()&&<><p className={result.warning?'c360-review warning':''}><strong>{result.warning?'Decoder warning — verify the recorded VIN':'VIN decoded without a reported decoder error'}</strong>{result.warning&&<span> · {result.message}</span>}</p><dl className="t3-vin-specs">{result.fields.map(field=><div key={field.key}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}</dl>{!result.fields.length&&<p>No specifications returned.</p>}<p>Retrieved {result.acquiredAt} · <a href={result.url} target="_blank" rel="noreferrer">NHTSA response ↗</a></p></>}
    <p className="c360-disclaimer">Decoded specifications describe manufacturer information, not current condition, ownership, insurance, or unrepaired recalls. Model year is decoded by NHTSA; it is not inferred from inspection date. Fields returned with a decoder warning are provisional.</p><a href="https://vpic.nhtsa.dot.gov/api/" target="_blank" rel="noreferrer">About NHTSA vPIC ↗</a>
  </section>;
}
