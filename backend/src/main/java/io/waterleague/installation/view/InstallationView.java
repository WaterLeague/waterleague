package io.waterleague.installation.view;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record InstallationView(
    UUID id,
    String districtId,
    String cellId,
    UUID ownerId,
    String ownerName,
    String facilityType,
    BigDecimal areaM2,
    BigDecimal cost,
    Instant installedAt) {}
