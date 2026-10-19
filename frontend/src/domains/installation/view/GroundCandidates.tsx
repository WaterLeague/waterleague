import { buildingRaycast } from '../../city/service/buildingRaycastService';
import { GeometryBufferCache } from '../../../shared/repository/geometryBufferCache';
import { Sphere, Vector3 } from 'three';
import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { BufferGeometry, BufferAttribute, MeshBasicMaterial, Color, DoubleSide } from 'three';
import type { Terrain } from '../../terrain/entity/terrain';
import type { FacilityType } from '../../game/entity/game';
import {
  candidateKey,
  candidateMask,
  type GroundCandidate,
} from '../service/candidateTilesService';
import { availableSiteColor } from '../../city/service/siteVisibilityService';
import { streetAtFace } from '../../urban/service/streetGeometryService';
type CandidateBuffers = {
  positions: Float32Array;
  masks: Float32Array;
  bounds: Float32Array;
  ends: number[];
  sphere: number[];
};
const cache = new GeometryBufferCache<CandidateBuffers>();
const terrainIds = new WeakMap<object, number>();
let terrainId = 0;
export const GroundCandidates = memo(function GroundCandidates({
  rows,
  terrain,
  type,
  ownDistrictId,
  occupiedSites,
  onSelect,
}: {
  rows: GroundCandidate[];
  occupiedSites?: ReadonlySet<string>;
  terrain: Terrain | null;
  type: FacilityType | '';
  ownDistrictId: string | null;
  onSelect: (key: string) => void;
}) {
  const [shape, setShape] = useState<{
    geometry: BufferGeometry;
    rows: GroundCandidate[];
    ends: number[];
  } | null>(null);
  const [failed, setFailed] = useState(false);
  const uniform = useRef({ activeMask: { value: 0 } });
  const material = useMemo(() => {
    const m = new MeshBasicMaterial({
      color: availableSiteColor,
      transparent: true,
      opacity: 0.7,
      depthWrite: false,
      side: DoubleSide,
      toneMapped: false,
    });
    m.onBeforeCompile = (s) => {
      s.uniforms.activeMask = uniform.current.activeMask;
      s.uniforms.excludedColor = { value: new Color('#9caaa1') };
      s.vertexShader =
        'attribute float candidateMask; attribute float candidateOther; attribute float candidateOccupied; varying float vCandidateMask; varying float vCandidateOther; varying float vCandidateOccupied;\n' +
        s.vertexShader;
      s.vertexShader = s.vertexShader.replace(
        '#include <begin_vertex>',
        '#include <begin_vertex>\n vCandidateMask=candidateMask;vCandidateOther=candidateOther;vCandidateOccupied=candidateOccupied;'
      );
      s.fragmentShader =
        'uniform float activeMask; uniform vec3 excludedColor; varying float vCandidateMask; varying float vCandidateOther; varying float vCandidateOccupied;\n' +
        s.fragmentShader;
      s.fragmentShader = s.fragmentShader.replace(
        '#include <color_fragment>',
        '#include <color_fragment>\n float matchType=activeMask<.5?1.:step(.5,mod(floor(vCandidateMask/max(1.,activeMask)),2.));matchType*=1.-vCandidateOccupied;diffuseColor.rgb=mix(excludedColor,diffuseColor.rgb,matchType);diffuseColor.a*=mix(.2,1.,matchType)*mix(1.,.16,vCandidateOther);'
      );
    };
    m.customProgramCacheKey = () => 'candidate-mask-v1';
    return m;
  }, []);
  uniform.current.activeMask.value = candidateMask(type);
  useEffect(() => () => material.dispose(), [material]);
  useEffect(() => {
    if (!rows.length) {
      setShape(null);
      return;
    }
    setFailed(false);
    if (terrain && !terrainIds.has(terrain)) terrainIds.set(terrain, ++terrainId);
    const variant = String(terrain ? terrainIds.get(terrain) : 0);
    const apply = (data: CandidateBuffers) => {
      const geometry = new BufferGeometry();
      geometry.setAttribute('position', new BufferAttribute(data.positions, 3));
      geometry.setAttribute('candidateMask', new BufferAttribute(data.masks, 1));
      geometry.setAttribute(
        'candidateOther',
        new BufferAttribute(new Float32Array(data.masks.length), 1)
      );
      geometry.setAttribute(
        'candidateOccupied',
        new BufferAttribute(new Float32Array(data.masks.length), 1)
      );
      geometry.boundingSphere = new Sphere(new Vector3(...data.sphere.slice(0, 3)), data.sphere[3]);
      geometry.userData.raycast = buildingRaycast(data);
      setShape({ geometry, rows, ends: data.ends });
    };
    const cached = cache.get(rows, variant);
    if (cached) {
      apply(cached);
      return;
    }
    const worker = new Worker(new URL('../service/candidateGeometry.worker.ts', import.meta.url), {
      type: 'module',
    });
    worker.onmessage = ({ data }) => {
      if (data.failed) {
        setFailed(true);
        worker.terminate();
        return;
      }
      cache.put(rows, variant, data);
      apply(data);
      worker.terminate();
    };
    const fail = () => {
      setFailed(true);
      worker.terminate();
    };
    worker.onerror = fail;
    worker.onmessageerror = fail;
    worker.postMessage({ rows, terrain });
    return () => worker.terminate();
  }, [rows, terrain]);
  useEffect(() => () => shape?.geometry.dispose(), [shape]);
  useEffect(() => {
    if (!shape) return;
    const a = shape.geometry.getAttribute('candidateOther') as BufferAttribute;
    const occupied = shape.geometry.getAttribute('candidateOccupied') as BufferAttribute;
    shape.rows.forEach((r, i) => {
      const start = (shape.ends[i - 1] ?? 0) * 3,
        end = shape.ends[i] * 3;
      for (let j = start; j < end; j++) {
        a.setX(j, ownDistrictId && r[1] !== ownDistrictId ? 1 : 0);
        occupied.setX(j, occupiedSites?.has(candidateKey(r)) ? 1 : 0);
      }
    });
    a.needsUpdate = true;
    occupied.needsUpdate = true;
  }, [shape, ownDistrictId, occupiedSites]);
  if (failed) throw new Error('설치 후보 표시 실패');
  return shape ? (
    <mesh
      geometry={shape.geometry}
      raycast={
        shape.rows[0]?.[0].startsWith('overview-') ? () => {} : shape.geometry.userData.raycast
      }
      material={material}
      renderOrder={4}
      onClick={(e) => {
        if (e.delta > 5) return;
        const i = streetAtFace(shape.ends, e.faceIndex ?? -1);
        if (i >= 0) {
          e.stopPropagation();
          onSelect(candidateKey(shape.rows[i]));
        }
      }}
    />
  ) : null;
});
