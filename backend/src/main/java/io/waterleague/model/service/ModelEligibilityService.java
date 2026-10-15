package io.waterleague.model.service;

import io.waterleague.model.entity.*;
import io.waterleague.model.exception.ModelNotEligibleException;
import org.springframework.stereotype.Service;

@Service
public class ModelEligibilityService {
    public void requireOfficial(ModelEvidence evidence, String rainfallHash, boolean usesPeak, boolean siteClaim) {
        boolean verified = evidence.level() == ValidationLevel.BENCHMARKED || evidence.level() == ValidationLevel.SITE_VALIDATED;
        if (!verified || evidence.revoked() || evidence.reportHash() == null
            || !evidence.reportHash().matches("[a-f0-9]{64}")
            || !evidence.approvedRainfallHashes().contains(rainfallHash)
            || (usesPeak && !evidence.peakValidated())
            || (siteClaim && evidence.level() != ValidationLevel.SITE_VALIDATED)) {
            throw new ModelNotEligibleException();
        }
    }
}
