"""Read-only inventory of PBIP definitions and PBIX metadata; never refresh or evaluate DAX.

PBIX extraction optionally needs pbixray==0.15.5. Outputs contain local model
definitions and should remain in ignored output storage, not in public Git history.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import re
import zipfile


def checksum(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def walk(value):
    if isinstance(value, str) and value[:1] in '{[':
        try:
            yield from walk(json.loads(value))
        except (ValueError, TypeError):
            pass
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def visual_summary(value):
    nodes = list(walk(value))
    return {'types': dict(collections.Counter(n['visualType'] for n in nodes if 'visualType' in n)),
            'fields': sorted({n['queryRef'] for n in nodes if isinstance(n.get('queryRef'), str)}),
            'properties': sorted({n['Property'] for n in nodes if isinstance(n.get('Property'), str)})}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def review(root, output, pbix=False):
    root, output = pathlib.Path(root).resolve(), pathlib.Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'scope': str(root), 'mode': 'STATIC_DEFINITIONS_NOT_DAX_EXECUTION', 'models': [], 'reports': []}
    for model in sorted(root.glob('*.SemanticModel')):
        item = {'name': model.name, 'tables': [], 'relationships': []}
        for path in sorted((model/'definition/tables').glob('*.tmdl')):
            source = path.read_text(encoding='utf-8-sig')
            objects = []
            for match in re.finditer(r'^\t(measure|column|partition) (.+?)(?=^\t(?:measure|column|partition|annotation|changedProperty) |\Z)', source, re.M | re.S):
                body = match.group(2)
                objects.append({'kind': match.group(1), 'name': body.splitlines()[0].split(' =')[0].strip("'"),
                                'line': source.count('\n', 0, match.start())+1, 'definition': body})
            item['tables'].append({'name': path.stem, 'path': str(path), 'sha256': checksum(path), 'objects': objects,
                                   'public_source_ids': sorted(set(re.findall(r'/v4/([a-z0-9]{4}-[a-z0-9]{4})', source)))})
        rel = model/'definition/relationships.tmdl'
        if rel.exists():
            item['relationships'] = [s.strip() for s in re.split(r'^relationship ', rel.read_text(encoding='utf-8-sig'), flags=re.M) if s.strip()]
        result['models'].append(item)
    for report in sorted(root.glob('*.Report')):
        pages = []
        for p in sorted((report/'definition/pages').glob('*/page.json')):
            page = read_json(p)
            visuals = [read_json(v) for v in sorted((p.parent/'visuals').glob('*/visual.json'))]
            pages.append({'name': page['displayName'], 'visibility': page.get('visibility','Visible'),
                          'visual_count': len(visuals), **visual_summary(visuals)})
        result['reports'].append({'name': report.name, 'pages': pages})
    for path in sorted(root.glob('*.pbix')):
        print('Reviewing '+path.name, flush=True)
        before = checksum(path)
        item = {'name': path.name, 'sha256': before, 'bytes': path.stat().st_size}
        with zipfile.ZipFile(path) as archive:
            layout = json.loads(archive.read('Report/Layout').decode('utf-16-le'))
            pages = [{'name': p['displayName'], 'visual_count': len(p.get('visualContainers', [])),
                      **visual_summary(p.get('visualContainers', []))} for p in layout['sections']]
            result['reports'].append({'name': path.name, 'pages': pages})
            item['archive_members'] = [{'name': p.filename, 'bytes': p.file_size} for p in archive.infolist()]
        item['binary_status'] = 'NOT_EXTRACTED'
        if pbix:
            from pbixray import PBIXRay
            with PBIXRay(str(path), on_disk=True) as model:
                for attr in ['schema', 'dax_measures', 'dax_columns', 'dax_tables', 'relationships', 'power_query', 'statistics']:
                    frame = getattr(model, attr)
                    item[attr] = json.loads(frame.to_json(orient='records', date_format='iso'))
                item['binary_status'] = 'METADATA_EXTRACTED_NOT_EXECUTED'
        if checksum(path) != before:
            raise ValueError('Input changed during read-only review: '+path.name)
        result['models'].append(item)
        (output/(path.stem+'.metadata.json')).write_text(json.dumps(item, indent=2), encoding='utf-8')
    (output/'inventory.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    for m in result['models']:
        print(m['name'], 'tables', len(m.get('tables', [])) or len({r.get('TableName') for r in m.get('schema', [])}),
              'measures', len(m.get('dax_measures', [])) or sum(o['kind']=='measure' for t in m.get('tables',[]) for o in t['objects']))
    for r in result['reports']:
        print(r['name'], [(p['name'],p['visual_count']) for p in r['pages']])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('output')
    parser.add_argument('--pbix', action='store_true')
    args = parser.parse_args()
    review(args.root, args.output, args.pbix)
