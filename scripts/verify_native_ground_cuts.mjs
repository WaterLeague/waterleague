import {readFile,writeFile} from 'node:fs/promises';import{gunzipSync}from'node:zlib';import{createServer}from'../frontend/node_modules/vite/dist/node/index.js';
import{parseArgs}from'node:util';import assert from'node:assert/strict';
const {values}=parseArgs({options:{report:{type:'string'}}});assert(values.report);
const base='frontend/public/data/';
const body=JSON.parse(gunzipSync(await readFile(base+'seoul-bridges-v1/structures.json.gz'))); const groups=body.groups.map(g=>({...g,displayWaterPolygons:body.waterPolygons}));
const index=JSON.parse(await readFile(base+'seoul-features-v1/index.json'));
const bounds=[...(body.waterPolygons??groups.flatMap(g=>g.groundCutPolygons??[])),...groups.flatMap(g=>(g.surfaceCuts??[]).flatMap(c=>c.polygons))].map(p=>p[0].reduce((b,q)=>[Math.min(b[0],q[0]),Math.min(b[1],q[1]),Math.max(b[2],q[0]),Math.max(b[3],q[1])],[Infinity,Infinity,-Infinity,-Infinity]));
const server=await createServer({root:'frontend',server:{middlewareMode:true,hmr:false},appType:'custom'});
try{
const{NativeGroundCuts}=await server.ssrLoadModule('/src/domains/urban/service/nativeGroundCutService.ts');const{topographyGeometry}=await server.ssrLoadModule('/src/domains/topography/service/topographyGeometryService.ts');const cuts=new NativeGroundCuts(groups);let tiles=0,areas=0,changed=0,bridgeCopies=0;
for(const entry of index.tiles){const b=entry.bounds;if(!bounds.some(c=>c[0]<=b[2]&&c[2]>=b[0]&&c[1]<=b[3]&&c[3]>=b[1]))continue;
const tile=JSON.parse(gunzipSync(await readFile(base+'seoul-features-v1/'+entry.file)));
const bridges=tile.areas.filter(([layer])=>['BRIDGE_AREA','PEDESTRIAN_OVERPASS_AREA','GRADE_SEPARATED_INTERSECTION_AREA'].includes(index.layers[layer].role));
const mesh=topographyGeometry({...tile,areas:bridges,points:[],lines:[]},index.layers,null,false,true);assert.equal(mesh.positions.length+mesh.lines.length,0);bridgeCopies+=bridges.length;
for(const [layer,fid,polygons]of tile.areas){if(!['ROAD_AREA','SIDEWALK_AREA','RAILWAY_AREA','INTERSECTION_AREA','INTERCHANGE_AREA','CROSSWALK_AREA','TRAFFIC_SAFETY_AREA'].includes(index.layers[layer].role))continue;
try{const result=cuts.surface(polygons,index.layers[layer].role,fid);assert(result.flat(3).every(Number.isFinite));areas++;if(result!==polygons)changed++;}catch(e){throw new Error('원 타일 '+entry.id+' fid '+fid+': '+e.message);}}
tiles++;if(tiles%50===0)console.log(JSON.stringify({tiles,areas,changed}));
}
const result={status:'PASS',tiles,areas,changed,bridgeCopies,scope:'수면·육상 교량과 겹치는 모든 원 타일의 통행면 절단과 원 교량 지면 사본 제거 검사'};await writeFile(values.report,JSON.stringify(result)+'\n',{flag:'wx'});console.log(JSON.stringify(result));
}finally{await server.close();}
