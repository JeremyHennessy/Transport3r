import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

// Exercise the actual readiness predicate used by Playwright, without network.
const source=readFileSync(new URL('./verify_live_ui.py',import.meta.url),'utf8');
const match=/READINESS_JS = r'''([\s\S]*?)'''/.exec(source);
assert.ok(match,'Production browser readiness predicate must remain testable');
function check(text,label,expected,{selectors=[],lines=0}={}){
 const document={body:{innerText:text},querySelector:s=>selectors.includes(s)?{}:null,
   querySelectorAll:s=>s==='.t3-insurance-line'?Array(lines).fill({}):[]};
 const fn=runInNewContext(`(${match[1]})`,{document});
 return JSON.parse(JSON.stringify(fn({label,expected,errors:['Carrier identity could not load.']})));
}
test('directory uppercase and whitespace remain semantically identical',()=>{
 assert.deepEqual(check('NATIONWIDE  CARRIER\nINTELLIGENCE','carriers',['Nationwide carrier intelligence'],{selectors:['.t3-carrier-row:not(.header) .carrier-name a']}),{ready:true});
});
test('VIN uppercase label does not time out with the correct detail panel',()=>{
 assert.deepEqual(check('OBSERVED VEHICLE EVIDENCE','vin',['Observed vehicle evidence'],{selectors:['[data-testid="vin-detail"]']}),{ready:true});
});
test('missing heading, missing directory rows and wrong VIN panel remain failures',()=>{
 assert.equal(check('Different heading','carriers',['Nationwide carrier intelligence']),false);
 assert.equal(check('NATIONWIDE CARRIER INTELLIGENCE','carriers',['Nationwide carrier intelligence']),false);
 assert.equal(check('OBSERVED VEHICLE EVIDENCE','vin',['Observed vehicle evidence']),false);
});
test('case normalization must not hide an identity error',()=>{
 assert.deepEqual(check('CARRIER IDENTITY COULD NOT LOAD.','summary',[]),{error:'Carrier identity could not load.'});
});
test('all eight insurance lines are still required',()=>{
 assert.equal(check('Review by coverage line','insurance',['Review by coverage line'],{lines:7}),false);
 assert.deepEqual(check('REVIEW BY COVERAGE LINE','insurance',['Review by coverage line'],{lines:8}),{ready:true});
});
test('an Atlas heading without a rendered map is not ready',()=>{
 assert.equal(check('Carrier Geography Atlas','atlas-carrier',['Carrier Geography Atlas']),false);
});
test('an integrity loading state is not a passing installation check',()=>{
 assert.equal(check('Data Integrity CHECKING THE INSTALLED EVIDENCE SERVICE','integrity',['Data Integrity']),false);
});

test('evidence navigation and loading cards cannot pass as loaded lineage',()=>{
 assert.equal(check('Evidence loading complete carrier evidence','evidence',['Evidence']),false);
 assert.equal(check('Evidence lineage','evidence',['Evidence lineage']),false);
 assert.deepEqual(check('Evidence lineage','evidence',['Evidence lineage'],{selectors:['.c360-card .c360-raw-census']}),{ready:true});
});
test('authority navigation cannot pass without the actual authority table',()=>{
 assert.equal(check('Authority Operating authority','authority',['Operating authority']),false);
 assert.deepEqual(check('Operating authority','authority',['Operating authority'],{selectors:['.c360-table.authority']}),{ready:true});
});
test('section capture excludes shared loading cards and selects actual evidence lineage',()=>{
 assert.ok(source.includes("'evidence': '.c360-card:has(.c360-raw-census)'"));
 assert.ok(source.includes(':not([data-testid="complete-data-status"])'));
 assert.ok(source.includes('target.scroll_into_view_if_needed(timeout=45000)'));
});
