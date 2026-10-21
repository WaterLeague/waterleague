import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js';
const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const {values} = parseArgs({options:{report:{type:'string'}}});
assert(values.report);
const hash = data => createHash('sha256').update(data).digest('hex');
const base = path.join(root,'frontend/public/data');
const raw = await readFile(path.join(base,'seoul-bridges-v1/index.json')), index = JSON.parse(raw);
const info = JSON.parse(await readFile(path.join(base,'seoul-terrain-native-v1/terrain.json')));
const files = {};
for (const [name, entry] of Object.entries(info.files)) {
  const bytes = await readFile(path.join(base,'seoul-terrain-native-v1',name));
  assert.equal(hash(bytes),entry.sha256);
  files[name]=bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength);
}
const terrain={...info,heights:new Float32Array(files['height-f32le.bin']),
  districts:new Uint8Array(files['district-u8.bin']),cover:new Uint8Array(files['cover-u8.bin'])};
const server=await createServer({root:path.join(root,'frontend'),server:{middlewareMode:true,hmr:false},appType:'custom'});
try {
  const {nativeBridgesDto}=await server.ssrLoadModule('/src/domains/urban/dto/nativeBridgeDto.ts');
  const {NATIVE_BRIDGE_HASH}=await server.ssrLoadModule('/src/domains/urban/repository/nativeBridgeVersion.ts');
  const {nativeStreets}=await server.ssrLoadModule('/src/domains/urban/service/nativeStreetService.ts');
  const {streetGeometry,streetHeight}=await server.ssrLoadModule('/src/domains/urban/service/streetGeometryService.ts');
  const {bridgePierPositions}=await server.ssrLoadModule('/src/domains/urban/service/nativeBridgeStructureService.ts');
  const {nativeBridgeHeight,connectBridgeDatums}=await server.ssrLoadModule('/src/domains/urban/service/nativeBridgeService.ts');
  const {terrainMeshHeight}=await server.ssrLoadModule('/src/domains/terrain/service/terrainDrapeService.ts');
  assert.equal(hash(raw),NATIVE_BRIDGE_HASH);
  const packed=await readFile(path.join(base,'seoul-bridges-v1',index.file));
  assert.equal(hash(packed),index.storedSha256);
  const data=gunzipSync(packed,{maxOutputLength:index.bytes});
  assert.equal(hash(data),index.sha256);
  const body=nativeBridgesDto.parse(JSON.parse(data));
  const names=new Set(['한강대교','잠수교','방화대교','행주대교','마포대교','반포대교','한남대교','동호대교','한강철교','당산철교','잠실철교',
    '양화대교','서강대교','성산대교','월드컵대교','가양대교','성수대교','청담대교','영동대교','잠실대교','올림픽대교']);
  body.groups=connectBridgeDatums(body.groups);
  const groups=body.groups.filter(g=>g.role==='PEDESTRIAN_OVERPASS_AREA'||g.names?.some(n=>names.has(n)));
  const checks=[];
  for (const group of groups) {
    assert(group.names.length<=1 && new Set(group.kinds.map(k=>k==='고가차도'?'도로교':k)).size<=1);
    const streets=nativeStreets([], [group]);
    let pedestrianSamples=0;
    for(const street of streets.filter(s=>s.walk&&s.nativeWalkingDecks))
      for(let i=1;i<street.coordinates.length;i++){
        const a=street.coordinates[i-1],b=street.coordinates[i],count=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/15));
        for(let j=0;j<=count;j++){
          const p=[a[0]+(b[0]-a[0])*j/count,a[1]+(b[1]-a[1])*j/count];
          assert(streetHeight(terrain,p,street)>terrainMeshHeight(terrain,p)+.25,`교량 보행로 수면 겹침: ${group.names}`);
          pedestrianSamples++;
        }
      }
    const start=performance.now(), fine=streetGeometry(streets,terrain,true), fineMs=performance.now()-start;
    const coarseStart=performance.now(), coarse=streetGeometry(streets,terrain,false), coarseMs=performance.now()-coarseStart;
    assert(fine.positions.every(Number.isFinite) && fine.colors.every(Number.isFinite));
    assert(fine.positions.length>0 && fine.ends.length===streets.length);
    assert(coarse.positions.length<=fine.positions.length);
    const piers=bridgePierPositions(group.outlinePolygons??group.polygons);
    const length=Math.hypot(group.bounds[2]-group.bounds[0],group.bounds[3]-group.bounds[1]);
    if(length>500) assert(piers.length>0,'긴 교량의 교각 누락');
    checks.push({sourceId:group.id,names:group.names,kinds:group.kinds,
      extentM:length,sourcePieces:group.sourceIds.length,profiles:group.profiles.length,
      maximumSourcePathSpanM:Math.max(0,...group.profiles.map(p=>p.span[1]-p.span[0])),
      pierCount:piers.length,pedestrianSamples,displayDeckHeightM:nativeBridgeHeight(terrain,group.displayDatumPolygons??group.polygons,streets.find(s=>s.nativeDeckLiftM)?.nativeDeckLiftM),
      fineVertices:fine.positions.length/3,coarseVertices:coarse.positions.length/3,fineMs,coarseMs});
  }
  assert(checks.some(g=>g.names.includes('마포대교')&&g.maximumSourcePathSpanM>1000));
  assert(checks.some(g=>g.names.includes('당산철교')&&g.maximumSourcePathSpanM>1000));
  const report={schemaVersion:1,status:'PASS',indexSha256:hash(raw),groups:body.groups.length,
    testedHanRiverGroups:groups.filter(g=>g.names?.some(n=>names.has(n))).length,testedFootbridgeGroups:groups.filter(g=>g.role==='PEDESTRIAN_OVERPASS_AREA').length,checks,scope:'원본과 실제 지형을 사용한 CPU 형상·연결 검사. 현장 제원 또는 브라우저 FPS 검증과 구분'};
  await writeFile(path.resolve(values.report),JSON.stringify(report)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:report.status,groups:report.groups,testedHanRiverGroups:report.testedHanRiverGroups,testedFootbridgeGroups:report.testedFootbridgeGroups,pedestrianSamples:checks.reduce((n,c)=>n+c.pedestrianSamples,0)}));
} finally { await server.close(); }
