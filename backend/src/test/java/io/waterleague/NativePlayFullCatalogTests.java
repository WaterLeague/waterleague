package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.service.JsonService;
import io.waterleague.spatial.repository.*;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class NativePlayFullCatalogTests {
  @Test
  void readsAllDistrictsFromThePublishedBundleAndExportsExactApiCellsForWorkerComparison()
      throws Exception {
    var json = new JsonService(new ObjectMapper());
    var source = new NativePlayBundle(json, Path.of("../tmp/native-spatial").toAbsolutePath().normalize().toString());
    var repository = new NativePlayRepository(source, json);
    assertThat(source.manifest().path("recordCount").asInt()).isEqualTo(1_023_100);
    var districts = new TreeSet<String>();
    source.manifest().path("districtKindCounts").properties()
        .forEach(entry -> districts.add(entry.getKey().split(":")[0]));
    assertThat(districts).hasSize(25);
    var cases = new ArrayList<Map<String, Object>>();
    try (var connection = repository.connection(); var query = connection.prepareStatement(
        "SELECT id,cx,cy FROM sites WHERE district_id=? AND kind='ROOF' AND allowed_mask<>0 ORDER BY fid LIMIT 1")) {
      for (String district : districts) {
        query.setString(1, district);
        try (var rows = query.executeQuery()) {
          assertThat(rows.next()).isTrue();
          String identifier = rows.getString(1);
          double x = rows.getDouble(2), y = rows.getDouble(3);
          var cells = repository.bounds(x - 50, y - 50, x + 50, y + 50, district, null, 2000, false);
          assertThat(cells).anyMatch(cell -> cell.path("id").asString().equals(identifier));
          for (var cell : cells) assertThat(repository.require(district, cell.path("id").asString())).isEqualTo(cell);
          cases.add(Map.of("districtId", district, "bounds", List.of(x - 50, y - 50, x + 50, y + 50), "sites", cells));
        }
      }
    }
    var proof = Map.of("catalogSha256", repository.sha256(), "bundleSha256", NativePlayBundle.MANIFEST_SHA256,
        "coordinateSystem", "EPSG:5186", "cases", cases);
    Files.writeString(Path.of("target/native-play-cross-runtime-v1.json"), json.write(proof) + "\n");
  }
}
