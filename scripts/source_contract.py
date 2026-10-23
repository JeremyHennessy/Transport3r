"""Single machine-readable FMCSA identity, grain and release contract."""
import json
import pathlib

ROOT=pathlib.Path(__file__).resolve().parents[1]
PATH=ROOT/'data/fmcsa_source_contract.json'
ALLOWED_STRATEGIES={'direct_usdot','direct_usdot_legacy','inspection_parent','legacy_docket'}

def load_contract():
    payload=json.loads(PATH.read_text(encoding='utf-8'))
    if payload.get('version')!=1 or payload.get('identity_contract')!='FMCSA_CARRIER_IDENTITY_1':
        raise ValueError('Unsupported FMCSA source contract')
    sources=payload.get('sources')
    if not isinstance(sources,dict) or not sources:
        raise ValueError('FMCSA source contract is empty')
    for sid,item in sources.items():
        identity=item.get('identity',{})
        if identity.get('strategy') not in ALLOWED_STRATEGIES or not identity.get('field'):
            raise ValueError('Invalid identity contract: '+sid)
        if not item.get('grain') or not item.get('release_group') or not isinstance(item.get('event_date_fields'),list):
            raise ValueError('Incomplete source semantics: '+sid)
    return payload

def source_contracts():
    return load_contract()['sources']

def catalog_sources():
    value=json.loads((ROOT/'data/fmcsa_sources.json').read_text(encoding='utf-8'))
    return value['sources'] if isinstance(value,dict) else value
