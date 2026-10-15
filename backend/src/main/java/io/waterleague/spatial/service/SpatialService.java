package io.waterleague.spatial.service;

import io.waterleague.account.entity.Account;
import io.waterleague.common.exception.*;
import io.waterleague.common.security.RateLimitService;
import io.waterleague.spatial.mapper.SpatialMapper;
import io.waterleague.spatial.repository.VWorldRepository;
import io.waterleague.spatial.view.SpatialView;
import java.util.concurrent.Semaphore;
import org.springframework.stereotype.Service;

@Service
public class SpatialService {
  private final VWorldRepository repository;
  private final SpatialMapper mapper;
  private final RateLimitService limits;
  private final Semaphore requests = new Semaphore(2);

  public SpatialService(VWorldRepository r, SpatialMapper m, RateLimitService l) {
    repository = r;
    mapper = m;
    limits = l;
  }

  public SpatialView buildings(Account actor) {
    limits.check("spatial-account:" + actor.id(), 10, 3600);
    limits.check("spatial-global", 60, 3600);
    if (!requests.tryAcquire()) throw new DomainException(ErrorCode.SPATIAL_UNAVAILABLE);
    try {
      return mapper.map(repository.buildings());
    } finally {
      requests.release();
    }
  }
}
