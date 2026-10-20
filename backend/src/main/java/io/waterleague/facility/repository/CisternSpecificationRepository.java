package io.waterleague.facility.repository;

import io.waterleague.common.exception.DomainException;
import io.waterleague.common.exception.ErrorCode;
import io.waterleague.common.service.JsonService;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.JsonNode;

@Repository
public class CisternSpecificationRepository {
  public static final String HASH =
      "6fdf0d866bb28901196cd4354a786228fa1a53b77a3d8c8e805e5d9744edde17";
  private final JsonNode catalog;
  private final String raw;

  public CisternSpecificationRepository(JsonService json) throws java.io.IOException {
    try (var in =
        new ClassPathResource("facilities/cistern-specifications-v1.json").getInputStream()) {
      var bytes = in.readNBytes(65537);
      raw = new String(bytes, StandardCharsets.UTF_8);
      if (bytes.length > 65536 || !json.hash(raw).equals(HASH))
        throw new IllegalStateException("이용조 공개 규격 무결성 오류");
      catalog = json.tree(raw);
    }
  }

  public String raw() {
    return raw;
  }

  public JsonNode catalog() {
    return catalog.deepCopy();
  }

  public JsonNode require(String id, String hash) {
    if (!HASH.equals(hash)) throw new DomainException(ErrorCode.CONFLICT);
    for (var spec : catalog.path("specifications"))
      if (spec.path("id").asString().equals(id)) return spec.deepCopy();
    throw new DomainException(ErrorCode.PLACEMENT_INVALID);
  }
}
