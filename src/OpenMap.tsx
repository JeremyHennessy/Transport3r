import {useEffect,useRef,useState} from 'react';
import type {Map as MapLibreMap, Marker} from 'maplibre-gl';
import {DISPLAY_BOUNDARIES,REGIONS,type MapRegion} from './openGeography';
import {loadMapRenderer} from './mapRuntime';

export function OpenMap({regions,selected,onSelect,label}:{regions:MapRegion[];selected?:string;onSelect:(code:string)=>void;label:string}) {
  const element=useRef<HTMLDivElement>(null),map=useRef<MapLibreMap|null>(null),markers=useRef<Marker[]>([]),callback=useRef(onSelect);
  callback.current=onSelect;
  const [ready,setReady]=useState(false),[error,setError]=useState('');
  useEffect(()=>{
    let active=true;setReady(false);setError('');
    void loadMapRenderer().then(module=>{
      if(!active||!element.current)return;
      const instance=new module.Map({container:element.current,center:[-98,38],zoom:3,minZoom:1,maxZoom:9,attributionControl:false,
        style:{version:8,sources:{regions:{type:'geojson',data:DISPLAY_BOUNDARIES}},layers:[
          {id:'background',type:'background',paint:{'background-color':'#edf3f7'}},
          {id:'land',type:'fill',source:'regions',paint:{'fill-color':'#d5e5e6','fill-opacity':0.94}},
          {id:'borders',type:'line',source:'regions',paint:{'line-color':'#8aaeb1','line-width':1}},
        ]}});
      map.current=instance;
      instance.addControl(new module.NavigationControl({showCompass:false}),'top-right');
      instance.addControl(new module.AttributionControl({compact:false,customAttribution:'U.S. Census 2025 | Simplified display geography'}),'bottom-right');
      instance.on('load',()=>{if(active)setReady(true);});
      instance.on('error',()=>{if(active)setError('Interactive map unavailable. The regional list below remains usable.');});
    }).catch(()=>{if(active)setError('Interactive map unavailable. The regional list below remains usable.');});
    return()=>{active=false;markers.current.forEach(marker=>marker.remove());markers.current=[];map.current?.remove();map.current=null;};
  },[]);
  useEffect(()=>{
    if(!ready)return;
    let active=true;
    void loadMapRenderer().then(module=>{
      if(!active||!map.current)return;
      markers.current.forEach(marker=>marker.remove());markers.current=[];
      for(const region of regions){
        const coordinate=REGIONS.get(region.code);if(!coordinate||!region.count)continue;
        const button=document.createElement('button');button.type='button';button.className='t3-map-marker'+(selected===region.code?' selected':'');
        button.setAttribute('aria-label',`${region.code}: ${region.count.toLocaleString()} records; regional aggregate, not a precise location`);
        button.title=`${region.code}: ${region.count.toLocaleString()} records${region.inspections===undefined?'':`; ${region.inspections} inspection, ${region.crashes} crash, ${region.reporting} reporting-jurisdiction records`}`;
        const code=document.createElement('strong'),count=document.createElement('span');code.textContent=region.code;count.textContent=region.count.toLocaleString();button.append(code,count);
        button.addEventListener('click',()=>callback.current(region.code));
        markers.current.push(new module.Marker({element:button}).setLngLat(coordinate).addTo(map.current));
      }
      const points=regions.filter(region=>region.count>0).map(region=>REGIONS.get(region.code)!).filter(Boolean);
      if(points.length){
        const chosen=selected?REGIONS.get(selected):undefined;
        if(chosen)map.current.jumpTo({center:chosen,zoom:4});
        else map.current.fitBounds([[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1]))],[Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))]],{padding:65,maxZoom:4,duration:0});
      }
    }).catch(()=>{if(active)setError('Map markers unavailable. Use the regional list below.');});
    return()=>{active=false;};
  },[ready,regions,selected]);
  return <div className="t3-open-map-shell"><div ref={element} className="t3-open-map" role="region" aria-label={label} data-map-ready={ready&&!error?'true':'false'}/>
    <button type="button" className="t3-map-reset" onClick={()=>map.current?.jumpTo({center:[-98,38],zoom:3})}>Reset map view</button>
    {error?<p role="status" className="t3-map-error">{error}</p>:!ready?<p role="status" className="t3-map-loading">Loading open-source map...</p>:null}
    <div className="t3-map-credit">MapLibre GL JS · local Census boundaries · no external tiles or address sharing</div></div>;
}
