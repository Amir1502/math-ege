package ru.mathege.preview;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;

final class OfflineAssets {
    interface AssetSource {
        InputStream open(String path) throws IOException;
    }

    static final class Response {
        final int status;
        final String reason;
        final String mimeType;
        final String encoding;
        final Map<String, String> headers;
        final InputStream body;

        private Response(int status, String reason, String mimeType, String encoding,
                         Map<String, String> headers, InputStream body) {
            this.status = status;
            this.reason = reason;
            this.mimeType = mimeType;
            this.encoding = encoding;
            this.headers = headers;
            this.body = body;
        }
    }

    private final AssetSource source;

    OfflineAssets(AssetSource source) {
        this.source = source;
    }

    Response respond(String url, String method) {
        OfflineAssetPolicy.Asset asset = OfflineAssetPolicy.asset(url, method);
        if (asset == null) return error(403, "Forbidden", "Доступ к этому адресу запрещён.");
        InputStream body;
        try {
            body = source.open(asset.path);
        } catch (IOException | SecurityException exception) {
            return error(404, "Not Found", "Ресурс отсутствует в пакете.");
        }
        if (body == null) return error(404, "Not Found", "Ресурс отсутствует в пакете.");
        return new Response(200, "OK", asset.mimeType, asset.encoding, OfflineAssetPolicy.headers(), body);
    }

    private static Response error(int status, String reason, String message) {
        return new Response(status, reason, "text/plain", "UTF-8", OfflineAssetPolicy.headers(),
            new ByteArrayInputStream(message.getBytes(StandardCharsets.UTF_8)));
    }
}