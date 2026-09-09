import {readValue, type DataRow} from './datahub';
import type {SafetyWindowResult} from './safetyWindow';
import boundaries from './stateBoundaries.json';
export function eventGeography(result:SafetyWindowResult) {
  const known=new Set(boundaries.states.map(state=>state.code));
  let unlocated=0,rejected=0;
  const events=result.sources.flatMap(source=>source.error?[]:(source.slice?.rows??[]).flatMap((row:DataRow,index)=>{
    if(readValue(row,['DOT_NUMBER'])!==result.dot){rejected++;return [];}
    const kind=source.id==='fx4q-ay7w'?'inspection':'crash';
    const locationState=readValue(row,[kind==='inspection'?'COUNTY_CODE_STATE':'STATE'])?.trim().toUpperCase();
    const reportingState=kind==='inspection'?readValue(row,['REPORT_STATE'])?.trim().toUpperCase():undefined;
    const state=known.has(locationState??'')?locationState:known.has(reportingState??'')?reportingState:undefined;
    if(!state){unlocated++;return [];}
    const id=readValue(row,[kind==='inspection'?'INSPECTION_ID':'CRASH_ID']);
    return [{key:`${source.id}:${id??index}`,id,state,kind,precision:state===locationState?'source location state':'reporting jurisdiction only',date:readValue(row,[kind==='inspection'?'INSP_DATE':'REPORT_DATE'])??'Unknown',report:readValue(row,['REPORT_NUMBER'])??'Unknown',location:readValue(row,['LOCATION_DESC','LOCATION'])??'Not reported',source:source.id,dot:result.dot}];
  }));
  return {events,unlocated,rejected};
}
