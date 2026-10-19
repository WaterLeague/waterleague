/* EPA 누적 집수 강우를 읽으며 시간·수문 상태를 변경하지 않는다. */
extern TRunoffTotals RunoffTotals;

WL_NETWORK_EXPORT int wl_rainfallVersion(void) { return 1; }

WL_NETWORK_EXPORT int wl_rainfallSnapshot(double *v, int n)
{
    const double ft3ToM3 = 0.028316846592;
    const double ft2ToM2 = 0.09290304;
    double area = 0.0;
    int j;
    if (!IsOpenFlag || !IsStartedFlag || !v || n != 5) return -1;
    for (j = 0; j < Nobjects[SUBCATCH]; j++) area += Subcatch[j].area;
    v[0] = NewRunoffTime / 1000.0;
    v[1] = RunoffTotals.rainfall * ft3ToM3;
    v[2] = area * ft2ToM2;
    v[3] = area * UCF(LANDAREA) * 10000.0;
    v[4] = UCF(LANDAREA);
    return 0;
}
