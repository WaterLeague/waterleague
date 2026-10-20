/* 지표 저류·빗물받이 반환을 제외한 외부 월류 발생 단계의 길이만 누적한다. */
static double *wlFloodSeconds = NULL;
static double wlFloodObservedSeconds = 0.0;
static double wlFloodSteps = 0.0;

static void wl_floodDurationRelease(void)
{
    free(wlFloodSeconds);
    wlFloodSeconds = NULL;
    wlFloodObservedSeconds = wlFloodSteps = 0.0;
}

static int wl_floodDurationBegin(void)
{
    if (!IsStartedFlag || NewRoutingTime != 0.0 || Nobjects[NODE] <= 0) return -1;
    wl_floodDurationRelease();
    wlFloodSeconds = calloc(Nobjects[NODE], sizeof(double));
    return wlFloodSeconds ? 0 : -2;
}

static void wl_floodDurationObserve(double before)
{
    double dt = NewRoutingTime / 1000.0 - before;
    int j;
    if (!wlFloodSeconds || dt <= 0.0) return;
    for (j = 0; j < Nobjects[NODE]; j++)
        if (Node[j].type != OUTFALL && Node[j].inlet != CAPTURE &&
            Node[j].newVolume <= Node[j].fullVolume && Node[j].overflow > 0.0)
            wlFloodSeconds[j] += dt;
    wlFloodObservedSeconds += dt;
    wlFloodSteps += 1.0;
}

WL_NETWORK_EXPORT int wl_floodDurationVersion(void) { return 1; }

WL_NETWORK_EXPORT int wl_floodDurationRead(int j, double *v, int n)
{
    if (!IsStartedFlag || !wlFloodSeconds || !v || n != 3 ||
        j < 0 || j >= Nobjects[NODE]) return -1;
    v[0] = wlFloodSeconds[j];
    v[1] = wlFloodObservedSeconds;
    v[2] = wlFloodSteps;
    return 0;
}
