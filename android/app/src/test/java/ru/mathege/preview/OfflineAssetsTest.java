package ru.mathege.preview;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import java.io.ByteArrayInputStream;
import java.io.FileNotFoundException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

public final class OfflineAssetsTest {
    @Test
    public void allowedRequestsReadOnlyTheirPackagedPathAndPreserveBytes() throws Exception {
        byte[] bytes = "Встроенный курс".getBytes(StandardCharsets.UTF_8);
        List<String> paths = new ArrayList<>();
        OfflineAssets assets = new OfflineAssets(path -> {
            paths.add(path);
            return new ByteArrayInputStream(bytes);
        });
        OfflineAssets.Response response = assets.respond(OfflineAssetPolicy.ENTRY, "GET");
        assertEquals(200, response.status);
        assertEquals("OK", response.reason);
        assertEquals("text/html", response.mimeType);
        assertEquals("UTF-8", response.encoding);
        assertEquals(OfflineAssetPolicy.headers(), response.headers);
        try (InputStream body = response.body) {
            assertArrayEquals(bytes, read(body));
        }
        assertEquals(1, paths.size());
        assertEquals("www/offline.html", paths.get(0));
    }

    @Test
    public void forbiddenRequestsNeverOpenFilesAndAlwaysReturnAResponse() throws Exception {
        OfflineAssets assets = new OfflineAssets(path -> { throw new AssertionError("Unexpected asset read"); });
        for (String url : new String[]{null, "file:///android_asset/www/offline.html", "https://evil.invalid/secret", OfflineAssetPolicy.ORIGIN + "/api/"}) {
            OfflineAssets.Response response = assets.respond(url, "GET");
            assertEquals(403, response.status);
            assertEquals("Forbidden", response.reason);
            assertEquals("text/plain", response.mimeType);
            assertEquals(OfflineAssetPolicy.headers(), response.headers);
            try (InputStream body = response.body) {
                assertTrue(read(body).length > 0);
            }
        }
        assertEquals(403, assets.respond(OfflineAssetPolicy.ENTRY, "POST").status);
    }

    @Test
    public void missingOrUnreadableAssetsDoNotFallThroughToTheNetwork() {
        OfflineAssets missing = new OfflineAssets(path -> { throw new FileNotFoundException(path); });
        OfflineAssets denied = new OfflineAssets(path -> { throw new SecurityException(); });
        for (OfflineAssets assets : new OfflineAssets[]{missing, denied, new OfflineAssets(path -> null)}) {
            OfflineAssets.Response response = assets.respond(OfflineAssetPolicy.ENTRY, "GET");
            assertEquals(404, response.status);
            assertEquals("Not Found", response.reason);
            assertEquals("text/plain", response.mimeType);
            assertEquals(OfflineAssetPolicy.headers(), response.headers);
            assertNotNull(response.body);
        }
    }

    private static byte[] read(InputStream body) throws Exception {
        java.io.ByteArrayOutputStream output = new java.io.ByteArrayOutputStream();
        byte[] buffer = new byte[256];
        int length;
        while ((length = body.read(buffer)) != -1) output.write(buffer, 0, length);
        return output.toByteArray();
    }
}
