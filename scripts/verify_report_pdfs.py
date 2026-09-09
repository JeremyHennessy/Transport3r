"""Validate generated client reports; pypdf is a verification-only dependency."""
import json,pathlib,sys
from pypdf import PdfReader
import pdfplumber
folder=pathlib.Path(sys.argv[1]);results=[]
for file in sorted(folder.glob('*.pdf')):
    reader=PdfReader(file);texts=[p.extract_text() for p in reader.pages];text='\n'.join(texts)
    assert '3938496' in text and 'REPORT FIXTURE' in text, (file,'identity')
    assert '2026-01-01' in text and '2026-09-09' in text, (file,'window')
    assert 'fx4q-ay7w' in text and 'FMCSA' in text,(file,'provenance')
    assert all(len(t.strip())>80 for t in texts),(file,'blank page')
    if file.stem.endswith('-brief'):assert 1<=len(texts)<=3,(file,len(texts),'brief page count')
    else:assert 'Evidence appendix' in text and 'Source coverage' in text,(file,'appendix')
    if file.stem.startswith('partial'):assert 'Unavailable' in text,(file,'missing data')
    with pdfplumber.open(file) as document:
        for number,page in enumerate(document.pages,1):
            outside=[char for char in page.chars if char['text'].strip() and (char['x0']<0 or char['x1']>page.width+1 or char['top']<0 or char['bottom']>page.height+1)]
            assert not outside,(file,number,'text outside PDF page')
    results.append({'file':file.name,'pages':len(texts),'characters':len(text)})
assert len(results)==16, len(results)
(folder/'pdf-validation.json').write_text(json.dumps({'status':'PASS','reports':results},indent=2))
print(json.dumps(results,indent=2))
