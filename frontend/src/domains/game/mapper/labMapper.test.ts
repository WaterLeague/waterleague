import { describe, expect, it } from 'vitest';
import model from '../../../../../data/models/seongsu-lab.json';
import { mapLab } from './labMapper';
const lab = () => ({ modelHash: 'a'.repeat(64), model: structuredClone(model) });
describe('실험 계약', () => {
  it('실제 커밋 자료의 원화·시간·면적 계약 수용', () => {
    expect(mapLab(lab()).model.currency).toBe('KRW');
  });
  it('단위 변경과 강우 결측·총량 불일치 거부', () => {
    const a = lab();
    a.model.currency = 'POINT';
    expect(() => mapLab(a)).toThrow();
    const b = lab();
    b.model.rainfall.depthsMm.pop();
    expect(() => mapLab(b)).toThrow();
    const c = lab();
    c.model.rainfall.totalDepthMm += 1;
    expect(() => mapLab(c)).toThrow();
  });
  it('중복 구역·면적 초과 거부', () => {
    const a = lab();
    a.model.cells.push(a.model.cells[0]);
    expect(() => mapLab(a)).toThrow();
    const b = lab();
    b.model.cells[0].maxAreaM2 = b.model.cells[0].areaM2 + 1;
    expect(() => mapLab(b)).toThrow();
  });
});
