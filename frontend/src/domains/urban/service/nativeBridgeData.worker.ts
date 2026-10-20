import { readNativeBridges } from '../repository/nativeBridgeDataSource';
self.onmessage = async () => {
  try {
    const groups = await readNativeBridges(new AbortController().signal);
    self.postMessage({ groups });
  } catch {
    self.postMessage({ failed: true });
  }
};
