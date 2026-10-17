import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import oldMap from '../../../../public/data/seongsu.json';
import newMap from '../../../../public/data/seongsu-ngii-v2.json';
import oldModel from '../../../../../data/models/seongsu-lab.json';
import newModel from '../../../../../data/models/seongsu-ngii-v2-421-20240718.json';
import { mapDto } from '../dto/catalogDto';
import { toCandidateMap } from '../mapper/catalogMapper';
import { buildingPolygons } from './mapGeometryService';
import {
  labelLeaderEnd,
  positionSceneLabels,
  type LabelBounds,
  type SceneLabel,
} from './sceneLabelService';

function verifyVisible(labels: SceneLabel[], bounds: LabelBounds) {
  for (const [index, label] of labels.entries()) {
    expect(label.x - label.width / 2).toBeGreaterThanOrEqual(bounds.left);
    expect(label.x + label.width / 2).toBeLessThanOrEqual(bounds.right);
    expect(label.y - label.height / 2).toBeGreaterThanOrEqual(bounds.top);
    expect(label.y + label.height / 2).toBeLessThanOrEqual(bounds.bottom);
    for (const other of labels.slice(0, index))
      expect(
        Math.abs(label.x - other.x) >= (label.width + other.width) / 2 + 4 ||
          Math.abs(label.y - other.y) >= (label.height + other.height) / 2 + 4
      ).toBe(true);
  }
}

describe('3D 화면 구역 표식', () => {
  it('두 실제 지도의 13개 구역을 작은 화면·회전·탑뷰에서 겹치지 않게 표시', () => {
    for (const [snapshot, model] of [
      [oldMap, oldModel],
      [newMap, newModel],
    ] as const) {
      const map = toCandidateMap(mapDto.parse(snapshot));
      for (const [width, height] of [
        [320, 460],
        [548, 500],
        [1280, 720],
      ])
        for (const position of [
          [310, 320, 380],
          [-310, 160, 380],
          [0, 460, 0.1],
          [-280, 400, -280],
        ]) {
          const camera = new THREE.OrthographicCamera(
            -width / 2,
            width / 2,
            height / 2,
            -height / 2,
            0.1,
            1500
          );
          camera.position.set(position[0], position[1], position[2]);
          camera.lookAt(0, 0, 0);
          camera.updateMatrixWorld();
          let x = 0,
            y = 0;
          for (const building of map.buildings)
            for (const [east, north] of buildingPolygons(building).flatMap((polygon) => polygon[0]))
              for (const elevation of [0, building.heightM]) {
                const p = new THREE.Vector3(east, elevation, -north).applyMatrix4(
                  camera.matrixWorldInverse
                );
                x = Math.max(x, Math.abs(p.x));
                y = Math.max(y, Math.abs(p.y));
              }
          camera.zoom = Math.min(width / (2 * x + 60), (height - 110) / (2 * y + 50));
          camera.updateProjectionMatrix();
          const labels = model.cells.map((cell) => {
            const p = new THREE.Vector3(
              cell.center[0],
              cell.heightM + 0.7,
              -cell.center[1]
            ).project(camera);
            return {
              id: cell.id,
              x: ((p.x + 1) * width) / 2,
              y: ((1 - p.y) * height) / 2,
              width: cell.kind === 'GROUND' ? 56 : 36,
              height: 26,
              priority: cell.id === 'G1' ? 3 : 0,
            };
          });
          const original = structuredClone(labels);
          const bounds = { left: 12, top: 58, right: width - 60, bottom: height - 70 };
          const result = positionSceneLabels(labels, bounds);
          expect(result).toHaveLength(13);
          verifyVisible(result, bounds);
          expect(positionSceneLabels(labels, bounds)).toEqual(result);
          expect(labels).toEqual(original);
        }
    }
  });

  it('표시 공간이 부족하면 선택 구역을 우선하고 겹치는 표식은 생략', () => {
    const labels = ['R1', 'G1', 'G2'].map((id) => ({
      id,
      x: 30,
      y: 30,
      width: 40,
      height: 26,
      priority: id === 'G1' ? 3 : 0,
    }));
    const bounds = { left: 0, top: 0, right: 42, bottom: 28 };
    const result = positionSceneLabels(labels, bounds);
    expect(result.map((label) => label.id)).toEqual(['G1']);
    verifyVisible(result, bounds);
    expect(positionSceneLabels(labels, { ...bounds, right: 20 })).toEqual([]);
  });

  it('연결선은 표식의 가장자리에서 끝나며 글자를 가리지 않음', () => {
    const label = { id: 'G1', x: 100, y: 100, width: 40, height: 26, priority: 0 };
    expect(labelLeaderEnd({ x: 100, y: 150 }, label)).toEqual({ x: 100, y: 113 });
    expect(labelLeaderEnd({ x: 180, y: 100 }, label)).toEqual({ x: 120, y: 100 });
    expect(labelLeaderEnd({ x: 100, y: 100 }, label)).toEqual({ x: 100, y: 100 });
  });
});
