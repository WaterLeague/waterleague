/* 시설별 층 상태와 원 체적만 읽으며 계산·수지·시간 간격을 변경하지 않는다. */
#if defined(_WIN32)
#define WL_LID_EXPORT __declspec(dllexport)
#else
#define WL_LID_EXPORT __attribute__((visibility("default")))
#endif

WL_LID_EXPORT int wl_connectedLidVersion(void) { return 1; }

WL_LID_EXPORT int wl_connectedLidCount(int j)
{
    int count = 0;
    TLidList *entry;
    if (j < 0 || j >= Nobjects[SUBCATCH]) return -1;
    if (!LidGroups || !LidGroups[j]) return 0;
    for (entry = LidGroups[j]->lidList; entry; entry = entry->nextLidUnit) count++;
    return count;
}

WL_LID_EXPORT int wl_connectedLidRead(int j, int ordinal, double *v, int n,
                                    char *name, int length)
{
    TLidList *entry;
    TLidUnit *unit;
    TLidProc *proc;
    double factor;
    int i;
    if (j < 0 || j >= Nobjects[SUBCATCH] || ordinal < 0 || !v || n != 15 ||
        !name || length < 2 || !LidGroups || !LidGroups[j]) return -1;
    entry = LidGroups[j]->lidList;
    for (i = 0; entry && i < ordinal; i++) entry = entry->nextLidUnit;
    if (!entry) return -2;
    unit = entry->lidUnit;
    proc = &LidProcs[unit->lidIndex];
    if ((int)strlen(proc->ID) >= length) return -3;
    strcpy(name, proc->ID);
    factor = unit->area * unit->number * 0.028316846592;
    v[0] = NewRunoffTime / 1000.0;
    v[1] = unit->area * unit->number * 0.3048 * 0.3048;
    v[2] = unit->surfaceDepth * 304.8;
    v[3] = proc->soil.thickness > 0.0 ? unit->soilMoisture : -1.0;
    v[4] = proc->storage.thickness > 0.0 ? unit->storageDepth * 304.8 : -1.0;
    v[5] = unit->waterBalance.inflow * factor;
    v[6] = unit->waterBalance.evap * factor;
    v[7] = unit->waterBalance.infil * factor;
    v[8] = unit->waterBalance.surfFlow * factor;
    v[9] = unit->waterBalance.drainFlow * factor;
    v[10] = unit->waterBalance.initVol * factor;
    v[11] = unit->waterBalance.finalVol * factor;
    v[12] = unit->number;
    v[13] = unit->drainNode;
    v[14] = unit->drainSubcatch;
    return 0;
}
