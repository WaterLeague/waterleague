/* EPA가 실제 적용한 내부 단계 포착·역류를 별도 메모리에 누적한다. */
#if defined(_WIN32)
#define WL_INLET_EXPORT __declspec(dllexport)
#else
#define WL_INLET_EXPORT __attribute__((visibility("default")))
#endif
#define WL_INLET_FIELDS 10
static double *wlInletTotals = NULL;
static int wlInletInvalid = 0;

WL_INLET_EXPORT int wl_inletVersion(void) { return 1; }

WL_INLET_EXPORT void wl_inletRelease(void)
{
    free(wlInletTotals);
    wlInletTotals = NULL;
    wlInletInvalid = 0;
}

WL_INLET_EXPORT int wl_inletBegin(void)
{
    wl_inletRelease();
    if (!UsesInlets || !FirstInlet || Nobjects[LINK] <= 0) return -1;
    wlInletTotals = calloc(Nobjects[LINK] * WL_INLET_FIELDS, sizeof(double));
    return wlInletTotals ? 0 : -2;
}

static void wl_inletObserve(double dt)
{
    TInlet *inlet;
    double *v, capture, back, approach;
    const double factor = 0.028316846592;
    if (!wlInletTotals) return;
    if (!isfinite(dt) || dt <= 0.0) { wlInletInvalid = 1; return; }
    for (inlet = FirstInlet; inlet; inlet = inlet->nextInlet)
    {
        v = wlInletTotals + inlet->linkIndex * WL_INLET_FIELDS;
        capture = inlet->flowCapture * factor;
        back = inlet->backflow * factor;
        approach = fabs(Link[inlet->linkIndex].newFlow) * factor;
        if (!isfinite(capture) || !isfinite(back) || !isfinite(approach)
            || capture < 0.0 || back < 0.0) { wlInletInvalid = 1; continue; }
        v[0] += capture * dt;
        v[1] += back * dt;
        v[2] += (capture - back) * dt;
        if (capture > 0.0) v[3] += dt;
        if (back > 0.0) v[4] += dt;
        v[5] = MAX(v[5], capture);
        v[6] = MAX(v[6], back);
        v[7] = MAX(v[7], approach);
        v[8] += dt;
        v[9] += 1.0;
    }
}

WL_INLET_EXPORT int wl_inletRead(int link, double *v, int n, int *nodes)
{
    TInlet *inlet;
    int i;
    if (!wlInletTotals || wlInletInvalid || !v || n != WL_INLET_FIELDS || !nodes
        || link < 0 || link >= Nobjects[LINK]) return -1;
    inlet = Link[link].inlet;
    if (!inlet) return -2;
    for (i = 0; i < n; i++) v[i] = wlInletTotals[link * n + i];
    nodes[0] = Link[link].node2;
    nodes[1] = inlet->nodeIndex;
    return 0;
}
