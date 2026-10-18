package io.waterleague.surface.dto;

import io.waterleague.common.exception.*;

public record SurfaceFrameRequest(int index, double minX, double minY, double maxX, double maxY) {
  public void validate() {
    if (index < 0
        || index >= 10000
        || !Double.isFinite(minX)
        || !Double.isFinite(minY)
        || !Double.isFinite(maxX)
        || !Double.isFinite(maxY)
        || minX >= maxX
        || minY >= maxY
        || minX < -60000
        || minY < -60000
        || maxX > 60000
        || maxY > 60000) throw new DomainException(ErrorCode.REQUEST_INVALID);
  }
}
