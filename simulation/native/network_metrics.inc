/* 평가 관측만 별도 메모리에 보존하며 EPA 계산 상태를 변경하지 않는다. */
static int *wlMetricNodes = NULL;
static double *wlMetricValues = NULL;
static int wlMetricCount = 0;
static double wlMetricStart, wlMetricEnd, wlMetricDuration;
static long wlMetricSteps;

WL_NETWORK_EXPORT int wl_metricsVersion(void) { return 1; }

WL_NETWORK_EXPORT void wl_metricsRelease(void)
{
    free(wlMetricNodes);
    free(wlMetricValues);
    wlMetricNodes = NULL;
    wlMetricValues = NULL;
    wlMetricCount = 0;
}

WL_NETWORK_EXPORT int wl_metricsBegin(double start, double end, int *nodes, int count)
{
    int i, j;
    if (!IsStartedFlag || NewRoutingTime != 0.0 || !isfinite(start) || !isfinite(end)
        || start < 0.0 || end <= start || end > TotalDuration / 1000.0
        || !nodes || count < 1 || count > Nobjects[NODE]) return -1;
    for (i = 0; i < count; i++)
    {
        if (nodes[i] < 0 || nodes[i] >= Nobjects[NODE] || Node[nodes[i]].type != OUTFALL
            || Outfall[Node[nodes[i]].subIndex].routeTo >= 0)
            return -2;
        for (j = 0; j < i; j++) if (nodes[i] == nodes[j]) return -3;
    }
    wl_metricsRelease();
    wlMetricNodes = calloc(count, sizeof(int));
    /* 방향별 이전 유량·체적·첨두·첨두 시각, 마지막 행은 동시 합계. */
    wlMetricValues = calloc((count + 1) * 8, sizeof(double));
    if (!wlMetricNodes || !wlMetricValues) { wl_metricsRelease(); return -4; }
    wlMetricCount = count;
    wlMetricStart = start;
    wlMetricEnd = end;
    wlMetricDuration = 0.0;
    wlMetricSteps = 0;
    for (i = 0; i < count; i++) wlMetricNodes[i] = nodes[i];
    for (i = 0; i <= count; i++)
        wlMetricValues[8*i+6] = wlMetricValues[8*i+7] = start;
    return 0;
}

static void wl_metricsObserve(double before)
{
    const double ft3ToM3 = 0.028316846592;
    double now = NewRoutingTime / 1000.0, dt, left, right, a, b, q, sum[2] = {0, 0};
    double *v;
    int i, k;
    if (!wlMetricCount) return;
    dt = now - before;
    if (dt <= 0.0) return;
    left = MAX(before, wlMetricStart);
    right = MIN(now, wlMetricEnd);
    for (i = 0; i <= wlMetricCount; i++)
    {
        v = wlMetricValues + 8*i;
        for (k = 0; k < 2; k++)
        {
            q = i == wlMetricCount ? sum[k] :
                wlPreviousRates[3*wlMetricNodes[i]+1+k] * ft3ToM3;
            if (i < wlMetricCount) sum[k] += q;
            if (right > left)
            {
                a = v[k] + (q - v[k]) * (left - before) / dt;
                b = v[k] + (q - v[k]) * (right - before) / dt;
                v[2+k] += (a + b) * (right - left) / 2.0;
                if (a > v[4+k]) { v[4+k] = a; v[6+k] = left; }
                if (b > v[4+k]) { v[4+k] = b; v[6+k] = right; }
            }
            v[k] = q;
        }
    }
    if (right > left) { wlMetricDuration += right - left; wlMetricSteps++; }
}

WL_NETWORK_EXPORT int wl_metricsRead(int i, double *v, int n)
{
    int k;
    if (!IsStartedFlag || !wlMetricCount || i < 0 || i > wlMetricCount || !v || n != 8)
        return -1;
    for (k = 0; k < 6; k++) v[k] = wlMetricValues[8*i+2+k];
    v[6] = wlMetricDuration;
    v[7] = (double)wlMetricSteps;
    return 0;
}
