package io.waterleague.utilization.mapper;

import io.waterleague.utilization.entity.*;
import io.waterleague.utilization.view.*;
import org.springframework.stereotype.Component;

@Component
public class UtilizationMapper {
  public UtilizationView view(UtilizationRequest r) {
    return new UtilizationView(
        r.id(),
        r.jobId(),
        r.versionId(),
        r.modelHash(),
        r.organizationId(),
        r.organizationName(),
        r.title(),
        r.purpose(),
        r.policyVersion(),
        r.termsHash(),
        r.state(),
        r.revision(),
        r.createdAt(),
        r.updatedAt());
  }

  public ReviewView view(StrategyReview r) {
    return new ReviewView(
        r.id(),
        r.jobId(),
        r.organizationId(),
        r.organizationName(),
        r.state(),
        r.reason(),
        r.limitations(),
        r.createdAt());
  }
}
