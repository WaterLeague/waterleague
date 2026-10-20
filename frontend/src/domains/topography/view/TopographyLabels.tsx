import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Matrix4, Vector3 } from 'three';
import type { TopographyView } from '../entity/topography';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainMeshHeight } from '../../terrain/service/terrainDrapeService';
export function TopographyLabels({
  value,
  terrain,
  distance,
}: {
  value: TopographyView;
  terrain: Terrain | null;
  distance: number;
}) {
  const { gl, size, camera } = useThree();
  const canvas = useMemo(() => {
    const element = document.createElement('canvas');
    element.setAttribute('aria-label', '공개 수치지형도 지명');
    element.setAttribute('role', 'img');
    element.style.cssText =
      'position:absolute;inset:0;pointer-events:none;z-index:3;width:100%;height:100%;';
    return element;
  }, []);
  const labels = useMemo(() => value.tiles.flatMap((tile) => tile.data.labels), [value.tiles]);
  const previous = useRef({
    matrix: new Matrix4(),
    labels: null as typeof labels | null,
    visible: false,
    width: 0,
    height: 0,
  });
  const point = useMemo(() => new Vector3(), []);
  useEffect(() => {
    gl.domElement.parentElement?.append(canvas);
    return () => canvas.remove();
  }, [gl, canvas]);
  useFrame(() => {
    const visible = distance < 3500,
      last = previous.current;
    if (
      last.matrix.equals(camera.matrixWorldInverse) &&
      last.labels === labels &&
      last.visible === visible &&
      last.width === size.width &&
      last.height === size.height
    )
      return;
    last.matrix.copy(camera.matrixWorldInverse);
    last.labels = labels;
    last.visible = visible;
    last.width = size.width;
    last.height = size.height;
    const ratio = Math.min(1.5, devicePixelRatio || 1);
    canvas.width = Math.round(size.width * ratio);
    canvas.height = Math.round(size.height * ratio);
    const context = canvas.getContext('2d');
    if (!context) return;
    context.scale(ratio, ratio);
    context.clearRect(0, 0, size.width, size.height);
    if (!visible) return;
    context.font = '11px Pretendard, sans-serif';
    context.textAlign = 'center';
    context.lineJoin = 'round';
    context.lineWidth = 3;
    const occupied: { left: number; right: number; top: number; bottom: number }[] = [];
    for (const label of labels) {
      point
        .set(label.point[0], terrainMeshHeight(terrain, label.point) + 2, -label.point[1])
        .project(camera);
      if (point.z < -1 || point.z > 1 || Math.abs(point.x) > 1 || Math.abs(point.y) > 1) continue;
      const x = ((point.x + 1) * size.width) / 2,
        y = ((1 - point.y) * size.height) / 2,
        width = context.measureText(label.text).width + 8;
      const box = { left: x - width / 2, right: x + width / 2, top: y - 9, bottom: y + 8 };
      if (
        occupied.some(
          (other) =>
            box.left < other.right &&
            box.right > other.left &&
            box.top < other.bottom &&
            box.bottom > other.top
        )
      )
        continue;
      occupied.push(box);
      context.strokeStyle = 'rgba(250,251,246,.9)';
      context.fillStyle = '#334e49';
      context.strokeText(label.text, x, y);
      context.fillText(label.text, x, y);
    }
  }, -0.05);
  return null;
}
