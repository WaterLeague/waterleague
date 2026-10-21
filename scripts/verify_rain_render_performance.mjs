import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { stripTypeScriptTypes } from 'node:module';
import { resolve } from 'node:path';
const root = resolve(import.meta.dirname, '..');
const output = process.argv[2];
assert(output, '새 검증 결과 파일 경로 필요');
const baselineRef = process.argv[3] ?? '93d5ed97';
assert(/^[a-f0-9]{7,40}$/.test(baselineRef), '기준 커밋 해시 필요');
const sourcePath = 'frontend/src/domains/rainfall/service/rainEffectService.ts';
const oldSource = execFileSync('git', ['show', `${baselineRef}:${sourcePath}`], { cwd: root, encoding: 'utf8' });
const newSource = await readFile(resolve(root, sourcePath), 'utf8');
const load = (source) => import('data:text/javascript;base64,' + Buffer.from(stripTypeScriptTypes(source)).toString('base64'));
const [before, after] = await Promise.all([load(oldSource), load(newSource)]);
const rawCity = await readFile(resolve(root, 'frontend/public/data/seoul-native-v1/city.json'));
const city = JSON.parse(rawCity);
const sha = (value) => createHash('sha256').update(value).digest('hex');
const median = (values) => [...values].sort((a,b)=>a-b)[Math.floor(values.length/2)];
const scenarios = [{ center: [0,0], distance:35000 }, ...city.districts.filter((_,i)=>i%6===0).map(d=>({ center:d.center, distance:3000 }))];
const results=[];
for (const scenario of scenarios) {
  const { x, y, radius } = before.rainSamplingWindow(scenario.center, scenario.distance);
  const visible = city.districts.filter(d => d.polygons.some(p => {
    const xs = p[0].map(v=>v[0]), ys = p[0].map(v=>v[1]);
    return Math.max(...xs)>=x-radius && Math.min(...xs)<=x+radius && Math.max(...ys)>=y-radius && Math.min(...ys)<=y+radius;
  }));
  const count=Math.floor(Math.min(6000/Math.max(1,visible.length),scenario.distance<9000?1000:200));
  const measure = (service) => {
    const start = performance.now();
    const seeds = visible.flatMap(d => service.rainParticleSeeds(d.polygons, [x,y], radius, count));
    return { ms: performance.now()-start, seeds };
  };
  const times = { before: [], after: [] }; let original, optimized;
  for(let pass=0;pass<7;pass++) {
    for (const key of pass%2 ? ['after','before'] : ['before','after']) {
      const result=measure(key==='before' ? before : after);
      times[key].push(result.ms);
      if(key==='before') original=result.seeds; else optimized=result.seeds;
    }
  }
  assert.deepEqual(optimized, original, '원 입자 좌표·위상 누락 또는 변경');
  const beforeMedianMs=median(times.before.slice(1)), afterMedianMs=median(times.after.slice(1));
  results.push({ ...scenario, districts:visible.length, particles:original.length, outputSha256:sha(JSON.stringify(original)), beforeMedianMs, afterMedianMs, speedup:beforeMedianMs/afterMedianMs, timesMs:times });
}
const report = {
  schemaVersion:1, status:'PASS', recordedAt:new Date().toISOString(),
  scope:'서울 원 경계의 동일 표시 입자 CPU 생성. 균일 표시 밀도의 시험 조건이며 실제 날씨·브라우저 FPS 아님.',
  nodeVersion:process.version, baselineRef, sourceCitySha256:sha(rawCity), beforeSourceSha256:sha(oldSource), afterSourceSha256:sha(newSource),
  iterations:7, timingPolicy:'첫 실행 별도 보존, 이후 6회 중앙값, 전후 교차 실행', results,
};
await writeFile(resolve(root,output),JSON.stringify(report,null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify(results.map(({timesMs,...value})=>value),null,2));
