import java.net.URI;
import java.net.http.*;
import java.time.Duration;

public class HttpHealthCheck {
  public static void main(String[] args) throws Exception {
    var client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();
    var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:8080/actuator/health/readiness"))
        .timeout(Duration.ofSeconds(3)).GET().build();
    if (client.send(request, HttpResponse.BodyHandlers.discarding()).statusCode() != 200)
      System.exit(1);
  }
}
