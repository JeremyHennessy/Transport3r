// Private single-owner UI, appended only by the loopback server. No persistent browser storage.
(() => {
  const workspace = $('workspace'), section = node('section'); section.id = 'loss-history';
  section.append(node('p','PRIVATE LOSS-REVIEW WORKFLOW','eyebrow'),node('h2','Loss history'),
    node('p','Preview a normalized loss-history JSON file, review every issue, and explicitly approve the exact file before import. Claims remain on this computer; missing history is not zero losses.'),
    node('p','Single-owner local workflow only. Use a private data directory outside the repository. No multi-tenant hosting, document extraction, coverage decision or actuarial acceptance is implied.','note'));
  const sourceLabel=node('label','Normalized loss-history JSON file');
  const source=node('input');source.id='lossHistoryFile';source.type='file';source.accept='.json,application/json';
  source.setAttribute('aria-describedby','lossHistorySourceNote');sourceLabel.append(source);
  const sourceNote=node('p','Up to 2,000,000 bytes. Use the PRIVATE_LOSS_HISTORY_1 schema; claimant names and narratives are not accepted.','note');sourceNote.id='lossHistorySourceNote';
  const previewButton=button('Preview loss history',previewSource);previewButton.id='lossHistoryPreview';
  const clearButton=button('Clear selected file',()=>reset());
  const previewResult=node('div');previewResult.id='lossHistoryPreviewResult';previewResult.setAttribute('aria-live','polite');
  const approvalLabel=node('label',undefined,'loss-approval');const approval=node('input');approval.type='checkbox';approval.id='lossHistoryApproval';
  approvalLabel.append(approval,document.createTextNode(' I reviewed this exact file, the policy matches and every issue, and approve this import.'));
  const importButton=button('Import approved loss history',importSource);importButton.id='lossHistoryImport';
  const importResult=node('div');importResult.id='lossHistoryImportResult';importResult.setAttribute('aria-live','polite');
  const historyButton=button('Load private loss history',()=>historyPage(0));historyButton.id='lossHistoryLoad';
  const history=node('div');history.id='lossHistoryBatches';history.setAttribute('aria-live','polite');
  section.append(sourceLabel,sourceNote,previewButton,clearButton,previewResult,approvalLabel,importButton,importResult,
    node('h3','Accepted import history'),node('p','Each batch represents supplied observations at one valuation. Historical valuations are never summed together.','note'),historyButton,history);
  workspace.insertBefore(section,$('inbox'));
  const link=node('a','Loss history');link.href='#loss-history';
  workspace.querySelector('nav').insertBefore(link,workspace.querySelector('nav a[href="#inbox"]'));
  let raw=null, plan=null, expiresAt=0, generation=0, historyGeneration=0, busy=false;
  const active=()=>!workspace.hidden;
  function controls(){
    previewButton.disabled=busy||!raw||!active();source.disabled=busy;
    approval.disabled=busy||!plan?.approval_token||Date.now()>=expiresAt||!active();
    importButton.disabled=approval.disabled||!approval.checked;
  }
  function reset(clearResults=true){
    generation++;historyGeneration++;raw=null;plan=null;expiresAt=0;busy=false;source.value='';approval.checked=false;
    if(clearResults){previewResult.replaceChildren();importResult.replaceChildren();history.replaceChildren();}
    controls();
  }
  source.addEventListener('change',async()=>{
    generation++;const revision=generation;raw=null;plan=null;expiresAt=0;approval.checked=false;
    previewResult.replaceChildren();importResult.replaceChildren();controls();
    const file=source.files?.[0];if(!file)return;
    if(!file.size||file.size>2000000){message('Select a nonempty JSON file no larger than 2,000,000 bytes.',true);return;}
    try{
      const bytes=new Uint8Array(await file.arrayBuffer());if(revision!==generation||!active())return;
      let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      raw=btoa(binary);controls();
    }
    catch{if(revision===generation)message('The selected file could not be read.',true);}
  });
  approval.addEventListener('change',controls);
  async function previewSource(){
    if(!raw||busy||!active())return;
    const revision=++generation;busy=true;plan=null;approval.checked=false;previewResult.replaceChildren();controls();
    try{
      const result=await api('/api/loss-history/preview',{source_base64:raw});
      if(revision!==generation||!active())return;
      plan=result;expiresAt=Date.now()+result.approval_expires_in_seconds*1000;
      previewResult.append(node('h3',result.status==='READY_FOR_PRIVATE_IMPORT'?'Ready for explicit review approval':'Review required; no rows imported'),
        node('p',`${result.input_rows} input rows; ${result.unique_candidate_rows} unique candidates; ${result.exact_duplicate_rows} exact repeats; ${result.review_required_rows} rows require review.`),
        node('p',`Valuation ${result.valuation_date}. Preview ${result.preview_sha256}.`,'note'));
      for(const issue of result.issues??[])previewResult.append(node('p',`Row ${issue.row}: ${issue.reason}`,'error'));
      previewResult.append(node('p','Approval expires after ten minutes and is bound to this login session, the exact input bytes and the saved portfolio. Existing-ledger conflicts are checked again during the atomic import.','note'));
    }catch(error){if(revision===generation){plan=null;message(error.message,true);}}
    finally{if(revision===generation){busy=false;controls();}}
  }
  async function importSource(){
    controls();if(importButton.disabled||!raw||!plan)return;
    const revision=++generation,body={source_base64:raw,expected_preview:plan.preview_sha256,approval_token:plan.approval_token,approved:true};
    busy=true;controls();
    try{
      const result=await api('/api/loss-history/import',body);
      if(revision!==generation||!active())return;
      reset(false);previewResult.replaceChildren();importResult.replaceChildren(node('h3','Imported privately'),
        node('p',`${result.imported_rows} new observations; ${result.existing_observation_rows} already recorded. No rows were overwritten.`));
      renderSummary(importResult,result.summary);await historyPage(0);
    }catch(error){if(revision===generation){plan=null;approval.checked=false;previewResult.replaceChildren(node('p','Import was not accepted. Resolve the issue and generate a fresh preview.','error'));message(error.message,true);}}
    finally{if(revision===generation){busy=false;controls();}}
  }
  function money(value){
    const amount=BigInt(value.known_sum);return `${amount.toLocaleString()} known minor units; ${value.unknown_count} unknown`;
  }
  function renderSummary(parent,summary){
    parent.append(node('p',`Valuation ${summary.valuation_date}; ${summary.observations} supplied observations. This is not a complete loss run or a coverage finding.`,'note'));
    for(const group of summary.groups){
      const entry=record(parent,`${group.coverage_line} / ${group.currency}`);
      entry.append(node('p',`Paid: ${money(group.paid_minor)}. Outstanding: ${money(group.outstanding_minor)}. Gross indemnity only; expenses and recoveries excluded.`));
    }
    parent.append(button('Export this private valuation summary',()=>{
      const blob=new Blob([JSON.stringify(summary,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob);
      const a=node('a');a.href=url;a.download='private-loss-valuation-summary.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }));
  }
  async function historyPage(offset){
    const revision=++historyGeneration,sessionGeneration=generation;historyButton.disabled=true;
    try{
      const result=await api('/api/loss-history/batches?'+new URLSearchParams({limit:20,offset}));
      if(revision!==historyGeneration||sessionGeneration!==generation||!active())return;
      history.replaceChildren();
      if(!result.batches.length)history.append(node('p','No import batches on this page. Missing history does not establish zero claims.'));
      for(const batch of result.batches){
        const entry=record(history,`Valuation ${batch.valuation_date}`);
        entry.append(node('p',`${batch.input_rows} input rows; ${batch.imported_rows} new observations; reviewed by ${batch.reviewer} at ${batch.created_at}.`),
          button('View this valuation summary',async()=>{
            const before=generation,value=await api('/api/loss-history/summary?'+new URLSearchParams({batch_id:batch.batch_id}));
            if(before!==generation||!active()||!entry.isConnected)return;
            const detail=node('div');renderSummary(detail,value);entry.append(detail);
          }));
      }
      const previous=button('Previous loss imports',()=>historyPage(Math.max(0,offset-20))),next=button('Next loss imports',()=>historyPage(offset+20));
      previous.disabled=offset===0;next.disabled=!result.has_next;history.append(previous,next);
    }finally{historyButton.disabled=false;}
  }
  $('logout').addEventListener('click',()=>reset());
  new MutationObserver(()=>{if(workspace.hidden)reset();else controls();}).observe(workspace,{attributes:true,attributeFilter:['hidden']});
  const timer=setInterval(()=>{if(plan?.approval_token&&Date.now()>=expiresAt){plan=null;approval.checked=false;previewResult.append(node('p','Preview expired. Review a fresh preview before importing.','note'));}controls();},1000);
  window.addEventListener('pagehide',()=>{clearInterval(timer);reset();},{once:true});
  controls();
})();
