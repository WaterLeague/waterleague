import { BufferAttribute, BufferGeometry } from 'three';
import type { Terrain } from '../../terrain/entity/terrain';
import type { Street } from '../entity/urban';
import { partBounds } from '../../../shared/repository/meshBounds';
import { streetDetailEnabled, streetGeometry } from './streetGeometryService';

export type StreetBuffers = {
  positions: Float32Array;
  colors: Float32Array;
  normals: Float32Array;
  bounds: Float32Array;
  ends: number[];
  sphere: number[];
};
type Part = Omit<StreetBuffers, 'ends' | 'sphere'>;
const yieldTask = () => new Promise<void>((resolve) => setTimeout(resolve, 0));
function shapeKey(value: unknown) {
  const references = new WeakMap<object, number>();
  let sequence = 0;
  // 순환 진입로와 공유 상판 참조를 보존하면서 같은 연결 그래프에 같은 캐시 키를 부여한다.
  return JSON.stringify(value, (_key, item: unknown) => {
    if (!item || typeof item !== 'object') return item;
    const reference = references.get(item);
    if (reference !== undefined) return { $geometryReference: reference };
    references.set(item, sequence++);
    return item;
  });
}

export class StreetMeshBuilder {
  private readonly cache = new Map<string, { part: Part; bytes: number }>();
  private keys = new WeakMap<Street, Map<string, string>>();
  private terrain: Terrain | null | undefined;
  private bytes = 0;
  private generated = 0;
  private reused = 0;

  constructor(private readonly maximumBytes = 48 * 1024 * 1024) {}

  get statistics() {
    return { generated: this.generated, reused: this.reused, bytes: this.bytes };
  }

  async build(
    roads: Street[],
    terrain: Terrain | null,
    detailed: boolean,
    parkingAisles: string[],
    center: [number, number] | undefined,
    signal: AbortSignal
  ): Promise<StreetBuffers> {
    signal.throwIfAborted();
    if (terrain !== this.terrain) {
      this.cache.clear();
      this.keys = new WeakMap();
      this.bytes = 0;
      this.terrain = terrain;
    }
    const aisleIds = new Set(parkingAisles);
    const hashes: Promise<void>[] = [];
    const encoder = new TextEncoder();
    const entries: { road: Street; detail: boolean; parking: boolean; key: string }[] = [];
    for (const road of roads) {
      signal.throwIfAborted();
      const detail = streetDetailEnabled(road, detailed, center);
      const parking = aisleIds.has(road.id);
      const variant = `${detail}:${parking}`;
      const saved = this.keys.get(road)?.get(variant);
      if (saved) {
        entries.push({ road, detail, parking, key: saved });
        continue;
      }
      // 이동체 전용 수면·상판 참조를 도로마다 문자열로 복제하지 않는다.
      const {
        nativeWaterDecks: _waterDecks,
        nativeWalkingDecks: _walkingDecks,
        nativeGroundCutPolygons,
        ...shape
      } = road;
      const actorOnlySupport =
        road.nativeSourceRole &&
        !road.nativePolygons &&
        !road.nativeRailPaths &&
        (!road.nativeLanePaths || road.nativeLaneClipPolygons);
      const key = shapeKey([
        {
          ...shape,
          ...(road.nativeLanePaths?.length && !road.nativeLaneClipPolygons
            ? { nativeGroundCutPolygons }
            : {}),
          ...(!actorOnlySupport
            ? { nativeWaterDecks: _waterDecks, nativeWalkingDecks: _walkingDecks }
            : {}),
        },
        detail,
        parking,
      ]);
      const entry = { road, detail, parking, key };
      entries.push(entry);
      // 큰 키를 병렬 해시하되 동시에 보관하는 원문 수를 제한한다.
      if (key.length > 256) {
        hashes.push(
          crypto.subtle.digest('SHA-256', encoder.encode(key)).then((digest) => {
            entry.key =
              'sha256:' +
              Array.from(new Uint8Array(digest), (value) =>
                value.toString(16).padStart(2, '0')
              ).join('');
          })
        );
        if (hashes.length === 32) {
          await Promise.all(hashes);
          hashes.length = 0;
        }
      }
    }
    if (hashes.length) await Promise.all(hashes);
    const wanted = new Set(entries.map((entry) => entry.key));
    const evictable = [...this.cache.keys()].filter((key) => !wanted.has(key));
    let evictionIndex = 0;
    const parts: Part[] = [];
    let lastYield = performance.now();
    for (const { road, detail, parking, key } of entries) {
      signal.throwIfAborted();
      // 같은 도로라도 형상·높이·차선·상세 단계가 달라지면 별도 메시로 계산한다.
      const found = this.cache.get(key);
      let part: Part;
      if (found) {
        this.cache.delete(key);
        this.cache.set(key, found);
        part = found.part;
        this.reused++;
      } else {
        const data = streetGeometry([road], terrain, detail, parking ? [road.id] : []);
        const geometry = new BufferGeometry();
        geometry.setAttribute('position', new BufferAttribute(data.positions, 3));
        geometry.computeVertexNormals();
        part = {
          positions: data.positions,
          colors: data.colors,
          normals: geometry.getAttribute('normal').array as Float32Array,
          bounds: partBounds(data.positions, data.ends),
        };
        geometry.dispose();
        this.generated++;
        const bytes =
          key.length * 2 + Object.values(part).reduce((sum, value) => sum + value.byteLength, 0);
        if (bytes <= this.maximumBytes) {
          while (this.bytes + bytes > this.maximumBytes && evictionIndex < evictable.length) {
            const oldest = evictable[evictionIndex++];
            this.bytes -= this.cache.get(oldest)!.bytes;
            this.cache.delete(oldest);
            this.keys = new WeakMap();
          }
          // 현재 시야 전체가 한도를 넘을 때 필요한 캐시끼리 밀어내며 전부 재생성하지 않는다.
          if (this.bytes + bytes <= this.maximumBytes) {
            this.cache.set(key, { part, bytes });
            this.bytes += bytes;
          }
        }
      }
      // 상한 안에 보관한 형상만 키를 재사용하고 퇴출 시 참조를 함께 비운다.
      if (this.cache.has(key)) {
        const variants = this.keys.get(road) ?? new Map<string, string>();
        variants.set(`${detail}:${parking}`, key);
        this.keys.set(road, variants);
      }
      parts.push(part);
      if (performance.now() - lastYield >= 8) {
        // 타일을 이동하는 동안 취소 메시지를 처리하되 완성된 개별 형상은 재사용한다.
        await yieldTask();
        signal.throwIfAborted();
        lastYield = performance.now();
      }
    }
    const size = parts.reduce((sum, part) => sum + part.positions.length, 0);
    const positions = new Float32Array(size),
      colors = new Float32Array(size),
      normals = new Float32Array(size),
      bounds = new Float32Array(parts.length * 6),
      ends: number[] = [];
    let offset = 0;
    for (const [i, part] of parts.entries()) {
      positions.set(part.positions, offset);
      colors.set(part.colors, offset);
      normals.set(part.normals, offset);
      bounds.set(part.bounds, i * 6);
      offset += part.positions.length;
      ends.push(offset / 9);
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(positions, 3));
    geometry.computeBoundingSphere();
    const sphere = [...geometry.boundingSphere!.center.toArray(), geometry.boundingSphere!.radius];
    geometry.dispose();
    // 전송할 합본과 보관할 개별 버퍼를 분리해 전송 후에도 캐시를 사용할 수 있게 한다.
    return { positions, colors, normals, bounds, ends, sphere };
  }
}
