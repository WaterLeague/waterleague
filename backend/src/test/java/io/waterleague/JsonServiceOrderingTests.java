package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.service.JsonService;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class JsonServiceOrderingTests {
  private final ObjectMapper mapper = new ObjectMapper();
  private final JsonService json = new JsonService(mapper);

  @Test
  void writesNestedMapsAndTreesInStableOrderWithoutChangingArraysAmountsOrNulls() {
    var reverse = new LinkedHashMap<String, Object>();
    reverse.put("z", List.of(3, 1, 2));
    reverse.put("b", new BigDecimal("171428.9999"));
    reverse.put("a", json.tree("{\"z\":null,\"a\":{\"z\":2,\"a\":1}}"));
    var forward = new LinkedHashMap<String, Object>();
    forward.put("a", json.tree("{\"a\":{\"a\":1,\"z\":2},\"z\":null}"));
    forward.put("b", new BigDecimal("171428.9999"));
    forward.put("z", List.of(3, 1, 2));
    var expected = "{\"a\":{\"a\":{\"a\":1,\"z\":2},\"z\":null},\"b\":171428.9999,\"z\":[3,1,2]}";
    assertThat(json.write(reverse)).isEqualTo(expected).isEqualTo(json.write(forward));
    assertThat(json.hash(json.write(reverse))).isEqualTo(json.hash(json.write(forward)));
  }

  @Test
  void preservesStoredRawHashesAndDoesNotMutateTheSharedMapperOrParsedTree() {
    var raw = "{\"z\":2,\"a\":1}";
    var tree = json.tree(raw);
    var original = mapper.writeValueAsString(tree);
    var hash = json.hash(raw);
    assertThat(json.write(tree)).isEqualTo("{\"a\":1,\"z\":2}");
    assertThat(mapper.writeValueAsString(tree)).isEqualTo(original).isEqualTo(raw);
    assertThat(json.hash(raw)).isEqualTo(hash).isNotEqualTo(json.hash(json.write(tree)));
  }

  @Test
  void refusesIncomparableMapKeysInsteadOfHashingAnArbitraryOrder() {
    assertThatThrownBy(() -> json.write(Map.of("a", 1, 2, 3))).isInstanceOf(RuntimeException.class);
  }

  @Test
  void preservesTheSameNestedMapOfCostHashAcrossIndependentJvms() throws Exception {
    var java = Path.of(System.getProperty("java.home"), "bin", "java").toString();
    var classpath =
        System.getProperty("surefire.test.class.path", System.getProperty("java.class.path"));
    var expected = new JsonService(new ObjectMapper()).write(Probe.value());
    for (int i = 0; i < 3; i++) {
      var process = new ProcessBuilder(java, "-cp", classpath, Probe.class.getName()).start();
      try {
        assertThat(process.waitFor(Duration.ofSeconds(15))).isTrue();
        assertThat(process.exitValue()).isZero();
        assertThat(new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8))
            .isEqualTo(expected);
      } finally {
        if (process.isAlive()) process.destroyForcibly();
      }
    }
  }

  public static class Probe {
    static Object value() {
      return Map.of(
          "currency",
          "KRW",
          "quantityM2",
          new BigDecimal("10.00"),
          "lines",
          List.of(
              Map.of(
                  "quantity", new BigDecimal("10.00"), "amountKrw", new BigDecimal("3500000.00"))),
          "source",
          new JsonService(new ObjectMapper())
              .tree("{\"scope\":\"시험용\",\"sourceSha256\":\"public-test-only\"}"));
    }

    public static void main(String[] args) {
      System.out.print(new JsonService(new ObjectMapper()).write(value()));
    }
  }
}
