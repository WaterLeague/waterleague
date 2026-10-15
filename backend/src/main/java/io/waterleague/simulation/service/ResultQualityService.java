package io.waterleague.simulation.service;

import io.waterleague.simulation.entity.RunMetrics;
import io.waterleague.simulation.exception.ResultQualityException;
import org.springframework.stereotype.Service;

@Service
public class ResultQualityService {
    public void validate(RunMetrics result, double maxErrorPercent) {
        if (!Double.isFinite(maxErrorPercent) || maxErrorPercent <= 0
            || !nonNegative(result.runoffM3()) || !nonNegative(result.peakM3s()) || !nonNegative(result.finalStorageM3())
            || !Double.isFinite(result.runoffContinuityPercent()) || Math.abs(result.runoffContinuityPercent()) > maxErrorPercent
            || (result.routed() && (result.routingContinuityPercent() == null
                || !Double.isFinite(result.routingContinuityPercent()) || Math.abs(result.routingContinuityPercent()) > maxErrorPercent))) {
            throw new ResultQualityException();
        }
    }
    private boolean nonNegative(double value) { return Double.isFinite(value) && value >= 0; }
}
