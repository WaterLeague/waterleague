package io.waterleague.ranking.service;

import io.waterleague.model.entity.ModelEvidence;
import io.waterleague.model.service.ModelEligibilityService;
import io.waterleague.simulation.entity.RunMetrics;
import io.waterleague.simulation.service.ResultQualityService;
import io.waterleague.simulation.exception.ResultQualityException;
import org.springframework.stereotype.Service;
import java.math.*;

@Service
public class ScoreService {
    private final ModelEligibilityService eligibility;
    private final ResultQualityService quality;
    public ScoreService(ModelEligibilityService eligibility, ResultQualityService quality) {
        this.eligibility = eligibility; this.quality = quality;
    }
    public BigDecimal calculate(ModelEvidence evidence, String rainfallHash, RunMetrics baseline, RunMetrics strategy,
                                BigDecimal runoffWeight, BigDecimal peakWeight) {
        if (runoffWeight == null || peakWeight == null || runoffWeight.signum() < 0 || peakWeight.signum() < 0
            || runoffWeight.add(peakWeight).compareTo(BigDecimal.ONE) != 0) throw new ResultQualityException();
        eligibility.requireOfficial(evidence, rainfallHash, peakWeight.signum() > 0, false);
        quality.validate(baseline, 1); quality.validate(strategy, 1);
        var volume = runoffWeight.signum() == 0 ? BigDecimal.ZERO : reduction(baseline.runoffM3(), strategy.runoffM3());
        var peak = peakWeight.signum() == 0 ? BigDecimal.ZERO : reduction(baseline.peakM3s(), strategy.peakM3s());
        return volume.multiply(runoffWeight).add(peak.multiply(peakWeight)).multiply(BigDecimal.valueOf(100))
            .setScale(8, RoundingMode.HALF_EVEN);
    }
    private BigDecimal reduction(double baseline, double strategy) {
        // 무유출·검출한계 미만 기준안의 불안정한 점수를 차단한다.
        if (baseline <= 0.000001) throw new ResultQualityException();
        var base = BigDecimal.valueOf(baseline);
        return base.subtract(BigDecimal.valueOf(strategy)).divide(base, MathContext.DECIMAL128);
    }
}
