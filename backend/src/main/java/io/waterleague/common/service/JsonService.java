package io.waterleague.common.service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.ObjectWriter;
import tools.jackson.databind.SerializationFeature;
import tools.jackson.databind.cfg.JsonNodeFeature;

@Component
public class JsonService {
  private final ObjectMapper mapper;
  private final ObjectWriter writer;

  public JsonService(ObjectMapper mapper) {
    this.mapper = mapper;
    // Map.of의 JVM별 순서와 읽은 트리의 입력 순서가 새 원문 해시에 섞이지 않게 한다.
    this.writer =
        mapper
            .writer()
            .with(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
            .with(SerializationFeature.FAIL_ON_ORDER_MAP_BY_INCOMPARABLE_KEY)
            .with(JsonNodeFeature.WRITE_PROPERTIES_SORTED);
  }

  public String write(Object value) {
    return writer.writeValueAsString(value);
  }

  public <T> T read(String value, Class<T> type) {
    return mapper.readValue(value, type);
  }

  public tools.jackson.databind.JsonNode tree(String value) {
    return mapper.readTree(value);
  }

  public String hash(String value) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
    } catch (Exception e) {
      throw new IllegalStateException(e);
    }
  }
}
