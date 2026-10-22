package io.waterleague.gameanalysis.service;

import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class UpstageClient {
  private final HttpClient http =
      HttpClient.newBuilder()
          .connectTimeout(Duration.ofSeconds(5))
          .followRedirects(HttpClient.Redirect.NEVER)
          .build();
  public static final int MAXIMUM_RESPONSE = 65536;

  public static final class Unavailable extends RuntimeException {
    final int status;

    public Unavailable(int status) {
      this.status = status;
    }
  }

  public String complete(String key, String payload) {
    var request =
        HttpRequest.newBuilder(URI.create("https://api.upstage.ai/v1/chat/completions"))
            .timeout(Duration.ofSeconds(25))
            .header("Authorization", "Bearer " + key)
            .header("Content-Type", "application/json")
            .header("Accept", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
            .build();
    try {
      var pending =
          http.sendAsync(
              request,
              HttpResponse.BodyHandlers.limiting(
                  HttpResponse.BodyHandlers.ofByteArray(), MAXIMUM_RESPONSE));
      try {
        var response = pending.get(25, java.util.concurrent.TimeUnit.SECONDS);
        if (response.statusCode() != 200) throw new Unavailable(response.statusCode());
        if (!response
            .headers()
            .firstValue("Content-Type")
            .orElse("")
            .toLowerCase(java.util.Locale.ROOT)
            .startsWith("application/json")) throw new Unavailable(0);
        return new String(response.body(), StandardCharsets.UTF_8);
      } finally {
        if (!pending.isDone()) pending.cancel(true);
      }
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new Unavailable(0);
    } catch (Unavailable e) {
      throw e;
    } catch (Exception e) {
      throw new Unavailable(0);
    }
  }
}
