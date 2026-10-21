package io.waterleague.urban.repository;

import io.waterleague.common.exception.*;
import io.waterleague.common.repository.ExternalRequestStore;
import io.waterleague.common.repository.ExternalRequestStore.Response;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import org.springframework.stereotype.Repository;

@Repository
public class SeoulUrbanRepository {
  public static final String SOURCE = "https://data.seoul.go.kr/SeoulRtd/";
  private final ExternalRequestStore store;
  private final ExternalRequestStore.Policy policy =
      ExternalRequestStore.policy("SEOUL_URBAN", "PUBLIC", 4000, 1_000_000_000L);

  public SeoulUrbanRepository(ExternalRequestStore store) {
    this.store = store;
  }

  private final HttpClient client =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(4))
          .followRedirects(HttpClient.Redirect.NEVER)
          .build();

  public Response population(String name) {
    return fetch("ppltn_congest", name);
  }

  public Response traffic(String name) {
    return fetch("road", name);
  }

  private Response fetch(String service, String name) {
    // 공개 화면과 같은 HTTPS 조회만 허용하며 브라우저의 쿠키·인증키를 전달하지 않는다.
    var uri =
        URI.create(
            SOURCE
                + "api/"
                + service
                + "?hotspotNm="
                + URLEncoder.encode(name, StandardCharsets.UTF_8));
    try {
      return store.acquire(
          policy, uri.toString(), Duration.ofSeconds(300), 1_000_000, () -> request(uri));
    } catch (ExternalRequestStore.Unavailable e) {
      throw new DomainException(ErrorCode.URBAN_UNAVAILABLE);
    }
  }

  private String request(URI uri) {
    try {
      var request =
          HttpRequest.newBuilder(uri)
              .timeout(Duration.ofSeconds(10))
              .header("Referer", SOURCE)
              .header("Accept", "application/json")
              .GET()
              .build();
      var response =
          client.send(
              request,
              HttpResponse.BodyHandlers.limiting(
                  HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8), 1_000_000));
      if (response.statusCode() != 200)
        store.block(
            policy,
            response.statusCode(),
            ExternalRequestStore.retrySeconds(
                response.headers().firstValue("Retry-After").orElse("")));
      if (response.statusCode() != 200
          || !response
              .headers()
              .firstValue("Content-Type")
              .orElse("")
              .toLowerCase(java.util.Locale.ROOT)
              .startsWith("application/json"))
        throw new DomainException(ErrorCode.URBAN_UNAVAILABLE);
      return response.body();
    } catch (DomainException e) {
      throw e;
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new DomainException(ErrorCode.URBAN_UNAVAILABLE);
    } catch (Exception e) {
      throw new DomainException(ErrorCode.URBAN_UNAVAILABLE);
    }
  }
}
