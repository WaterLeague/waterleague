package io.waterleague.installation.entity;

import io.waterleague.strategy.entity.FacilityType;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record SharedInstallation(
    UUID id,
    String districtId,
    String cellId,
    UUID ownerId,
    String ownerName,
    String modelHash,
    FacilityType facilityType,
    BigDecimal areaM2,
    BigDecimal cost,
    Instant installedAt,
    Instant removedAt,
    Instant seasonEndsAt) {
  public SharedInstallation(
      UUID id,
      String districtId,
      String cellId,
      UUID ownerId,
      String ownerName,
      String modelHash,
      FacilityType facilityType,
      BigDecimal areaM2,
      BigDecimal cost,
      Instant installedAt,
      Instant removedAt) {
    this(
        id,
        districtId,
        cellId,
        ownerId,
        ownerName,
        modelHash,
        facilityType,
        areaM2,
        cost,
        installedAt,
        removedAt,
        null);
  }
}
