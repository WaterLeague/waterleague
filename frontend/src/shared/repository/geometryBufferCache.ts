// CPU 버퍼만 제한 보관하고 GPU 객체의 생성·해제는 화면 생명주기에 맡긴다.
export class GeometryBufferCache<T extends { positions: Float32Array }> {
  private entries = new Map<object, { variant: string; value: T; bytes: number }>();
  private bytes = 0;
  constructor(private maximum = 48 * 1024 * 1024) {}
  get(key: object, variant: string) {
    const entry = this.entries.get(key);
    if (!entry || entry.variant !== variant) return undefined;
    this.entries.delete(key);
    this.entries.set(key, entry);
    return entry.value;
  }
  put(key: object, variant: string, value: T) {
    const bytes = Object.values(value as Record<string, unknown>).reduce<number>(
      (n, v) => n + (ArrayBuffer.isView(v) ? v.byteLength : Array.isArray(v) ? v.length * 8 : 0),
      0
    );
    const previous = this.entries.get(key);
    if (previous) {
      this.bytes -= previous.bytes;
      this.entries.delete(key);
    }
    if (bytes > this.maximum) return;
    this.entries.set(key, { variant, value, bytes });
    this.bytes += bytes;
    while (this.bytes > this.maximum) {
      const oldest = this.entries.keys().next().value!;
      this.bytes -= this.entries.get(oldest)!.bytes;
      this.entries.delete(oldest);
    }
  }
}
