package ru.mathege.preview;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;

final class OfflineAssetPolicy {
    static final String ORIGIN = "https://appassets.androidplatform.net";
    static final String PREFIX = "/assets/www/";
    static final String ENTRY = ORIGIN + PREFIX + "offline.html";
    private static final Pattern RESOURCE = Pattern.compile("assets/[A-Za-z0-9_-]+\\.(js|css|svg|png|woff2|woff|ttf)");
    private static final Map<String, String> HEADERS;

    static {
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("X-Content-Type-Options", "nosniff");
        headers.put("Cache-Control", "no-store");
        headers.put("Referrer-Policy", "no-referrer");
        headers.put("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; worker-src 'none'; manifest-src 'none'");
        HEADERS = Collections.unmodifiableMap(headers);
    }

    private OfflineAssetPolicy() {
    }

    static final class Asset {
        final String path;
        final String mimeType;
        final String encoding;

        private Asset(String name, String mimeType, String encoding) {
            this.path = "www/" + name;
            this.mimeType = mimeType;
            this.encoding = encoding;
        }
    }

    static Asset asset(String url, String method) {
        if (!"GET".equals(method) || url == null || url.length() > 4096) return null;
        for (int index = 0; index < url.length(); index++) {
            char value = url.charAt(index);
            if (value <= 32 || value == 127 || Character.isWhitespace(value)) return null;
        }
        URI uri;
        try {
            uri = new URI(url);
        } catch (URISyntaxException exception) {
            return null;
        }
        if (!"https".equals(uri.getScheme()) || !"appassets.androidplatform.net".equals(uri.getRawAuthority())
                || uri.getRawQuery() != null || uri.getRawPath() == null || !uri.getRawPath().startsWith(PREFIX)) return null;
        String name = uri.getRawPath().substring(PREFIX.length());
        if (name.equals("offline.html")) return new Asset(name, "text/html", "UTF-8");
        if (uri.getRawFragment() != null) return null;
        if (name.equals("offline-compatibility.js")) return new Asset(name, "text/javascript", "UTF-8");
        if (name.matches("course/(profile|lessons|tasks|manifest)\\.json")) return new Asset(name, "application/json", "UTF-8");
        if (!RESOURCE.matcher(name).matches()) return null;
        String extension = name.substring(name.lastIndexOf('.') + 1);
        switch (extension) {
            case "js": return new Asset(name, "text/javascript", "UTF-8");
            case "css": return new Asset(name, "text/css", "UTF-8");
            case "svg": return new Asset(name, "image/svg+xml", "UTF-8");
            case "png": return new Asset(name, "image/png", null);
            case "woff2": return new Asset(name, "font/woff2", null);
            case "woff": return new Asset(name, "font/woff", null);
            case "ttf": return new Asset(name, "font/ttf", null);
            default: return null;
        }
    }

    static boolean navigation(String url) {
        Asset asset = asset(url, "GET");
        return asset != null && asset.path.equals("www/offline.html");
    }

    static Map<String, String> headers() {
        return HEADERS;
    }
}
