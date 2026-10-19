/* EPA 침투식의 배치 호출과 단위 변환만 수행한다. */
typedef struct {
    int count;
    TGrnAmpt cells[];
} WLSurfaceSoils;

int wl_soilVersion(void) { return 1; }

void* wl_soilCreate(int count, const double* parameters)
{
    int i;
    WLSurfaceSoils* bank;
    if (count < 1 || count > 200000 || !parameters) return NULL;
    for (i = 0; i < count * 3; i++)
        if (!isfinite(parameters[i])) return NULL;
    bank = calloc(1, sizeof(WLSurfaceSoils) + count * sizeof(TGrnAmpt));
    if (!bank) return NULL;
    bank->count = count;
    UnitSystem = SI;
    for (i = 0; i < count; i++) {
        double p[3] = {parameters[3*i], parameters[3*i+1], parameters[3*i+2]};
        if (!grnampt_setParams(&bank->cells[i], p)) { free(bank); return NULL; }
        grnampt_initState(&bank->cells[i]);
    }
    return bank;
}

int wl_soilAdvance(void* pointer, int count, double dt, int modified,
    double recovery, const double* rainfallMps, const double* pondedM, double* infiltratedM)
{
    int i;
    WLSurfaceSoils* bank = pointer;
    if (!bank || count != bank->count || !rainfallMps || !pondedM || !infiltratedM
        || !isfinite(dt) || dt <= 0 || !isfinite(recovery) || recovery <= 0
        || (modified != 0 && modified != 1)) return 1;
    for (i = 0; i < count; i++)
        if (!isfinite(rainfallMps[i]) || rainfallMps[i] < 0
            || !isfinite(pondedM[i]) || pondedM[i] < 0) return 2;
    /* 별도 라이브러리에서만 전역 계수를 설정하며 호출자는 직렬 실행한다. */
    InfilFactor = 1.0;
    Evap.recoveryFactor = recovery;
    for (i = 0; i < count; i++) {
        infiltratedM[i] = grnampt_getInfil(&bank->cells[i], dt,
            rainfallMps[i] / 0.3048, pondedM[i] / 0.3048,
            modified ? MOD_GREEN_AMPT : GREEN_AMPT) * dt * 0.3048;
        if (!isfinite(infiltratedM[i]) || infiltratedM[i] < 0) return 3;
    }
    return 0;
}

int wl_soilState(void* pointer, int count, double* output)
{
    int i;
    WLSurfaceSoils* bank = pointer;
    if (!bank || count != bank->count || !output) return 1;
    for (i = 0; i < count; i++) grnampt_getState(&bank->cells[i], output + 5*i);
    return 0;
}

void wl_soilRelease(void* pointer) { free(pointer); }
