package ru.mathege.preview;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.IOException;

/** One WebView over packaged, allowlisted HTTPS assets; no server, network or bridge. */
public final class OfflineActivity extends Activity {
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        webView.setBackgroundColor(getColor(R.color.canvas));
        configure();
        setContentView(webView);
        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl(OfflineAssetPolicy.ENTRY);
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configure() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setBlockNetworkLoads(true);
        settings.setGeolocationEnabled(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        webView.setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> { });
        webView.setWebViewClient(new BundledClient(new OfflineAssets(this::openAsset)));
    }

    private java.io.InputStream openAsset(String path) throws IOException {
        return getAssets().open(path);
    }

    private final class BundledClient extends WebViewClient {
        private final OfflineAssets assets;

        BundledClient(OfflineAssets assets) {
            this.assets = assets;
        }

        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            return respond(request.getUrl().toString(), request.getMethod());
        }

        @Override
        @SuppressWarnings("deprecation")
        public WebResourceResponse shouldInterceptRequest(WebView view, String url) {
            return respond(url, "GET");
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            return !OfflineAssetPolicy.navigation(request.getUrl().toString());
        }

        @Override
        @SuppressWarnings("deprecation")
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            return !OfflineAssetPolicy.navigation(url);
        }

        private WebResourceResponse respond(String url, String method) {
            OfflineAssets.Response response = assets.respond(url, method);
            return new WebResourceResponse(response.mimeType, response.encoding, response.status,
                response.reason, new java.util.LinkedHashMap<>(response.headers), response.body);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        webView.saveState(outState);
    }

    @Override
    protected void onPause() {
        webView.onPause();
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        webView.onResume();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        webView.setWebViewClient(new WebViewClient());
        webView.destroy();
        super.onDestroy();
    }
}