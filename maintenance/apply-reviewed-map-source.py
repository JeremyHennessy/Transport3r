"""One-time application of a hash-pinned reviewed source set, not a production importer."""
import base64
import hashlib
import json
import os
import pathlib
import subprocess
import zlib

root=pathlib.Path.cwd()
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==os.environ['EXPECTED_HEAD']
expected_parts=['3e46001e6b0bbf3a7e695f56a53eb57a64edecc7053ed1240bc1c0b67feb776b','85b5870507bc238969d1a51b719b989c6308c97beb61446c7f7da815f891891b','2eb31c0bac0386b00bf2541c7218632ddf66eb9b08335965e2840d2ed4faa114','f952a7d05010646c4b3cf132dd35a5024948edd02d36f4f11dcb3a5ed6885672']
chunks=[]
for number,expected in enumerate(expected_parts,1):
    p=root/f'maintenance/open-map-change-set.{number}.b64'
    assert p.is_file() and not p.is_symlink()
    raw=p.read_bytes()
    if number==1 and hashlib.sha256(raw).hexdigest()=='95a84a839b58490c032a92a98a90db1ae09e0684c3ac1c47b9d0c592c83eac28':
        assert raw.count(b'Rod9rttNNdu')==1
        raw=raw.replace(b'Rod9rttNNdu',b'Rod9rttNdu')
    assert hashlib.sha256(raw).hexdigest()==expected,number
    chunks.append(raw.strip())
body=zlib.decompress(base64.b64decode(b''.join(chunks),validate=True))
assert len(body)==71040 and hashlib.sha256(body).hexdigest()=='28b2ca78f59fa5a10d93191aef5ad305817a31f7a1715b8f682c94a7059b0fd2'
records=json.loads(body)
allowed={'docs/open-carrier-maps.md','scripts/live-source-retry.mjs','scripts/open-geography.test.mjs','scripts/public-asset-policy.mjs','scripts/public-assets.test.mjs','scripts/source-http.test.mjs','scripts/source-retry-policy.test.mjs','scripts/validate-carrier-mappings.mjs','scripts/validate_open_maps_browser.py','src/CarrierMaps.tsx','src/CarrierRouteApp.tsx','src/OfficialSmsPanel.tsx','src/OpenMap.tsx','src/WorkspaceApp.tsx','src/carrierEvidence.ts','src/carrierMaps.css','src/datahub.ts','src/main.tsx','src/mapRuntime.ts','src/openGeography.ts','src/sourceHttp.ts','vite.config.ts'}
assert len(records)==len(allowed) and {r['path'] for r in records}==allowed
existing_hash=hashlib.sha256((root/'vite.config.ts').read_bytes()).hexdigest()
assert existing_hash=='99f5db2a7d2620eeb0484c255910c1606c53af4d2881482f27f4379a719821ab'
next(r for r in records if r['path']=='vite.config.ts').update(before=existing_hash,after=existing_hash,edits=[])
staged={}
for r in records:
    path=root/r['path']
    assert path.resolve().is_relative_to(root) and not path.is_symlink()
    if r['before'] is None:
        assert not path.exists(),r['path']
        original=b''
    else:
        original=path.read_bytes()
        assert hashlib.sha256(original).hexdigest()==r['before'],r['path']
    updated=original
    end=len(original)
    for edit in reversed(r['edits']):
        offset,remove=edit['offset'],edit['remove']
        assert type(offset) is int and type(remove) is int and 0<=offset<=offset+remove<=end
        updated=updated[:offset]+edit['text'].encode('utf-8')+updated[offset+remove:]
        end=offset
    assert hashlib.sha256(updated).hexdigest()==r['after'],r['path']
    staged[r['path']]=updated

