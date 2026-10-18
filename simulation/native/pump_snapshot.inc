/* 펌프 관측은 별도 메모리에 기록하며 EPA 수리 계산을 변경하지 않는다. */
typedef struct {
    int active, powerCurve, npshCurve, previousOn;
    double previousFlow, volume, running, flowing, starts, peakFlow;
    double minHead, maxHead, invalidHead, invalidFlow, shaftKwh, maxNpsh;
    double observed, steps, minFlow, maxFlow;
} WLPumpObservation;
static WLPumpObservation *wlPumps = NULL;

WL_NETWORK_EXPORT int wl_pumpsVersion(void) { return 1; }
WL_NETWORK_EXPORT void wl_pumpsRelease(void) { free(wlPumps); wlPumps = NULL; }

WL_NETWORK_EXPORT int wl_pumpsBegin(int j, int powerCurve, int npshCurve)
{
    WLPumpObservation *p;
    TTableEntry *entry;
    if (!IsStartedFlag || NewRoutingTime != 0 || j < 0 || j >= Nobjects[LINK]
        || Link[j].type != PUMP || Pump[Link[j].subIndex].type != TYPE3_PUMP
        || powerCurve < 0 || powerCurve >= Nobjects[CURVE]
        || npshCurve < 0 || npshCurve >= Nobjects[CURVE]) return -1;
    if (!wlPumps) wlPumps = calloc(Nobjects[LINK], sizeof(WLPumpObservation));
    if (!wlPumps) return -2;
    p = wlPumps + j;
    if (p->active) return -3;
    p->active = 1;
    p->powerCurve = powerCurve;
    p->npshCurve = npshCurve;
    p->minHead = 1e100;
    p->maxHead = -1e100;
    entry = Curve[powerCurve].firstEntry;
    p->minFlow = entry->x;
    while (entry->next) entry = entry->next;
    p->maxFlow = entry->x;
    return 0;
}

static void wl_pumpsObserve(double before)
{
    const double ft3ToM3 = 0.028316846592;
    int j, n1, n2, k, on;
    double dt = NewRoutingTime/1000.0-before, q, head, userQ;
    WLPumpObservation *p;
    if (!wlPumps || dt <= 0) return;
    for (j = 0; j < Nobjects[LINK]; j++) {
        p = wlPumps+j;
        if (!p->active) continue;
        k = Link[j].subIndex; n1 = Link[j].node1; n2 = Link[j].node2;
        q = Link[j].newFlow*ft3ToM3;
        userQ = Link[j].newFlow*UCF(FLOW);
        head = (Node[n2].newDepth+Node[n2].invertElev
               -Node[n1].newDepth-Node[n1].invertElev)*UCF(LENGTH);
        on = Link[j].setting > 0;
        p->volume += (p->previousFlow+q)*dt/2;
        p->previousFlow = q;
        p->observed += dt; p->steps++;
        if (on) {
            p->running += dt;
            if (!p->previousOn) p->starts++;
            p->minHead = MIN(p->minHead, head); p->maxHead = MAX(p->maxHead, head);
            /* PUMP3의 범위 밖 조회는 끝점 유량을 유지하므로 별도 실패 판정이 필요하다. */
            if (head < Pump[k].xMin || head > Pump[k].xMax) p->invalidHead += dt;
        }
        if (q > 1e-9) {
            p->flowing += dt;
            p->peakFlow = MAX(p->peakFlow, q);
            if (userQ < p->minFlow-1e-8 || userQ > p->maxFlow+1e-8) p->invalidFlow += dt;
            else {
                p->shaftKwh += table_lookup(Curve+p->powerCurve, userQ)*dt/3600;
                p->maxNpsh = MAX(p->maxNpsh, table_lookup(Curve+p->npshCurve, userQ));
            }
        }
        p->previousOn = on;
    }
}

WL_NETWORK_EXPORT int wl_pumpsRead(int j, double *v, int n)
{
    WLPumpObservation *p;
    if (!IsStartedFlag || !wlPumps || j < 0 || j >= Nobjects[LINK] || !v || n != 13) return -1;
    p = wlPumps+j;
    if (!p->active) return -2;
    v[0]=p->volume; v[1]=p->running; v[2]=p->flowing; v[3]=p->starts; v[4]=p->peakFlow;
    v[5]=p->running ? p->minHead : 0; v[6]=p->running ? p->maxHead : 0;
    v[7]=p->invalidHead; v[8]=p->invalidFlow; v[9]=p->shaftKwh; v[10]=p->maxNpsh;
    v[11]=p->observed; v[12]=p->steps;
    return 0;
}
