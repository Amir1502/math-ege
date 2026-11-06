package ru.mathege.preview;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;

import java.util.Arrays;
import java.util.Collection;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.Parameterized;

@RunWith(Parameterized.class)
public final class OfflineAssetInvalidTest {
    @Parameterized.Parameters(name = "{index}: {0}")
    public static Collection<Object[]> cases() {
        String origin = "https://appassets.androidplatform.net";
        String base = origin + "/assets/www/";
        return Arrays.asList(new Object[][]{
                {null}, {""}, {"offline.html"}, {"//appassets.androidplatform.net/assets/www/offline.html"},
                {"http://appassets.androidplatform.net/assets/www/offline.html"},
                {"https://appassets.androidplatform.net.evil.invalid/assets/www/offline.html"},
                {"https://appassets.androidplatform.net@evil.invalid/assets/www/offline.html"},
                {"https://user@appassets.androidplatform.net/assets/www/offline.html"},
                {"https://appassets.androidplatform.net:443/assets/www/offline.html"},
                {"https://APPASSETS.androidplatform.net/assets/www/offline.html"},
                {"https://appassets.androidplatform.net./assets/www/offline.html"},
                {"file:///android_asset/www/offline.html"}, {"content://assets/www/offline.html"},
                {"javascript:alert(1)"}, {"data:text/html,hello"}, {"about:blank"},
                {base + "../offline.html"}, {base + "./offline.html"}, {base + "assets/../offline.html"},
                {base + "assets//offline.js"}, {base + "assets/%2e%2e/offline.html"},
                {base + "%2e%2e/offline.html"}, {base + "assets%2foffline.js"}, {base + "assets%5coffline.js"},
                {base + "%252e%252e/offline.html"}, {base + "offline.html?redirect=https://evil.invalid"},
                {base + "offline.html?"}, {base + "offline.html\n"}, {base + "offline.html\u0000"},
                {base + "assets\\offline.js"}, {base + "assets/offline.html"}, {base + ".env"},
                {base + "course/other.json"}, {base + "assets/other.json"}, {base + "assets/server.py"},
                {base + "course/tasks.json/"}, {origin + "/api/sessions"},
                {base + "offline.html#" + new String(new char[4097]).replace('\0', 'a')}
        });
    }

    private final String url;

    public OfflineAssetInvalidTest(String url) {
        this.url = url;
    }

    @Test
    public void requestsNeverFallThroughToNetworkOrOtherLocalFiles() {
        assertNull(OfflineAssetPolicy.asset(url, "GET"));
        assertFalse(OfflineAssetPolicy.navigation(url));
    }

    @Test
    public void mutationsAndMissingMethodsCannotReadAssets() {
        for (String method : new String[]{null, "", "POST", "PUT", "DELETE", "HEAD", "get"}) {
            assertNull(OfflineAssetPolicy.asset("https://appassets.androidplatform.net/assets/www/offline.html", method));
        }
    }
}
