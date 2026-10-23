"""Validate common-cut, SMS-release and model-release temporal policy."""
import json,pathlib
from source_contract import source_contracts

ROOT=pathlib.Path(__file__).resolve().parents[1]
POLICY=ROOT/'data/temporal_policy.json'
SMS_OBSERVATION=ROOT/'data/sms_release_observation.json'


def load_policy():
    value=json.loads(POLICY.read_text(encoding='utf-8'))
    if value.get('version')!=1 or value.get('contract')!='TRANSPORT3R_TEMPORAL_CUT_1':raise ValueError('Unsupported temporal policy')
    if value.get('knowledge_time')!='complete_cut_available_at' or value.get('event_date_is_knowledge_time') is not False or value.get('no_cross_cut_mixing') is not True:raise ValueError('Unsafe temporal policy')
    current=value.get('current_cut',{})
    if current.get('availability')!='complete_collection_completed_at' or current.get('requires_all_registered_sources') is not True or current.get('requires_stable_before_after_watermarks') is not True:
        raise ValueError('Unsafe current-cut availability policy')
    sms=value['sms_release_binding'];expected={sid for sid,item in source_contracts().items() if item['release_group']=='sms_current_unbound'}
    if set(sms.get('required_sources',[]))!=expected or sms.get('website_date_alone_is_sufficient') is not False or sms.get('maximum_event_date_alone_is_sufficient') is not False:raise ValueError('Unsafe SMS release policy')
    if value['model_release'].get('tri_v0_1')!='BLOCKED_RESEARCH_ONLY':raise ValueError('TRI v0.1 release block was removed')
    return value


def sms_binding(observation=None):
    policy=load_policy();path=pathlib.Path(observation) if observation else SMS_OBSERVATION
    value=json.loads(path.read_text(encoding='utf-8'))
    required=set(policy['sms_release_binding']['required_sources']);actual={item.get('id') for item in value.get('datahub_sources',[])}
    verified=value.get('datahub_month_binding')=='VERIFIED' and actual==required and all(item.get('binding_status')=='VERIFIED' for item in value['datahub_sources'])
    return {'status':'VERIFIED' if verified else 'UNVERIFIED','observation':str(path),'website_snapshot_date':value.get('website_snapshot_date'),'website_updated_on':value.get('website_updated_on'),'source_count':len(actual),'reason':None if verified else value.get('reason','Exact SMS release binding unavailable')}


if __name__=='__main__':print(json.dumps({'policy':load_policy(),'sms_binding':sms_binding()},indent=2))
