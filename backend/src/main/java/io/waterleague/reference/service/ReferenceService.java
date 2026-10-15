package io.waterleague.reference.service;

import io.waterleague.common.service.JsonService;
import io.waterleague.model.service.LabModelService;
import io.waterleague.reference.mapper.ReferenceMapper;
import io.waterleague.reference.repository.ReferenceRepository;
import io.waterleague.reference.view.ReferenceView;
import io.waterleague.strategy.entity.Placement;
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class ReferenceService {
  private final ReferenceRepository references;
  private final ReferenceMapper mapper;

  public ReferenceService(
      ReferenceRepository r, ReferenceMapper v, LabModelService models, JsonService json) {
    references = r;
    mapper = v;
    var report = r.report();
    for (var hash : report.path("modelHashes")) models.requireHash(hash.asString());
    for (var plan : report.path("plans")) {
      var placements = json.read(plan.path("placements").toString(), Placement[].class);
      BigDecimal cost =
          models.validate(
              report.path("trainingModelHash").asString(), java.util.List.of(placements));
      if (cost.compareTo(plan.path("cost").decimalValue()) != 0
          || cost.compareTo(plan.path("budget").decimalValue()) > 0)
        throw new IllegalStateException("CPU 기준안 예산 불일치");
    }
  }

  public ReferenceView view() {
    return mapper.view(references.hash(), references.report());
  }

  public String source() {
    return references.source();
  }

  public String ledger() {
    return references.ledger();
  }
}
