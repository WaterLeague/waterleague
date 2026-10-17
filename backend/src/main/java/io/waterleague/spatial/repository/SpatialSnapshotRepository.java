package io.waterleague.spatial.repository;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.spatial.entity.SpatialSnapshot;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Repository;

@Repository
public class SpatialSnapshotRepository {
  private final SpatialSnapshot snapshot;

  public SpatialSnapshotRepository(
      @Value("classpath:spatial/seongsu-buildings.json") Resource data,
      @Value("classpath:spatial/seongsu-buildings.sha256") Resource checksum) {
    try (var input = data.getInputStream();
        var digestInput = checksum.getInputStream()) {
      byte[] bytes = input.readNBytes(2_000_001);
      String expected = new String(digestInput.readNBytes(66), StandardCharsets.US_ASCII).strip();
      String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
      if (bytes.length == 0
          || bytes.length > 2_000_000
          || !expected.matches("[a-f0-9]{64}")
          || !actual.equals(expected)) {
        throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
      }
      // 서버 시작 시 고정 자료를 검사해 요청별 외부 조회와 시점 변동을 차단한다.
      snapshot = new SpatialSnapshot(new String(bytes, StandardCharsets.UTF_8), actual);
    } catch (Exception e) {
      throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
    }
  }

  public SpatialSnapshot snapshot() {
    return snapshot;
  }
}
