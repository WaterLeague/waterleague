package io.waterleague.spatial.service;

import io.waterleague.account.entity.Account;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.spatial.mapper.SpatialMapper;
import io.waterleague.spatial.repository.SpatialSnapshotRepository;
import io.waterleague.spatial.view.SpatialView;
import org.springframework.stereotype.Service;

@Service
public class SpatialService {
  private final SpatialView snapshot;
  private final RateLimitService limits;

  public SpatialService(SpatialSnapshotRepository r, SpatialMapper m, RateLimitService l) {
    snapshot = m.map(r.snapshot());
    limits = l;
  }

  public SpatialView buildings(Account actor) {
    limits.check("spatial-account:" + actor.id(), 60, 60);
    return snapshot;
  }
}
