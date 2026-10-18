package io.waterleague.infrastructure.mapper;

import io.waterleague.infrastructure.entity.InfrastructureAsset;
import io.waterleague.infrastructure.view.InfrastructureView;
import org.springframework.stereotype.Component;

@Component
public class InfrastructureMapper {
  public InfrastructureView.Asset toView(InfrastructureAsset a) {
    return new InfrastructureView.Asset(
        a.id(),
        a.sourceId(),
        a.name(),
        a.kind(),
        a.center(),
        a.districtId(),
        a.geometryEvidence(),
        a.verticalLayer(),
        a.validFrom(),
        a.validTo(),
        a.operationStatus(),
        a.hydraulicStatus(),
        a.pumpSpecs().deepCopy(),
        a.footprint() == null ? null : a.footprint().deepCopy());
  }
}
