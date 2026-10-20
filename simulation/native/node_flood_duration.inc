/* 지표 저류·빗물받이 반환을 제외한 외부 월류 발생 단계의 길이만 누적한다. */
static double *wlFloodSeconds = NULL;
static double wlFloodObservedSeconds = 0.0;
static double wlFloodSteps = 0.0;
static double wlFloodWindowStart = 0.0, wlFloodWindowEnd = 0.0;
static double wlFloodWindowSeconds = 0.0, wlFloodWindowCovered = 0.0, wlFloodWindowSteps = 0.0;

static void wl_floodDurationRelease(void)
{
    free(wlFloodSeconds);
    wlFloodSeconds = NULL;
    wlFloodObservedSeconds = wlFloodSteps = 0.0;
    wlFloodWindowStart = wlFloodWindowEnd = 0.0;
    wlFloodWindowSeconds = wlFloodWindowCovered = wlFloodWindowSteps = 0.0;
}

static int wl_floodDurationBegin(void)
{
    if (!IsStartedFlag || NewRoutingTime != 0.0 || Nobjects[NODE] <= 0) return -1;
    wl_floodDurationRelease();
    wlFloodSeconds = calloc(Nobjects[NODE], sizeof(double));
    wlFloodWindowEnd = TotalDuration / 1000.0;
    return wlFloodSeconds ? 0 : -2;
}

static void wl_floodDurationObserve(double before)
{
    double now = NewRoutingTime / 1000.0, dt = now - before;
    double left = MAX(before, wlFloodWindowStart), right = MIN(now, wlFloodWindowEnd);
    int j, active = 0;
    if (!wlFloodSeconds || dt <= 0.0) return;
    for (j = 0; j < Nobjects[NODE]; j++)
        if (Node[j].type != OUTFALL && Node[j].inlet != CAPTURE &&
            Node[j].newVolume <= Node[j].fullVolume && Node[j].overflow > 0.0)
        {
            wlFloodSeconds[j] += dt;
            active = 1;
        }
    wlFloodObservedSeconds += dt;
    wlFloodSteps += 1.0;
    /* 동시 월류 지점 수와 무관하게 평가 구간과 겹친 시간을 한 번만 반영한다. */
    if (right > left)
    {
        if (active) wlFloodWindowSeconds += right - left;
        wlFloodWindowCovered += right - left;
        wlFloodWindowSteps += 1.0;
    }
}

WL_NETWORK_EXPORT int wl_floodDurationVersion(void) { return 2; }

WL_NETWORK_EXPORT int wl_floodDurationWindow(double start, double end)
{
    if (!IsStartedFlag || !wlFloodSeconds || NewRoutingTime != 0.0 ||
        !isfinite(start) || !isfinite(end) || start < 0.0 || end <= start ||
        end > TotalDuration / 1000.0) return -1;
    wlFloodWindowStart = start;
    wlFloodWindowEnd = end;
    wlFloodWindowSeconds = wlFloodWindowCovered = wlFloodWindowSteps = 0.0;
    return 0;
}

WL_NETWORK_EXPORT int wl_floodDurationWindowRead(double *v, int n)
{
    if (!IsStartedFlag || !wlFloodSeconds || !v || n != 5) return -1;
    v[0] = wlFloodWindowSeconds;
    v[1] = wlFloodWindowCovered;
    v[2] = wlFloodWindowSteps;
    v[3] = wlFloodWindowStart;
    v[4] = wlFloodWindowEnd;
    return 0;
}

WL_NETWORK_EXPORT int wl_floodDurationRead(int j, double *v, int n)
{
    if (!IsStartedFlag || !wlFloodSeconds || !v || n != 3 ||
        j < 0 || j >= Nobjects[NODE]) return -1;
    v[0] = wlFloodSeconds[j];
    v[1] = wlFloodObservedSeconds;
    v[2] = wlFloodSteps;
    return 0;
}
