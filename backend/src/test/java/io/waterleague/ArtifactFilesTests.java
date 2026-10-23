package io.waterleague;

import static org.assertj.core.api.Assertions.*;

import io.waterleague.common.storage.ArtifactFiles;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.GZIPOutputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ArtifactFilesTests {
  @TempDir Path temporary;

  private Path gzip(String name, byte[] raw) throws Exception {
    var path = temporary.toRealPath().resolve(name + ".gz");
    try (var output = new GZIPOutputStream(Files.newOutputStream(path))) {
      output.write(raw);
    }
    return path;
  }

  @Test
  void plainAndCompressedPreserveExactOriginalBytes() throws Exception {
    var raw = "{\"score\":-0.00000000001}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    var file = temporary.toRealPath().resolve("result.json");
    Files.write(file, raw);
    assertThat(ArtifactFiles.read(file, 1024)).isEqualTo(raw);
    gzip("result.json", raw);
    Files.delete(file);
    assertThat(ArtifactFiles.read(file, 1024)).isEqualTo(raw);
  }

  @Test
  void expandedSizeAndTruncatedGzipAreRejected() throws Exception {
    gzip("large.json", new byte[1024 * 1024]);
    var file = temporary.toRealPath().resolve("large.json");
    assertThatThrownBy(() -> ArtifactFiles.read(file, 1024)).isInstanceOf(IOException.class);
    Files.write(file.resolveSibling("large.json.gz"), new byte[] {31, -117, 8});
    assertThatThrownBy(() -> ArtifactFiles.read(file, 1024)).isInstanceOf(IOException.class);
  }

  @Test
  void originalAndCompressedSymlinksAreRejected() throws Exception {
    var directory = temporary.toRealPath();
    var source = Files.writeString(directory.resolve("source"), "private");
    var plain = directory.resolve("result.json");
    Files.createSymbolicLink(plain, source);
    assertThatThrownBy(() -> ArtifactFiles.read(plain, 1024)).isInstanceOf(IOException.class);
    Files.delete(plain);
    Files.createSymbolicLink(directory.resolve("result.json.gz"), source);
    assertThatThrownBy(() -> ArtifactFiles.read(plain, 1024)).isInstanceOf(IOException.class);
  }

  @Test
  void plainFileRemainsPreferredDuringCompressionPublication() throws Exception {
    var file = temporary.toRealPath().resolve("result.json");
    Files.writeString(file, "original");
    gzip("result.json", "compressed".getBytes());
    assertThat(ArtifactFiles.read(file, 1024)).isEqualTo("original".getBytes());
  }
}
