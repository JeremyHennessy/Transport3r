import type {CarrierEvidence} from './carrierEvidence';

export type AtlasLoadState = {
  generation: number;
  status: 'idle'|'loading'|'loaded'|'failed'|'invalid';
  evidence: CarrierEvidence|null;
  error: string;
};
export type AtlasLoadAction =
  | {type:'start'|'clear'; generation:number}
  | {type:'complete'; generation:number; evidence:CarrierEvidence}
  | {type:'fail'|'invalidate'; generation:number; error:string};
export const initialAtlasLoadState: AtlasLoadState = {
  generation:0, status:'idle', evidence:null, error:'',
};

/** Superseded fetches must never repopulate a cleared/changed carrier view. */
export function atlasLoadReducer(state:AtlasLoadState, action:AtlasLoadAction):AtlasLoadState {
  if (!Number.isSafeInteger(action.generation) || action.generation < 1) {
    throw new Error('Atlas request generation must be a positive safe integer');
  }
  if (action.type==='complete' || action.type==='fail') {
    if (action.generation!==state.generation || state.status!=='loading') return state;
    return action.type==='complete'
      ? {...state,status:'loaded',evidence:action.evidence,error:''}
      : {...state,status:'failed',evidence:null,error:action.error};
  }
  if (action.generation<=state.generation) return state;
  return {generation:action.generation,evidence:null,
    status:action.type==='start'?'loading':action.type==='clear'?'idle':'invalid',
    error:action.type==='invalidate'?action.error:''};
}
