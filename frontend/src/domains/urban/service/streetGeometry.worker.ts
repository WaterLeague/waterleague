import { streetGeometry } from './streetGeometryService';
self.onmessage = (event) => {
  try {
    const data = streetGeometry(
      event.data.roads,
      event.data.terrain,
      event.data.detail,
      event.data.parkingAisles
    );
    self.postMessage(data, { transfer: [data.positions.buffer, data.colors.buffer] });
  } catch {
    self.postMessage({ failed: true });
  }
};
