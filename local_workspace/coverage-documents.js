// Private-workspace enhancement. Served after app.js in the SAME script response.
// No document contents are fetched or uploaded; only authenticated local metadata.
let checklistGeneration=0;
const documentPanel=node('div');documentPanel.id='coverageChecklist';documentPanel.hidden=true;
documentPanel.append(node('h3','Coverage document checklist'));
function identified(tag,id,text){const element=node(tag,text);element.id=id;return element;}
documentPanel.append(identified('p','coverageChecklistContext'),node('p','These are analyst prompts, not mandatory policy terms. Documents remain in your approved private storage; this workspace saves references only and never fetches or uploads them. Missing loss runs do not mean no claims.'));
const documentSummary=identified('p','coverageChecklistSummary');documentSummary.setAttribute('role','status');
documentPanel.append(documentSummary,identified('div','coverageChecklistItems'));
const documentForm=identified('form','coverageRequirementForm');documentForm.className='grid';documentForm.hidden=true;
for(const name of ['review_id','requirement_key','expected_revision','expected_template_version']){const input=node('input');input.name=name;input.type='hidden';documentForm.append(input);}
documentForm.append(identified('h4','coverageRequirementTitle','Document follow-up'));
function documentField(title,name,type){const label=node('label',title),input=node(type==='textarea'?'textarea':'input');input.name=name;if(type!=='textarea')input.type=type;label.append(input);documentForm.append(label);return input;}
const stateLabel=node('label','Document state'),documentState=node('select');documentState.name='status';
for(const [value,title] of [['not_requested','Not requested'],['requested','Requested'],['received','Received, not yet reviewed'],['reviewed','Reviewed by analyst'],['not_applicable','Not applicable, rationale required']]){const option=node('option',title);option.value=value;documentState.append(option);}
stateLabel.append(documentState);documentForm.append(stateLabel);
documentField('Follow-up due date','due_date','date');documentField('Date received','received_on','date');
const documentUrl=documentField('Private HTTPS evidence reference','evidence_url','url');documentUrl.maxLength=2000;documentUrl.placeholder='https://approved-storage.example/document';
documentField('Analyst rationale','notes','textarea').maxLength=4000;
documentForm.append(node('p','Received or reviewed items need a received date and evidence reference. Reviewed and not-applicable items require a rationale. These states never establish insurance coverage.'),node('button','Save document follow-up'));
const documentHistory=identified('pre','coverageRequirementHistory');documentHistory.hidden=true;
documentPanel.append(documentForm,documentHistory);$('insurance-reviews').append(documentPanel);
function clearCoverageChecklist(){
  checklistGeneration++;$('coverageChecklist').hidden=true;$('coverageChecklistItems').replaceChildren();
  $('coverageChecklistContext').textContent='';$('coverageChecklistSummary').textContent='';
  $('coverageRequirementForm').reset();$('coverageRequirementForm').hidden=true;
  $('coverageRequirementHistory').textContent='';$('coverageRequirementHistory').hidden=true;
}
async function loadCoverageChecklist(reviewId){
  const generation=++checklistGeneration;
  const plan=await api('/api/insurance-requirements?review_id='+encodeURIComponent(reviewId));
  if(!state||generation!==checklistGeneration)return;
  $('coverageChecklist').hidden=false;
  $('coverageChecklistContext').textContent=`${plan.account_id} / ${plan.policy_id} / USDOT ${plan.dot_number} / ${plan.line}`;
  $('coverageChecklistSummary').textContent=`${plan.summary.reviewed_or_not_applicable} of ${plan.summary.total} reviewed or marked not applicable; ${plan.summary.outstanding} outstanding. Not a coverage decision.`;
  $('coverageChecklistItems').replaceChildren();$('coverageRequirementForm').hidden=true;
  $('coverageRequirementHistory').hidden=true;$('coverageRequirementHistory').textContent='';
  const names={not_requested:'Not requested',requested:'Requested',received:'Received, not yet reviewed',reviewed:'Reviewed by analyst',not_applicable:'Not applicable'};
  for(const item of plan.items){
    const card=record($('coverageChecklistItems'),item.title);card.dataset.requirementKey=item.requirement_key;
    if(item.needs_template_review)card.append(node('p','Template updated: this prior review is not counted complete until explicitly reviewed against the current prompts.'));
    card.append(node('p',names[item.status]),node('small',`Revision ${item.revision}${item.due_date?' / follow-up '+item.due_date:''}${item.received_on?' / received '+item.received_on:''}`));
    if(item.notes)card.append(node('p',item.notes));
    if(item.evidence_url){const link=node('a','Open private evidence reference');link.href=item.evidence_url;link.target='_blank';link.rel='noopener noreferrer';card.append(link);}
    card.append(button('Edit document request',()=>{
      const form=$('coverageRequirementForm');
      const fields={review_id:plan.review_id,requirement_key:item.requirement_key,expected_revision:String(item.revision),expected_template_version:plan.template_version,
        status:item.status,due_date:item.due_date||'',received_on:item.received_on||'',evidence_url:item.evidence_url||'',notes:item.notes};
      for(const [name,value]of Object.entries(fields))form.elements.namedItem(name).value=value;
      $('coverageRequirementTitle').textContent=item.title;form.hidden=false;form.scrollIntoView();
    }));
    if(item.revision)card.append(button('Document change history',async()=>{
      const events=await api('/api/insurance-requirement-history?'+new URLSearchParams({review_id:plan.review_id,requirement_key:item.requirement_key}));
      if(!state||generation!==checklistGeneration)return;
      showJson('coverageRequirementHistory',events);$('coverageRequirementHistory').scrollIntoView();
    }));
  }
  for(const item of plan.retired_items||[]){
    const card=record($('coverageChecklistItems'),'Retired prompt: '+item.requirement_key);
    card.append(node('p',`Saved under ${item.template_version}. Read-only historical record; not part of current checklist completion.`));
    card.append(button('Retired document history',async()=>{
      const events=await api('/api/insurance-requirement-history?'+new URLSearchParams({review_id:plan.review_id,requirement_key:item.requirement_key}));
      if(!state||generation!==checklistGeneration)return;
      showJson('coverageRequirementHistory',events);$('coverageRequirementHistory').scrollIntoView();
    }));
  }
}
bindForm('coverageRequirementForm',async data=>{data.expected_revision=Number(data.expected_revision);await api('/api/insurance-requirement',data);await loadCoverageChecklist(data.review_id);message('Document follow-up saved locally with change history.');});
// Keep the existing workspace renderer and auth behavior intact. Render the
// document actions only after the saved-review list has been rebuilt.
const refreshBeforeDocuments=refresh;
refresh=async function(){
  await refreshBeforeDocuments();
  if(!state)return;
  const cards=Array.from($('insuranceReviewList').children).filter(element=>element.classList.contains('record'));
  for(const [index,item] of (state.insurance_reviews||[]).entries()){
    const card=cards[index];if(!card)throw new Error('Saved review and document action ordering differ');
    card.append(button('Requested documents',async()=>{await loadCoverageChecklist(item.id);$('coverageChecklist').scrollIntoView();}));
  }
};
const apiBeforeDocuments=api;
api=async function(path,body){
  try{return await apiBeforeDocuments(path,body);}
  finally{if(path==='/api/logout'||!state)clearCoverageChecklist();}
};
