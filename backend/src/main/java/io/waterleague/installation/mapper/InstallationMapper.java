package io.waterleague.installation.mapper;

import io.waterleague.installation.entity.SharedInstallation;
import io.waterleague.installation.view.InstallationView;

public final class InstallationMapper {
  private InstallationMapper() {}

  public static InstallationView view(
      SharedInstallation i, io.waterleague.installation.view.SiteView site) {
    return new InstallationView(
        i.id(),
        i.districtId(),
        i.cellId(),
        i.ownerId(),
        i.ownerName(),
        i.facilityType().name(),
        i.areaM2(),
        i.cost(),
        i.installedAt(),
        site.center(),
        site.heightM(),
        i.seasonEndsAt());
  }
}
