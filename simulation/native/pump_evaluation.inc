/* 선행 상태를 이어받고 평가 구간의 운전 통계만 별도 메모리에 적분한다. */
static WLPumpObservation *wlEvaluationPumps = NULL;
static double wlPumpEvaluationStart, wlPumpEvaluationEnd;
static int wlPumpEvaluationInvalid = 0;

WL_NETWORK_EXPORT int wl_pumpEvaluationVersion(void) { return 1; }
WL_NETWORK_EXPORT void wl_pumpEvaluationRelease(void)
{
    free(wlEvaluationPumps); wlEvaluationPumps = NULL;
    wlPumpEvaluationInvalid = 0;
}

WL_NETWORK_EXPORT int wl_pumpEvaluationBegin(double start, double end)
{
    if (!IsStartedFlag || NewRoutingTime != 0 || !wlPumps || wlEvaluationPumps
        || !isfinite(start) || !isfinite(end) || start < 0 || end <= start) return -1;
    wlEvaluationPumps = calloc(Nobjects[LINK], sizeof(WLPumpObservation));
    if (!wlEvaluationPumps) return -2;
    memcpy(wlEvaluationPumps, wlPumps, Nobjects[LINK]*sizeof(WLPumpObservation));
    wlPumpEvaluationStart = start; wlPumpEvaluationEnd = end;
    return 0;
}

static void wl_coupledPumpsObserve(double before)
{
    int j;
    double after = NewRoutingTime/1000.0;
    WLPumpObservation *whole;
    wl_pumpsObserve(before);
    if (!wlEvaluationPumps || after <= before) return;
    if (after <= wlPumpEvaluationStart) {
        for (j = 0; j < Nobjects[LINK]; j++) {
            wlEvaluationPumps[j].previousFlow = wlPumps[j].previousFlow;
            wlEvaluationPumps[j].previousOn = wlPumps[j].previousOn;
        }
        return;
    }
    if (before >= wlPumpEvaluationEnd) return;
    /* 결합 시계가 평가 경계를 분할해야 하며 겹친 내부 단계를 비례 배분하지 않는다. */
    if (before < wlPumpEvaluationStart || after > wlPumpEvaluationEnd) {
        wlPumpEvaluationInvalid = 1; return;
    }
    whole = wlPumps; wlPumps = wlEvaluationPumps;
    wl_pumpsObserve(before);
    wlPumps = whole;
}

WL_NETWORK_EXPORT int wl_pumpEvaluationRead(int j, double *v, int n)
{
    int status;
    WLPumpObservation *whole;
    if (!wlEvaluationPumps || wlPumpEvaluationInvalid) return -1;
    whole = wlPumps; wlPumps = wlEvaluationPumps;
    status = wl_pumpsRead(j, v, n);
    wlPumps = whole;
    return status;
}
