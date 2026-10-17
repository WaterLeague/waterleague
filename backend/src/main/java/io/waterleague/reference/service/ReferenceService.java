package io.waterleague.reference.service;

import io.waterleague.common.service.JsonService;
import io.waterleague.comparison.service.ComparisonCompatibilityService;
import io.waterleague.model.service.LabModelService;
import io.waterleague.reference.entity.ReferenceDocument;
import io.waterleague.reference.mapper.ReferenceMapper;
import io.waterleague.reference.repository.ReferenceRepository;
import io.waterleague.reference.view.ReferenceView;
import io.waterleague.strategy.entity.Placement;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

@Service
public class ReferenceService {
  private final ReferenceRepository references;
  private final ReferenceMapper mapper;
  private final LabModelService models;

  public ReferenceService(
      ReferenceRepository r,
      ReferenceMapper v,
      LabModelService m,
      JsonService json,
      ComparisonCompatibilityService compatibility) {
    references = r;
    mapper = v;
    models = m;
    for (var document : r.all()) {
      var report = document.report();
      String training = report.path("trainingModelHash").asString();
      var source = (JsonNode) models.view(training).get("model");
      for (String hash : document.modelHashes())
        compatibility.require(source, (JsonNode) models.view(hash).get("model"));
      if (!report.path("plans").isArray() || report.path("plans").size() != 3)
        throw new IllegalStateException("CPU 예산별 기준안 누락");
      for (var plan : report.path("plans")) {
        var placements = List.of(json.read(plan.path("placements").toString(), Placement[].class));
        for (String hash : document.modelHashes()) {
          BigDecimal cost = models.validate(hash, placements);
          if (cost.compareTo(plan.path("cost").decimalValue()) != 0
              || cost.compareTo(plan.path("budget").decimalValue()) > 0)
            throw new IllegalStateException("CPU 기준안 예산 불일치");
        }
        Set<String> evaluated = new HashSet<>();
        for (var evaluation : plan.path("evaluations"))
          if (!evaluated.add(evaluation.path("modelHash").asString()))
            throw new IllegalStateException("CPU 강우 결과 중복");
        if (!evaluated.equals(new HashSet<>(document.modelHashes())))
          throw new IllegalStateException("CPU 강우 결과 범위 불일치");
      }
    }
    r.require(models.hash());
  }

  private ReferenceDocument document(String hash) {
    return references.require(hash == null ? models.hash() : hash);
  }

  public ReferenceView view(String hash) {
    var document = document(hash);
    return mapper.view(document.hash(), document.report());
  }

  public String source(String hash) {
    return document(hash).source();
  }

  public String ledger(String hash) {
    return document(hash).ledger();
  }
}
