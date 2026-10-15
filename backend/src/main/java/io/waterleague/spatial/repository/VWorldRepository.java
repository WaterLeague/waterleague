package io.waterleague.spatial.repository;

import io.waterleague.common.exception.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

@Repository
public class VWorldRepository {
  private final String key;
  private final String domain;
  private final HttpClient client =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(5))
          .followRedirects(HttpClient.Redirect.NEVER)
          .build();

  public VWorldRepository(
      @Value("${waterleague.vworld-key:}") String key,
      @Value("${waterleague.vworld-domain:http://127.0.0.1:5173}") String domain) {
    this.key = key;
    this.domain = domain;
  }

  public String buildings() {
    if (key.isBlank()) throw new DomainException(ErrorCode.SPATIAL_ACCESS_UNAVAILABLE);
    try {
      var parameters = new LinkedHashMap<String, String>();
      parameters.put("service", "data");
      parameters.put("version", "2.0");
      parameters.put("request", "GetFeature");
      parameters.put("data", "LT_C_SPBD");
      parameters.put("geomFilter", "BOX(127.0525,37.5430,127.0555,37.5455)");
      parameters.put("columns", "bd_mgt_sn,buld_nm,gro_flo_co");
      parameters.put("size", "1000");
      parameters.put("page", "1");
      parameters.put("format", "json");
      parameters.put("crs", "EPSG:4326");
      parameters.put("domain", domain);
      parameters.put("key", key);
      var query =
          parameters.entrySet().stream()
              .map(e -> e.getKey() + "=" + URLEncoder.encode(e.getValue(), StandardCharsets.UTF_8))
              .collect(Collectors.joining("&"));
      var request =
          HttpRequest.newBuilder(URI.create("https://api.vworld.kr/req/data?" + query))
              .timeout(Duration.ofSeconds(15))
              .header("Accept", "application/json")
              .GET()
              .build();
      var response =
          client.send(
              request,
              HttpResponse.BodyHandlers.limiting(
                  HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8), 2_000_000));
      if (response.statusCode() != 200) throw new DomainException(ErrorCode.SPATIAL_UNAVAILABLE);
      if (response.body().contains(key)) throw new DomainException(ErrorCode.SPATIAL_DATA_INVALID);
      return response.body();
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new DomainException(ErrorCode.SPATIAL_UNAVAILABLE);
    } catch (java.io.IOException | IllegalArgumentException e) {
      // 외부 예외의 인증 쿼리와 응답 원문은 로그·오류 본문으로 전달하지 않는다.
      throw new DomainException(ErrorCode.SPATIAL_UNAVAILABLE);
    }
  }
}
