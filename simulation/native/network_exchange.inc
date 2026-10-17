/* 결합용 별도 빌드: EPA 수리식은 유지하고 짧은 교환 간격과 유입부 제원을 노출한다. */
WL_NETWORK_EXPORT int wl_exchangeVersion(void) { return 1; }

WL_NETWORK_EXPORT int wl_exchangeClockSettings(double *v, int n)
{
    if (!IsStartedFlag || !v || n != 3) return -1;
    v[0] = RouteStep;
    v[1] = MinRouteStep;
    v[2] = CourantFactor;
    return 0;
}

WL_NETWORK_EXPORT int wl_exchangeAdvance(int milliseconds)
{
    double realRouteStep = RouteStep, elapsedTime;
    int error;
    if (!IsStartedFlag || !wlPreviousRates || milliseconds < 1 || milliseconds > 60000)
        return -1;
    RoutingDuration = MIN(TotalDuration, NewRoutingTime + milliseconds);
    RouteStep = MIN(RouteStep, milliseconds / 1000.0);
    do { error = wl_observedStep(&elapsedTime); } while (elapsedTime > 0.0 && !error);
    RouteStep = realRouteStep;
    RoutingDuration = TotalDuration;
    ElapsedTime = NewRoutingTime < TotalDuration ? NewRoutingTime / MSECperDAY : 0.0;
    return error;
}

WL_NETWORK_EXPORT int wl_exchangePort(int j, double surfaceHeadM, double *v, int n)
{
    const double ft3ToM3 = 0.028316846592;
    double crest, head, q;
    int a, b, k, i, connections = 0;
    if (!IsStartedFlag || !wlPreviousRates || !v || n != 11 || j < 0 || j >= Nobjects[LINK])
        return -1;
    if (Link[j].type != ORIFICE) return -2;
    a = Link[j].node1;
    b = Link[j].node2;
    k = Link[j].subIndex;
    if (Orifice[k].type != BOTTOM_ORIFICE || Node[a].type == OUTFALL || Node[b].type != OUTFALL
        || Link[j].setting != 1.0 || Link[j].targetSetting != 1.0 || Orifice[k].orate != 0.0
        || Link[j].hasFlapGate || Node[b].extInflow || Node[b].dwfInflow || Node[b].rdiiInflow
        || Outfall[Node[b].subIndex].hasFlapGate
        || Outfall[Node[b].subIndex].routeTo >= 0) return -3;
    for (i = 0; i < Nobjects[LINK]; i++)
        if (Link[i].node1 == b || Link[i].node2 == b) connections++;
    if (connections != 1) return -4;
    for (i = 0; i < Nobjects[SUBCATCH]; i++)
        if (Subcatch[i].outNode == b) return -5;
    crest = Node[a].invertElev + Link[j].offset1;
    if (fabs(Node[b].invertElev - crest) > 1.e-6) return -6;
    head = MAX(0.0, surfaceHeadM / 0.3048 - crest);
    /* 하류 잠김을 무시한 EPA 자유 유출식으로 지표 배수의 상한만 읽는다. */
    q = 0.0;
    if (head > FUDGE && Orifice[k].hCrit > 0.0)
        q = head < Orifice[k].hCrit
            ? Orifice[k].cWeir * pow(head / Orifice[k].hCrit, 1.5)
            : Orifice[k].cOrif * sqrt(head);
    v[0] = a;
    v[1] = b;
    v[2] = crest * 0.3048;
    v[3] = Link[j].xsect.aFull * 0.3048 * 0.3048;
    v[4] = Orifice[k].cDisch;
    v[5] = Orifice[k].hCrit * 0.3048;
    v[6] = q * ft3ToM3;
    v[7] = wlPreviousRates[3*b+2] * ft3ToM3;
    v[8] = wlIntegratedVolumes[3*b+1] * ft3ToM3;
    v[9] = wlIntegratedVolumes[3*b+2] * ft3ToM3;
    v[10] = (Node[a].invertElev + Node[a].newDepth) * 0.3048;
    return 0;
}
