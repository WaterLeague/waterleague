package io.waterleague.surface.repository;

import io.waterleague.common.service.JsonService;
import io.waterleague.surface.exception.SurfaceResultException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;

@Repository
public class PublicSurfaceModelRepository {
  public record Model(
      String id,
      String name,
      String inputBundleSha256,
      String numericalPolicySha256,
      String classification,
      double[] bounds) {
    public Model {
      if (id == null
          || !id.matches("[a-z0-9-]{1,80}")
          || name == null
          || name.isBlank()
          || name.length() > 120
          || inputBundleSha256 == null
          || !inputBundleSha256.matches("[a-f0-9]{64}")
          || numericalPolicySha256 == null
          || !numericalPolicySha256.matches("[a-f0-9]{64}")
          || !"PUBLIC_INPUT_UNCALIBRATED_CURRENT_BASELINE".equals(classification)
          || bounds == null
          || bounds.length != 4
          || Arrays.stream(bounds).anyMatch(v -> !Double.isFinite(v) || Math.abs(v) > 60000)
          || bounds[0] >= bounds[2]
          || bounds[1] >= bounds[3]) throw new SurfaceResultException();
      bounds = bounds.clone();
    }

    @Override
    public double[] bounds() {
      return bounds.clone();
    }
  }

  private final Map<String, Model> models;

  public PublicSurfaceModelRepository(JsonService json) throws IOException {
    try (var in = new ClassPathResource("surface/public-models-v1.json").getInputStream()) {
      String raw = new String(in.readNBytes(100001), StandardCharsets.UTF_8);
      if (!json.hash(raw)
          .equals("e4d5625e18077516f2d00c69fb2c6644765e5075bd6f2823578c0f791cd59fe3"))
        throw new SurfaceResultException();
      var root = json.tree(raw);
      if (root.path("schemaVersion").asInt() != 1
          || !root.path("scope").asString().equals("PUBLIC_CURRENT_BASELINE_ONLY"))
        throw new SurfaceResultException();
      if (!root.path("models").isArray() || root.path("models").size() > 128)
        throw new SurfaceResultException();
      var values = new HashMap<String, Model>();
      for (var row : root.path("models")) {
        var bounds = new double[4];
        for (int i = 0; i < 4; i++) bounds[i] = row.path("bounds").get(i).asDouble();
        var model =
            new Model(
                row.path("id").asString(),
                row.path("name").asString(),
                row.path("inputBundleSha256").asString(),
                row.path("numericalPolicySha256").asString(),
                row.path("classification").asString(),
                bounds);
        if (values.put(model.id(), model) != null) throw new SurfaceResultException();
      }
      models = Map.copyOf(values);
    }
  }

  public Optional<Model> find(String id) {
    return Optional.ofNullable(models.get(id));
  }
}
