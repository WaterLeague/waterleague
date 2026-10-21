export function competitionScope(path: string, competitionId?: string | null) {
  return competitionId
    ? `${path}${path.includes('?') ? '&' : '?'}competitionId=${encodeURIComponent(competitionId)}`
    : path;
}
