import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile,writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { gunzipSync } from 'node:zlib';
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const {values}=parseArgs({options:{report:{type:'string'},samples:{type:'string'}}});
assert(values.report&&values.samples);
const hash=(raw)=>createHash('sha256').update(raw).digest('hex');
const reportPath=path.resolve(values.report),sampleRaw=await readFile(path.resolve(values.samples));
const indexRaw=await readFile(path.join(root,'frontend/public/data/seoul-features-v1/index.json'));
const server=await createServer({root:path.join(root,'frontend'),server:{middlewareMode:true},appType:'custom'});
try{
  const {topographyIndexDto,topographyTileDto}=await server.ssrLoadModule('/src/domains/topography/dto/topographyDto.ts');
  const {topographyGeometry}=await server.ssrLoadModule('/src/domains/topography/service/topographyGeometryService.ts');
  const {TOPOGRAPHY_HASH}=await server.ssrLoadModule('/src/domains/topography/repository/topographyRepository.ts');
  assert.equal(hash(indexRaw),TOPOGRAPHY_HASH);
  const index=topographyIndexDto.parse(JSON.parse(indexRaw)),samples=topographyTileDto.parse(JSON.parse(sampleRaw));
  const before=JSON.stringify(samples),layers=[];
  for(let layer=0;layer<121;layer++){
    const tile={schemaVersion:1,id:'0_0',points:samples.points.filter((row)=>row[0]===layer),
      lines:samples.lines.filter((row)=>row[0]===layer),areas:samples.areas.filter((row)=>row[0]===layer)};
    assert.equal(tile.points.length+tile.lines.length+tile.areas.length,1,'실제 원본 대표 도형 필요');
    const mesh=topographyGeometry(tile,index.layers,null,false),plan=topographyGeometry(tile,index.layers,null,true);
    assert(mesh.positions.length+mesh.lines.length+mesh.models.reduce((n,m)=>n+m.matrices.length,0)+mesh.labels.length>0,'3D 레이어 표시 누락');
    assert(plan.plan.some((part)=>part.areas||part.lines||part.points),'2D 레이어 표시 누락');
    for(const value of Object.values(mesh))if(value instanceof Float32Array)assert(value.every(Number.isFinite),'표시 좌표·법선 유한값');
    layers.push({id:index.layers[layer].id,renderer:index.layers[layer].renderer,mesh:true,plan:true});
  }
  assert.equal(JSON.stringify(samples),before,'원형 좌표·배열 변경 금지');
  const stress=[];
  const terrainBase=path.join(root,'frontend/public/data/seoul-terrain-native-v1');
  const terrainInfo=JSON.parse(await readFile(path.join(terrainBase,'terrain.json'))),terrainFiles={};
  for(const [name,entry] of Object.entries(terrainInfo.files)){
    const bytes=await readFile(path.join(terrainBase,name));assert.equal(hash(bytes),entry.sha256);
    terrainFiles[name]=bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength);
  }
  const terrain={...terrainInfo,heights:new Float32Array(terrainFiles['height-f32le.bin']),
    districts:new Uint8Array(terrainFiles['district-u8.bin']),cover:new Uint8Array(terrainFiles['cover-u8.bin'])};
  for(const entry of [...index.tiles].sort((a,b)=>b.bytes-a.bytes).slice(0,3)){
    const packed=await readFile(path.join(root,'frontend/public/data/seoul-features-v1',entry.file));
    const raw=gunzipSync(packed,{maxOutputLength:entry.bytes});assert.equal(hash(raw),entry.sha256);
    const started=performance.now(),tile=topographyTileDto.parse(JSON.parse(raw));
    const validated=performance.now(),mesh=topographyGeometry(tile,index.layers,terrain,false),finished=performance.now();
    assert(mesh.positions.every(Number.isFinite)&&mesh.lines.every(Number.isFinite));
    const bytes=Object.values(mesh).reduce((sum,value)=>sum+(ArrayBuffer.isView(value)?value.byteLength:0),0)+mesh.models.reduce((n,m)=>n+m.matrices.byteLength,0);
    stress.push({id:entry.id,sourceBytes:entry.bytes,validationMs:validated-started,geometryMs:finished-validated,bufferBytes:bytes,
      displayRecords:mesh.counts});
  }
  const report={schemaVersion:1,status:'PASS',indexSha256:hash(indexRaw),samplesSha256:hash(sampleRaw),
    layers,layersWithRealSource2dAnd3d:layers.length,sourceCoordinatesUnchanged:true,stress,
    stressTerrainScope:'실제 표시 지형과 큰 타일 3개의 CPU 형상·원문 해독 검사, 브라우저 프레임 성능과 구분'};
  await writeFile(reportPath,JSON.stringify(report)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:report.status,layers:layers.length,stress}));
}finally{await server.close();}
