import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';

const compiled=await build({entryPoints:['src/fleetIntegrity.ts'],bundle:true,write:false,format:'esm',platform:'node'});
const fleet=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);

const expectedBands=[
  ['A',1,1,'1 power unit'],['B',2,3,'2–3 power units'],['C',4,6,'4–6 power units'],
  ['D',7,8,'7–8 power units'],['E',9,11,'9–11 power units'],['F',12,14,'12–14 power units'],
  ['G',15,17,'15–17 power units'],['H',18,19,'18–19 power units'],['I',20,23,'20–23 power units'],
  ['J',24,28,'24–28 power units'],['K',29,32,'29–32 power units'],['L',33,38,'33–38 power units'],
  ['M',39,44,'39–44 power units'],['N',45,55,'45–55 power units'],['O',56,75,'56–75 power units'],
  ['P',76,100,'76–100 power units'],['Q',101,200,'101–200 power units'],['R',201,300,'201–300 power units'],
  ['S',301,400,'301–400 power units'],['T',401,550,'401–550 power units'],['U',551,999,'551–999 power units'],
  ['V',1000,2000,'1,000–2,000 power units'],['W',2001,3000,'2,001–3,000 power units'],
  ['X',3001,4000,'3,001–4,000 power units'],['Y',4001,5000,'4,001–5,000 power units'],
  ['Z',5001,Infinity,'Over 5,000 power units'],
];

test('fleet bands retain every FMCSA boundary and current display label',()=>{
  assert.deepEqual(fleet.FLEET_BANDS.map(({code,min,max,label})=>[code,min,max,label]),expectedBands);
  for(const [code,min,max,label] of expectedBands){
    assert.equal(fleet.expectedFleetBand(min),code);
    assert.equal(fleet.expectedFleetBand(Number.isFinite(max)?max:Number.MAX_SAFE_INTEGER),code);
    assert.equal(fleet.FLEET_BAND_LABELS[code],label);
  }
});

test('power-unit parsing accepts integers and well-formed comma values only',()=>{
  for(const [value,expected] of [[1,1],['1',1],[' 001 ',1],['1,000',1000],['5,001',5001]]){
    assert.equal(fleet.parseReportedPowerUnits(value),expected);
  }
  for(const value of [null,undefined,'',0,'0','-1',-1,'1.5',1.5,'1e3','1,00','1,000.0','NaN',NaN,Infinity,Number.MAX_SAFE_INTEGER+1]){
    assert.equal(fleet.parseReportedPowerUnits(value),null);
  }
});

test('assessment distinguishes matching, mismatching and unknown evidence',()=>{
  assert.deepEqual(fleet.assessFleetBand('1,000','v'),{status:'MATCH',powerUnits:1000,reported:'V',expected:'V'});
  assert.deepEqual(fleet.assessFleetBand('5,001','A'),{status:'MISMATCH',powerUnits:5001,reported:'A',expected:'Z'});
  assert.equal(fleet.assessFleetBand('1.5','A').status,'UNKNOWN');
  assert.equal(fleet.assessFleetBand('1','?').status,'UNKNOWN');
  assert.equal(fleet.assessFleetBand('',null).status,'UNKNOWN');
});
