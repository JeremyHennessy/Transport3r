import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
for(const file of ['ci.yml','app-review.yml']) {
 const text=await readFile(new URL(`../.github/workflows/${file}`,import.meta.url),'utf8');
 test(`${file}: rerun artifacts retain separate immutable attempt names`,()=>{
  const uploads=text.split('uses: actions/upload-artifact@v4').slice(1);
  assert.ok(uploads.length>0);
  for(const upload of uploads) {
   const name=upload.match(/name: ([^\n]+)/)?.[1];
   assert.ok(name?.includes('${{ github.sha }}'));
   assert.ok(name?.includes('${{ github.run_attempt }}'));
  }
  assert.doesNotMatch(text,/overwrite:\s*true/);
 });
 test(`${file}: PR concurrency preserves read-only and fail-closed validation`,()=>{
  assert.match(text,/permissions:\n  contents: read/);
  assert.match(text,/group:.*github.workflow.*github.event_name.*github.event.pull_request.number/);
  assert.match(text,/cancel-in-progress: \$\{\{ github.event_name == 'pull_request' \}\}/);
  assert.doesNotMatch(text,/continue-on-error:\s*true|contents:\s*write/);
 });
}
test('required live cohort gate still runs against official sources with original safety ceiling',async()=>{
 const text=await readFile(new URL('../.github/workflows/ci.yml',import.meta.url),'utf8');
 assert.match(text,/run: python scripts\/validate_evidence_warehouse.py --output \/tmp\/transport3r-warehouse --cohort data\/golden_carriers.json --max-rows 1000000 --profile underwriting_evidence_v3/);
 assert.doesNotMatch(text,/--cut |if: false/);
});
