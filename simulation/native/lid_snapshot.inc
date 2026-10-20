/* EPA 내부 상태를 읽기만 하며 물리 계산·누적 수지를 변경하지 않는다. */
#if defined(_WIN32)
#define WL_EXPORT __declspec(dllexport)
#else
#define WL_EXPORT __attribute__((visibility("default")))
#endif

extern TRunoffTotals RunoffTotals;

WL_EXPORT int wl_snapshotVersion(void) { return 1; }

WL_EXPORT int wl_hydrologySnapshot(double *v, int n)
{
    const double ft3ToM3 = 0.028316846592;
    const double ftToMm = 304.8;
    TLidUnit *unit;
    TLidProc *proc;
    int i, j, count = 0;
    TLidUnit *found = NULL;
    if (!v || n != 20 || Nobjects[SUBCATCH] < 1 || Nobjects[SUBCATCH] > 3 || !Subcatch)
        return -1;
    for (i = 0; i < n; i++) v[i] = -1.0;
    v[0] = NewRunoffTime / 1000.0;
    v[1] = RunoffTotals.rainfall * ft3ToM3;
    v[2] = RunoffTotals.evap * ft3ToM3;
    v[3] = RunoffTotals.infil * ft3ToM3;
    v[4] = RunoffTotals.runoff * ft3ToM3;
    v[5] = RunoffTotals.drains * ft3ToM3;
    v[6] = RunoffTotals.initStorage * ft3ToM3;
    v[7] = 0.0;
    v[8] = 0.0;
    for (j = 0; j < Nobjects[SUBCATCH]; j++) {
        v[7] += subcatch_getStorage(j) * ft3ToM3;
        /* 지붕에서 용기로 옮긴 내부 유량을 출구 유량에 중복 합산하지 않는다. */
        if (Subcatch[j].outSubcatch < 0) v[8] += Subcatch[j].newRunoff * ft3ToM3;
        if (!LidGroups || !LidGroups[j]) continue;
        if (!LidGroups[j]->lidList || LidGroups[j]->lidList->nextLidUnit) return -2;
        found = LidGroups[j]->lidList->lidUnit;
        count++;
    }
    if (count == 0) return 0;
    if (count != 1) return -2;
    unit = found;
    proc = &LidProcs[unit->lidIndex];
    v[9] = unit->surfaceDepth * ftToMm;
    if (proc->pavement.thickness > 0.0) v[10] = unit->paveDepth * ftToMm;
    if (proc->soil.thickness > 0.0) v[11] = unit->soilMoisture;
    if (proc->storage.thickness > 0.0) v[12] = unit->storageDepth * ftToMm;
    v[13] = unit->waterBalance.inflow * unit->area * unit->number * ft3ToM3;
    v[14] = unit->waterBalance.evap * unit->area * unit->number * ft3ToM3;
    v[15] = unit->waterBalance.infil * unit->area * unit->number * ft3ToM3;
    v[16] = unit->waterBalance.surfFlow * unit->area * unit->number * ft3ToM3;
    v[17] = unit->waterBalance.drainFlow * unit->area * unit->number * ft3ToM3;
    v[18] = unit->waterBalance.initVol * unit->area * unit->number * ft3ToM3;
    v[19] = unit->waterBalance.finalVol * unit->area * unit->number * ft3ToM3;
    return 1;
}
