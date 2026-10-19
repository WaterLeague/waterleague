/* EPA 누적 체적과 현재 저장량을 읽으며 계산 상태를 변경하지 않는다. */
#if defined(_WIN32)
#define WL_NETWORK_EXPORT __declspec(dllexport)
#else
#define WL_NETWORK_EXPORT __attribute__((visibility("default")))
#endif

extern TRoutingTotals FlowTotals;
extern TNodeStats *NodeStats;
extern double *NodeInflow;
extern double *NodeOutflow;

/* 별도 관측 메모리에만 반시간 적분을 누적한다. EPA 물리 상태에는 쓰지 않는다. */
static double *wlPreviousRates = NULL;
static double *wlIntegratedVolumes = NULL;

WL_NETWORK_EXPORT void wl_networkRelease(void)
{
    free(wlPreviousRates);
    free(wlIntegratedVolumes);
    wlPreviousRates = NULL;
    wlIntegratedVolumes = NULL;
}

WL_NETWORK_EXPORT int wl_networkBegin(void)
{
    if (!IsStartedFlag || Nobjects[NODE] <= 0) return -1;
    wl_networkRelease();
    wlPreviousRates = calloc(3 * Nobjects[NODE], sizeof(double));
    wlIntegratedVolumes = calloc(3 * Nobjects[NODE], sizeof(double));
    if (!wlPreviousRates || !wlIntegratedVolumes) return -2;
    return 0;
}

static int wl_observedStep(double *elapsedTime)
{
    double before = NewRoutingTime;
    double q[3], dt;
    int j, k, error = swmm_step(elapsedTime);
    if (error) return error;
    dt = (NewRoutingTime - before) / 1000.0;
    for (j = 0; j < Nobjects[NODE]; j++)
    {
        q[0] = q[1] = q[2] = 0.0;
        if (Node[j].type == OUTFALL)
        {
            if (Node[j].outflow > 0.0) q[2] = Node[j].outflow;
            else q[1] = Node[j].inflow;
        }
        else if (Node[j].newVolume <= Node[j].fullVolume)
            q[0] = Node[j].overflow;
        for (k = 0; k < 3; k++)
        {
            wlIntegratedVolumes[3*j+k] += (wlPreviousRates[3*j+k] + q[k]) * dt / 2.0;
            wlPreviousRates[3*j+k] = q[k];
        }
    }
    return 0;
}

WL_NETWORK_EXPORT int wl_networkAdvance(int seconds, double *elapsedTime)
{
    double realRouteStep = RouteStep;
    int error;
    if (!IsStartedFlag || !wlPreviousRates || !wlIntegratedVolumes || seconds < 0) return -1;
    if (seconds == 0) return wl_observedStep(elapsedTime);
    /* 공식 swmm_stride의 경계 처리와 동일하며 각 내부 단계 뒤에 읽기만 수행한다. */
    RoutingDuration = MIN(TotalDuration, NewRoutingTime + 1000.0 * seconds);
    if (seconds < RouteStep) RouteStep = seconds;
    do { error = wl_observedStep(elapsedTime); } while (*elapsedTime > 0.0 && !error);
    RouteStep = realRouteStep;
    RoutingDuration = TotalDuration;
    ElapsedTime = NewRoutingTime < TotalDuration ? NewRoutingTime / MSECperDAY : 0.0;
    *elapsedTime = ElapsedTime;
    return error;
}

WL_NETWORK_EXPORT int wl_networkVersion(void) { return 1; }

WL_NETWORK_EXPORT int wl_networkSettings(double *v, int n)
{
    if (!IsOpenFlag || !v || n != 4) return -1;
    v[0] = RouteModel == DW;
    v[1] = TotalDuration / 1000.0;
    v[2] = ReportStart == StartDateTime;
    v[3] = AllowPonding;
    return 0;
}

WL_NETWORK_EXPORT int wl_networkSnapshot(double *v, int n)
{
    const double ft3ToM3 = 0.028316846592;
    double storage = 0.0;
    int j;
    if (!IsOpenFlag || !IsStartedFlag || !v || n != 13) return -1;
    for (j = 0; j < Nobjects[NODE]; j++) storage += Node[j].newVolume;
    for (j = 0; j < Nobjects[LINK]; j++) storage += Link[j].newVolume;
    v[0] = NewRoutingTime / 1000.0;
    v[1] = FlowTotals.initStorage * ft3ToM3;
    v[2] = storage * ft3ToM3;
    v[3] = FlowTotals.dwInflow * ft3ToM3;
    v[4] = FlowTotals.wwInflow * ft3ToM3;
    v[5] = FlowTotals.gwInflow * ft3ToM3;
    v[6] = FlowTotals.iiInflow * ft3ToM3;
    v[7] = FlowTotals.exInflow * ft3ToM3;
    v[8] = FlowTotals.outflow * ft3ToM3;
    v[9] = FlowTotals.flooding * ft3ToM3;
    v[10] = FlowTotals.evapLoss * ft3ToM3;
    v[11] = FlowTotals.seepLoss * ft3ToM3;
    v[12] = FlowTotals.reacted * ft3ToM3;
    return 0;
}

WL_NETWORK_EXPORT int wl_nodeVolumes(int j, double *v, int n)
{
    const double ft3ToM3 = 0.028316846592;
    if (!IsOpenFlag || !IsStartedFlag || !v || n != 6 || !NodeStats || !wlIntegratedVolumes ||
        j < 0 || j >= Nobjects[NODE]) return -1;
    v[0] = NodeStats[j].volFlooded * ft3ToM3;
    v[1] = NodeInflow[j] * ft3ToM3;
    v[2] = NodeOutflow[j] * ft3ToM3;
    v[3] = wlIntegratedVolumes[3*j] * ft3ToM3;
    v[4] = wlIntegratedVolumes[3*j+1] * ft3ToM3;
    v[5] = wlIntegratedVolumes[3*j+2] * ft3ToM3;
    return 0;
}