# MapLibre v6 ESM requires explicit Vite worker bundling. No remote CDN worker.
# https://maplibre.org/maplibre-gl-js/docs/#esm
replacements={
 'src/main.tsx':[("configureMapLoader(() => import('maplibre-gl'));", "import mapWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';\nconfigureMapLoader(async () => {\n  const renderer = await import('maplibre-gl');\n  renderer.setWorkerUrl(mapWorkerUrl);\n  return renderer;\n});")],
 'scripts/public-asset-policy.mjs':[("(?:index|maplibre-gl)-", "(?:index|maplibre-gl(?:-worker)?)-")],
 'scripts/validate_open_maps_browser.py':[("requests=[];external=[];fail_map=False", "requests=[];external=[];console_errors=[];local_failures=[];workers=[];fail_map=False"),
 ("page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)));page.set_default_timeout(20000)","page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)));page.set_default_timeout(20000)\n            page.on('console',lambda message:console_errors.append(message.text) if message.type=='error' else None)\n            page.on('worker',lambda worker:workers.append(worker.url))\n            page.on('response',lambda response:local_failures.append({'url':response.url,'status':response.status}) if response.status>=400 and urlsplit(response.url).hostname=='127.0.0.1' else None)"),
 ("assert page.locator('[data-testid=directory-map] .t3-map-marker').count()==2", "page.wait_for_function(\"document.querySelectorAll('[data-testid=directory-map] .t3-map-marker').length===2\")\n                assert any('/Transport3r/assets/maplibre-gl-worker-' in url for url in workers),workers\n                assert not local_failures,local_failures"),
 ("result['error']=str(error);result['runtime_errors']=errors", "result['error']=str(error);result['runtime_errors']=errors;result['console_errors']=console_errors;result['local_failures']=local_failures;result['worker_urls']=workers")]
}
for name,changes in replacements.items():
    text=staged[name].decode('utf-8')
    for old,new in changes:
        assert text.count(old)==1,(name,old)
        text=text.replace(old,new)
    staged[name]=text.encode('utf-8')
staged['scripts/public-assets.test.mjs']+=b'''\n\ntest('map worker must be bundled and belong to the exact compiler inventory',async t=>{\n  assert.doesNotThrow(()=>assertPublicAsset('assets/maplibre-gl-worker-ABC123xy.js'));\n  assert.throws(()=>assertReviewedStaticAsset('assets/maplibre-gl-worker-ABC123xy.js'));\n  const {root,inventory}=await buildFixture(t);\n  await writeFile(join(root,'assets/maplibre-gl-worker-ABC123xy.js'),'unreviewed worker');\n  await assert.rejects(createManifest(root,commit,inventory),/not the exact generated/);\n});\n'''
expected_final={
 'src/main.tsx':'29a440bf8f05014cc5433dfbb7e801a610d5a836c9878a7d4c40d56e4bfba06e',
 'scripts/public-asset-policy.mjs':'bb21888d0e4c0bbb771679c988509041cc900cc5e04671ceb90be33ecbb360c3',
 'scripts/public-assets.test.mjs':'809ad64598a0b882ea63815bf4426a8c072e59079e1186b55dd8a1cf34e5e936',
 'scripts/validate_open_maps_browser.py':'1ac8aea89f33ab01804e197122bdd93d3346de2c93769911ccf1e9f27359978c'}
for name,expected in expected_final.items():
    assert hashlib.sha256(staged[name]).hexdigest()==expected,(name,hashlib.sha256(staged[name]).hexdigest())
for name,updated in staged.items():
    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(updated)
out=pathlib.Path('/tmp/transport3r-map-source');out.mkdir(parents=True,exist_ok=True)
(out/'verified-paths.json').write_text(json.dumps(sorted(allowed-{'vite.config.ts'})))
(out/'source-change-receipt.json').write_text(json.dumps({'input_head':os.environ['EXPECTED_HEAD'],'event_merge_sha':os.environ['GITHUB_SHA'],'change_set_sha256':hashlib.sha256(body).hexdigest(),'preserved_compatible_vite_sha256':existing_hash,'worker_fix':'EXPLICIT_VITE_BUNDLED_SAME_ORIGIN_WORKER','files':[{'path':r['path'],'before':r['before'],'after':hashlib.sha256(staged[r['path']]).hexdigest()} for r in records],'deployed':False},indent=2))
