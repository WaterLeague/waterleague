import { memo, useEffect, useMemo, useRef } from 'react';
import { Html } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import { Vector3 } from 'three';
import type { SharedInstallation } from '../entity/installation';
import { siteKey } from '../entity/installation';
import { representativeInstallations } from '../service/memberSitesService';
import { installationScore } from '../service/installationScore';
import type { Terrain } from '../../terrain/entity/terrain';
import { terrainHeight } from '../../terrain/service/terrainService';
import { positionSceneLabels } from '../../catalog/service/sceneLabelService';

export const InstallationNameplates = memo(function InstallationNameplates({
  installations,
  terrain,
  selectedKey,
  viewerId,
  distance,
  center,
  onSelect,
}: {
  installations: SharedInstallation[];
  terrain: Terrain | null;
  selectedKey: string;
  viewerId: string | null;
  distance: number;
  center: [number, number];
  onSelect: (key: string) => void;
}) {
  const labels = useRef(new Map<string, HTMLButtonElement>());
  const point = useMemo(() => new Vector3(), []);
  const values = useMemo(
    () =>
      distance >= 2400
        ? []
        : [...representativeInstallations(installations, viewerId).values()]
            .filter(
              (i) => Math.hypot(i.center[0] - center[0], i.center[1] - center[1]) < distance * 1.5
            )
            .sort(
              (a, b) =>
                Math.hypot(a.center[0] - center[0], a.center[1] - center[1]) -
                Math.hypot(b.center[0] - center[0], b.center[1] - center[1])
            )
            .slice(0, 96),
    [installations, viewerId, distance, center[0], center[1]]
  );
  const signature = useRef('');
  const dirty = useRef(true);
  useEffect(() => {
    dirty.current = true;
  }, [values, terrain]);
  useFrame(({ camera, size }) => {
    const next = `${camera.matrixWorld.elements}:${camera.projectionMatrix.elements}:${size.width}:${size.height}:${selectedKey}:${distance}`;
    if (!dirty.current && next === signature.current) return;
    dirty.current = false;
    signature.current = next;
    for (const element of labels.current.values()) element.hidden = true;
    if (distance >= 2400) return;
    const candidates = values.flatMap((i) => {
      point
        .set(i.center[0], terrainHeight(terrain, i.center) + i.heightM + 2, -i.center[1])
        .project(camera);
      if (Math.abs(point.x) > 0.96 || Math.abs(point.y) > 0.95 || Math.abs(point.z) > 1) return [];
      return [
        {
          id: i.id,
          x: ((point.x + 1) * size.width) / 2,
          y: ((1 - point.y) * size.height) / 2,
          width: 172,
          height: 46,
          priority: siteKey(i) === selectedKey ? 3 : i.ownerId === viewerId ? 2 : 0,
        },
      ];
    });
    for (const label of positionSceneLabels(candidates, {
      left: 12,
      top: 90,
      right: size.width - 12,
      bottom: size.height - 100,
    }).slice(0, 24)) {
      const element = labels.current.get(label.id);
      if (!element) continue;
      element.hidden = false;
      element.style.transform = `translate(${label.x}px,${label.y}px) translate(-50%,-50%)`;
      const anchor = candidates.find((c) => c.id === label.id)!;
      element.style.setProperty('--leader-x', `${anchor.x - label.x}px`);
      element.style.setProperty('--leader-y', `${anchor.y - label.y}px`);
    }
  });
  return (
    <Html fullscreen zIndexRange={[12, 0]} style={{ pointerEvents: 'none' }}>
      <div className="installation-nameplates">
        {values.map((i) => (
          <button
            key={i.id}
            hidden
            ref={(element) => {
              if (element) labels.current.set(i.id, element);
              else labels.current.delete(i.id);
            }}
            className="installation-nameplate"
            onClick={() => onSelect(siteKey(i))}
          >
            <span>{i.ownerId === viewerId ? `내 시설 · ${i.ownerName}` : i.ownerName}</span>
            <strong>{installationScore(i)}</strong>
            <i aria-hidden="true" />
          </button>
        ))}
      </div>
    </Html>
  );
});
