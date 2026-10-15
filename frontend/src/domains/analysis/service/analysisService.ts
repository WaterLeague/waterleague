export function comparisonFingerprint(sourceJobId: string, modelHashes: string[]) {
  return JSON.stringify([sourceJobId, [...modelHashes].sort()]);
}
export function patternFingerprint(jobIds: string[], topK: number) {
  return JSON.stringify([[...jobIds].sort(), topK]);
}
