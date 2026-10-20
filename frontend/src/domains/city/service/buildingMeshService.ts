import type { CityBuilding } from '../entity/city';
import {
  buildingMeshCapacity,
  buildBuildingMesh,
  type BuildingMeshData,
} from './buildingGeometryService';
import { buildingMeshKey } from './buildingMeshCache';

type Part = Omit<BuildingMeshData, 'ends'>;
const yieldTask = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

export class BuildingMeshBuilder {
  private readonly cache = new Map<string, { part: Part; bytes: number }>();
  private bytes = 0;
  private generated = 0;
  private reused = 0;

  constructor(private readonly maximumBytes = 32 * 1024 * 1024) {}

  get statistics() {
    return { generated: this.generated, reused: this.reused, bytes: this.bytes };
  }

  async build(buildings: CityBuilding[], signal: AbortSignal): Promise<BuildingMeshData> {
    signal.throwIfAborted();
    buildingMeshCapacity(buildings);
    let lastYield = performance.now();
    const entries: { building: CityBuilding; key: string }[] = [];
    for (const building of buildings) {
      entries.push({ building, key: buildingMeshKey([building]) });
      if (performance.now() - lastYield >= 8) {
        await yieldTask();
        signal.throwIfAborted();
        lastYield = performance.now();
      }
    }
    const wanted = new Set(entries.map((entry) => entry.key));
    const evictable = [...this.cache.keys()].filter((key) => !wanted.has(key));
    let evictionIndex = 0;
    const parts: Part[] = [];
    for (const { building, key } of entries) {
      signal.throwIfAborted();
      const found = this.cache.get(key);
      let part: Part;
      if (found) {
        this.cache.delete(key);
        this.cache.set(key, found);
        part = found.part;
        this.reused++;
      } else {
        const data = buildBuildingMesh([building]);
        part = { positions: data.positions, normals: data.normals, bounds: data.bounds };
        this.generated++;
        // 부분 뷰 길이가 아닌 실제 보관 버퍼를 계산해 메모리 한도를 지킨다.
        const bytes =
          key.length * 2 +
          part.positions.buffer.byteLength +
          part.normals.buffer.byteLength +
          part.bounds.buffer.byteLength;
        if (bytes <= this.maximumBytes) {
          while (this.bytes + bytes > this.maximumBytes && evictionIndex < evictable.length) {
            const oldest = evictable[evictionIndex++];
            this.bytes -= this.cache.get(oldest)!.bytes;
            this.cache.delete(oldest);
          }
          // 큰 시야에서도 현재 요청의 기존 형상끼리 밀어내며 전부 재생성하지 않는다.
          if (this.bytes + bytes <= this.maximumBytes) {
            this.cache.set(key, { part, bytes });
            this.bytes += bytes;
          }
        }
      }
      parts.push(part);
      if (performance.now() - lastYield >= 8) {
        await yieldTask();
        signal.throwIfAborted();
        lastYield = performance.now();
      }
    }
    const size = parts.reduce((sum, part) => sum + part.positions.length, 0);
    const positions = new Float32Array(size),
      normals = new Float32Array(size),
      bounds = new Float32Array(parts.length * 6),
      ends: number[] = [];
    let offset = 0;
    for (const [index, part] of parts.entries()) {
      positions.set(part.positions, offset);
      normals.set(part.normals, offset);
      bounds.set(part.bounds, index * 6);
      offset += part.positions.length;
      ends.push(offset / 9);
      if (performance.now() - lastYield >= 8) {
        await yieldTask();
        signal.throwIfAborted();
        lastYield = performance.now();
      }
    }
    // 합본만 전송해 부분 캐시의 버퍼와 건물별 클릭 범위를 보존한다.
    return { positions, normals, bounds, ends };
  }
}
