import {useEffect,useMemo,useState} from 'react';
import catalog from '../data/fmcsa_sources.json';
import {loadIntegrity,type IntegrityReport,type ReleaseInfo} from './integrityModel';
import './dataIntegrity.css';
import {loadRelease} from './releaseLoader';

const fmt = (value:number|null|undefined) => value == null ? '\u2014' : value.toLocaleString();
const time = (value:string|null|undefined) => value ? new Date(value).toLocaleString() : 'Not verified';
const queryFromHash = () => new URLSearchParams(window.location.hash.split('?')[1]??'').get('q')??'';
const api = String(import.meta.env?.VITE_EVIDENCE_API_URL??'').trim();
type ReleaseState = {kind:'loading'|'verified'|'unavailable';value:ReleaseInfo|null;error:string};
type State = {kind:'loading'|'not-configured'|'unavailable'|'verified';report:IntegrityReport|null;error:string};

export default function DataIntegrityPage(){
  const [state,setState] = useState<State>({kind:api?'loading':'not-configured',report:null,error:''});
  const [releaseState,setReleaseState] = useState<ReleaseState>({kind:'loading',value:null,error:''});
  const release=releaseState.value;
  const [version,setVersion] = useState(0),[query,setQuery] = useState(queryFromHash);
  const [copied,setCopied] = useState(false);
  useEffect(()=>{document.title='Data Integrity \u00b7 Transport3r';const changed=()=>setQuery(queryFromHash());
    window.addEventListener('hashchange',changed);return()=>window.removeEventListener('hashchange',changed);},[]);
  useEffect(()=>{
    const controller=new AbortController();let active=true;
    setState({kind:api?'loading':'not-configured',report:null,error:''});setReleaseState({kind:'loading',value:null,error:''});
    loadRelease(`${import.meta.env.BASE_URL}release-manifest.json`,controller.signal)
      .then(value=>{if(active)setReleaseState({kind:'verified',value,error:''});})
      .catch(error=>{if(active)setReleaseState({kind:'unavailable',value:null,error:error instanceof Error?error.message:'Release request failed'});});
    if(api)loadIntegrity(api,controller.signal).then(report=>{if(active)setState({kind:'verified',report,error:''});})
      .catch(error=>{if(active)setState({kind:'unavailable',report:null,error:error instanceof Error?error.message:String(error)});});
    return()=>{active=false;controller.abort();};
  },[version]);
  const report=state.report;
  const rows=useMemo(()=>catalog.filter(item=>`${item.id} ${item.name} ${item.family}`.toLowerCase().includes(query.trim().toLowerCase())),[query]);
  const byId=new Map(report?.sources.map(source=>[source.source,source])??[]);
  const duplicates=report?.sources.reduce((sum,row)=>sum+row.exact_duplicate_rows,0);
  const metadataAge=release?.metadataAt?Math.max(0,Math.floor((Date.now()-Date.parse(release.metadataAt))/86400000)):null;
  function filter(value:string){setQuery(value);const p=new URLSearchParams();if(value.trim())p.set('q',value);const target='#/integrity'+(p.size?'?'+p.toString():'');history.replaceState(null,'',target);}
  async function copy(){try{await navigator.clipboard.writeText(window.location.href);setCopied(true);}catch{setCopied(false);}}
  function download(){if(!report)return;const blob=new Blob([JSON.stringify(report,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);
    const anchor=document.createElement('a');anchor.href=url;anchor.download=`transport3r-integrity-${report.cut_id.replace(/[^a-zA-Z0-9.-]/g,'-')}.json`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  return <div className="t3-app">
    <header className="t3-topbar t3-integrity-topbar"><a className="t3-brand" href="#/overview" aria-label="Transport3r overview"><span className="t3-brand-text">Transport<span>3r</span></span></a>
      <nav className="t3-primary-nav" aria-label="Primary navigation"><a href="#/overview">Overview</a><a href="#/carriers">Carriers</a><a href="#/atlas">Atlas</a><a href="#/sources">Data Sources</a><a href="#/integrity" className="active" aria-current="page">Data Integrity</a></nav>
    </header>
    <main className="t3-main t3-integrity" data-testid="data-integrity">
      <section className="t3-integrity-hero"><div><div className="t3-eyebrow">Evidence you can trace</div><h1>Data Integrity</h1><p>Follow each official source from published rows to stored records and carrier assignments. A connection is not a reconciliation; unavailable totals stay unavailable.</p></div>
        <div className="t3-integrity-actions"><button onClick={()=>setVersion(v=>v+1)} className="t3-button primary" disabled={state.kind==='loading'}>{state.kind==='loading'?'Checking installation...':'Recheck installation'}</button><button className="t3-button secondary" onClick={copy}>{copied?'View link copied':'Copy view link'}</button></div>
      </section>
      <section className={'t3-integrity-status '+state.kind} role="status" aria-live="polite">
        <strong>{state.kind==='verified'?'Installed warehouse matches its independent audit':state.kind==='loading'?'Checking the installed evidence service':state.kind==='not-configured'?'Nationwide audit service is not connected':'Nationwide audit could not be verified'}</strong>
        <p>{state.kind==='verified'?'Source counts, exact duplicates, row-level carrier links and the installed warehouse SHA agree. This does not certify actuarial risk or today\u2019s live source publications.':state.kind==='not-configured'?'This public site does not currently have an evidence API configured. No nationwide totals or duplicate metrics are inferred from sample probes.':state.kind==='loading'?'The health response and audit must describe the same immutable warehouse cut.':state.error}</p>
      </section>
      <section className="t3-integrity-metrics" aria-label="Audited warehouse totals">
        {[['Source records',report?.raw_rows,'Across all source grains; not unique incidents'],['Census-resolved carriers',report?.census_carriers,'Unique positive USDOT identities in this cut'],['Sources independently audited',report?.source_count,`${catalog.length} sources are registered`],['Exact duplicate rows',duplicates,'Original columns only; not cross-source events']].map(([label,value,detail])=><article key={String(label)}><span>{label}</span><strong>{fmt(value as number|undefined)}</strong><small>{detail}</small></article>)}
      </section>
      <section className="t3-integrity-panel"><div className="t3-integrity-section"><div><div className="t3-eyebrow">Count conservation</div><h2>One source row, one accountable mapping</h2><p>These stages must reconcile within the same warehouse cut. Counts from different sources must not be added together as a fleet, crash or claims total.</p></div>{report&&<button className="t3-button secondary" onClick={download}>Export verified audit</button>}</div>
        <div className="t3-integrity-pipeline">{[['Published','published'],['Acquired','acquired'],['Stored','actual_raw'],['Mapped','actual_mapping'],['Joined view','actual_joined']].map(([label,key],index)=><div key={key}><small>0{index+1}</small><span>{label}</span><strong>{fmt(report?.sources.reduce((sum,row)=>sum+(row[key as 'actual_raw'] as number),0))}</strong><em>{report?'Reconciled':'Not independently verified'}</em></div>)}</div>
      </section>
      <section className="t3-integrity-panel"><div className="t3-integrity-section"><div><div className="t3-eyebrow">Source-level reconciliation</div><h2>All {catalog.length} FMCSA / DOT sources</h2></div><label className="t3-integrity-search">Find a source<input type="search" aria-label="Find a source" placeholder="Name, family or source ID" value={query} onChange={event=>filter(event.target.value)}/></label></div>
        <p className="t3-integrity-context">{rows.length} of {catalog.length} registered sources shown. Dashes mean no validated audit is installed, not zero records.</p>
        <p className="t3-integrity-scroll-hint">Scroll the table to compare every source and count. Search narrows the view without changing the audited totals.</p>
        <div className="t3-integrity-table-wrap" tabIndex={0} aria-label="Source reconciliation table; scroll horizontally for all counts"><table><caption>Published, imported and joined counts from the same independently audited cut.</caption><thead><tr><th scope="col">Official source</th><th scope="col">Published</th><th scope="col">Stored</th><th scope="col">Joined</th><th scope="col">Exact duplicates</th><th scope="col">Integrity</th></tr></thead><tbody>
          {rows.map(source=>{const row=byId.get(source.id);return <tr key={source.id}><th scope="row"><a href={`https://data.transportation.gov/d/${source.id}`} target="_blank" rel="noreferrer">{source.name}</a><small>{source.id} / {source.family}</small>{row&&<details><summary>Source provenance</summary><span>Retrieved: {time(row.available_at)}</span><span>Publisher update: {new Date(row.rows_updated_at*1000).toLocaleString()}</span><code>{row.sha256}</code><span>Resolved: {fmt(row.mapping_status.RESOLVED??0)} / identified only: {fmt(row.mapping_status.IDENTIFIED_ONLY??0)} / unresolved: {fmt(row.mapping_status.UNRESOLVED??0)}</span><span>Carrier identity disagreements: {row.identity_mapping_disagreements}</span></details>}</th><td>{fmt(row?.published)}</td><td>{fmt(row?.actual_raw)}</td><td>{fmt(row?.actual_joined)}</td><td>{fmt(row?.exact_duplicate_rows)}</td><td><span className={'t3-integrity-badge '+(row?'verified':'unknown')}>{row?'Reconciled':'Not verified'}</span></td></tr>;})}
        </tbody></table>{rows.length===0&&<p className="t3-integrity-no-results">No registered sources match this search.</p>}</div>
      </section>
      <section className="t3-integrity-provenance"><article data-release-status={releaseState.kind}><div className="t3-eyebrow">Public application</div><h2>Release provenance</h2><p role="status" aria-live="polite">{releaseState.kind==='loading'?'Loading release metadata...':releaseState.kind==='verified'?'Release metadata loaded; warehouse acceptance is a separate check.':`Release metadata unavailable: ${releaseState.error}. Recheck installation to retry.`}</p><dl><dt>Pages manifest commit</dt><dd><code>{release?.commit??'Not verified'}</code></dd><dt>Application built</dt><dd>{time(release?.builtAt)}</dd><dt>Bundled source-probe snapshot</dt><dd>{time(release?.metadataAt)}{metadataAge!==null&&<span className="t3-integrity-age">{metadataAge} days old; not a live check</span>}</dd></dl></article>
        <article><div className="t3-eyebrow">Installed evidence service</div><h2>Immutable data cut</h2><dl><dt>Cut identity</dt><dd>{report?.cut_id??'Not verified'}</dd><dt>Independent audit completed</dt><dd>{time(report?.audited_at)}</dd><dt>Warehouse SHA-256</dt><dd><code>{report?.warehouse_sha256??'Not verified'}</code></dd></dl></article></section>
      <p className="t3-integrity-boundary">Private insurer data is never loaded by this page. FEMA county context is a separate data product, not a carrier route or a hazard score. Source probes, accepted warehouse receipts, independent audits and live screen checks are distinct release gates.</p>
      <div className="t3-integrity-links"><a href="#/sources">Review source connectivity</a><a href="#/atlas">Open Carrier Geography Atlas</a><a href="https://github.com/JeremyHennessy/Transport3r/blob/main/docs/release-data-visual-audit.md" target="_blank" rel="noreferrer">Audit and installation requirements</a></div>
    </main><footer className="t3-footer"><span>Transport3r</span><span>Public evidence only</span><span>Unavailable is not zero</span></footer>
  </div>;
}
