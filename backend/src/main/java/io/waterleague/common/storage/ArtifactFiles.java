package io.waterleague.common.storage;

import java.io.IOException;
import java.nio.channels.Channels;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Set;
import java.util.zip.GZIPInputStream;

public final class ArtifactFiles {
  private ArtifactFiles() {}

  public static byte[] read(Path path, int max) throws IOException {
    if (max <= 0 || max > 64 * 1024 * 1024 || !path.isAbsolute() || !path.normalize().equals(path)) {
      throw new IOException("ARTIFACT_PATH_INVALID");
    }
    try {
      return readFile(path, max, false);
    } catch (NoSuchFileException missing) {
      // 압축본을 먼저 게시하므로 정리 중 원문 경로가 사라져도 완성된 압축본을 읽는다.
      return readFile(path.resolveSibling(path.getFileName() + ".gz"), max, true);
    }
  }

  private static byte[] readFile(Path path, int max, boolean compressed) throws IOException {
    var attributes = Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
    if (!attributes.isRegularFile() || !path.toRealPath().equals(path)) {
      throw new IOException("ARTIFACT_FILE_INVALID");
    }
    try (var channel =
        Files.newByteChannel(path, Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
      if (channel.size() > max + (compressed ? 1024L * 1024 : 0)) {
        throw new IOException("ARTIFACT_SIZE_EXCEEDED");
      }
      var raw = Channels.newInputStream(channel);
      try (var input = compressed ? new GZIPInputStream(raw) : raw) {
        var bytes = input.readNBytes(max + 1);
        if (bytes.length > max) throw new IOException("ARTIFACT_SIZE_EXCEEDED");
        return bytes;
      }
    }
  }
}
