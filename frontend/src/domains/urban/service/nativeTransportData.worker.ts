import { readNativeTransport } from '../repository/nativeTransportDataSource';
self.onmessage = async () => {
  try {
    self.postMessage({ data: await readNativeTransport(new AbortController().signal) });
  } catch {
    self.postMessage({ failed: true });
  }
};
