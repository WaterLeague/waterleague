import type { CityBuilding } from '../entity/city';
import type { BuildingMeshData } from './buildingGeometryService';

export function buildingMeshKey(buildings: CityBuilding[]): string {
  // 같은 식별자라도 형상·높이·표고가 바뀌면 이전 표시 메시를 재사용하지 않는다.
  return JSON.stringify(buildings.map((b) => [b.id, b.polygons, b.heightM, b.baseElevationM ?? 0]));
}

export class BuildingMeshCache {
  private readonly values = new Map<string, { data: BuildingMeshData; bytes: number }>();
  private bytes = 0;

  constructor(private readonly capacityBytes = 32 * 1024 * 1024) {}

  get(key: string): BuildingMeshData | undefined {
    const value = this.values.get(key);
    if (!value) return undefined;
    this.values.delete(key);
    this.values.set(key, value);
    return value.data;
  }

  put(key: string, data: BuildingMeshData): void {
    const existing = this.values.get(key);
    if (existing) {
      this.bytes -= existing.bytes;
      this.values.delete(key);
    }
    const bytes =
      key.length * 2 +
      data.positions.buffer.byteLength +
      data.normals.buffer.byteLength +
      data.bounds.buffer.byteLength +
      data.ends.length * 8;
    if (bytes > this.capacityBytes) return;
    while (this.bytes + bytes > this.capacityBytes && this.values.size) {
      const oldest = this.values.keys().next().value!;
      this.bytes -= this.values.get(oldest)!.bytes;
      this.values.delete(oldest);
    }
    this.values.set(key, { data, bytes });
    this.bytes += bytes;
  }

  clear(): void {
    this.values.clear();
    this.bytes = 0;
  }
}
