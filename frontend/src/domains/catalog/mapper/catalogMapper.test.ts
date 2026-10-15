import { describe,it,expect } from 'vitest';
import snapshot from '../../../../public/data/seongsu.json';
import { mapDto } from '../dto/catalogDto';
import { toCandidateMap } from './catalogMapper';

describe('공개 맵 계약',()=>{
  it('실제 스냅샷을 형상·도로로 분리하고 승인 상태를 보존',()=>{
    const map=toCandidateMap(mapDto.parse(snapshot));
    expect(map.buildings.length).toBe(94);
    expect(map.snapshot.officialEvaluationAvailable).toBe(false);
    expect(map.buildings.every(b=>b.coordinates.length>=4)).toBe(true);
  });
  it('공식 모델로 위장한 탐색 자료 거부',()=>{
    expect(mapDto.safeParse({...snapshot,officialEvaluationAvailable:true}).success).toBe(false);
  });
  it('비유한 높이를 가진 형상 거부',()=>{
    const data=structuredClone(snapshot);
    const building=data.features.find(f=>f.kind==='building')!;
    building.heightM=Number.NaN;
    expect(mapDto.safeParse(data).success).toBe(false);
  });
});
