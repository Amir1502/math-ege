package ru.mathege.preview;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class OfflineAssetPolicyTest {
    @Test
    public void firstLaunchResolvesOnlyToTheBundledDocument() {
        OfflineAssetPolicy.Asset asset = OfflineAssetPolicy.asset(OfflineAssetPolicy.ENTRY, "GET");
        assertNotNull(asset);
        assertEquals("www/offline.html", asset.path);
        assertEquals("text/html", asset.mimeType);
        assertEquals("UTF-8", asset.encoding);
        assertTrue(OfflineAssetPolicy.navigation(OfflineAssetPolicy.ENTRY));
        assertTrue(OfflineAssetPolicy.navigation(OfflineAssetPolicy.ENTRY + "#/session/9ca266f0-c6e8-4557-b724-9318f1ffb646"));
    }

    @Test
    public void packagedTextFontsAndCourseHaveExplicitMediaTypes() {
        String base = OfflineAssetPolicy.ORIGIN + OfflineAssetPolicy.PREFIX;
        for (String name : new String[]{"profile", "lessons", "tasks", "manifest"}) {
            OfflineAssetPolicy.Asset asset = OfflineAssetPolicy.asset(base + "course/" + name + ".json", "GET");
            assertNotNull(asset);
            assertEquals("application/json", asset.mimeType);
            assertEquals("UTF-8", asset.encoding);
            assertFalse(OfflineAssetPolicy.navigation(base + "course/" + name + ".json"));
        }
        assertEquals("text/javascript", OfflineAssetPolicy.asset(base + "offline-compatibility.js", "GET").mimeType);
        assertEquals("text/javascript", OfflineAssetPolicy.asset(base + "assets/offline-A0_-.js", "GET").mimeType);
        assertEquals("text/css", OfflineAssetPolicy.asset(base + "assets/offline-A0_-.css", "GET").mimeType);
        assertEquals("image/svg+xml", OfflineAssetPolicy.asset(base + "assets/figure.svg", "GET").mimeType);
        assertEquals("font/woff2", OfflineAssetPolicy.asset(base + "assets/inter-cyrillic-400.woff2", "GET").mimeType);
        assertNull(OfflineAssetPolicy.asset(base + "assets/inter-cyrillic-400.woff2", "GET").encoding);
    }

    @Test
    public void everyResponseHasTheLocalScriptAndNetworkBoundary() {
        assertEquals("nosniff", OfflineAssetPolicy.headers().get("X-Content-Type-Options"));
        assertEquals("no-store", OfflineAssetPolicy.headers().get("Cache-Control"));
        assertEquals("no-referrer", OfflineAssetPolicy.headers().get("Referrer-Policy"));
        assertEquals("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'; worker-src 'none'; manifest-src 'none'", OfflineAssetPolicy.headers().get("Content-Security-Policy"));
    }
}
