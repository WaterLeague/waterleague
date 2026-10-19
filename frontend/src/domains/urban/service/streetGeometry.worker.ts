import { BufferGeometry, BufferAttribute } from 'three';
import { partBounds } from '../../../shared/repository/meshBounds';
import { streetGeometry } from './streetGeometryService';
self.onmessage = (event) => {
  try {
    const data = streetGeometry(
      event.data.roads,
      event.data.terrain,
      event.data.detail,
      event.data.parkingAisles
    );
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(data.positions, 3));
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();
    const normals = geometry.getAttribute('normal').array as Float32Array,
      bounds = partBounds(data.positions, data.ends);
    const sphere = [...geometry.boundingSphere!.center.toArray(), geometry.boundingSphere!.radius];
    self.postMessage(
      { ...data, normals, bounds, sphere },
      { transfer: [data.positions.buffer, data.colors.buffer, normals.buffer, bounds.buffer] }
    );
  } catch {
    self.postMessage({ failed: true });
  }
};
