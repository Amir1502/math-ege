package ru.mathege.preview;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;

import androidx.browser.customtabs.CustomTabColorSchemeParams;
import androidx.browser.customtabs.CustomTabsClient;
import androidx.browser.customtabs.CustomTabsIntent;

import java.util.Collections;

/** The shell dispatches an origin; the browser owns all network and session data. */
public final class BrowserLauncher {
    public enum Result {
        OPENED,
        NO_DEFAULT_BROWSER,
        UNAVAILABLE
    }

    private BrowserLauncher() {
    }

    public static Result open(Activity activity, String origin) {
        PackageManager manager = activity.getPackageManager();
        // A scheme-only intent selects a browser, not a domain's App Link owner.
        // This is a package query, not a request to an invented live endpoint.
        Intent browserProbe = new Intent(Intent.ACTION_VIEW, Uri.parse("https://"));
        browserProbe.addCategory(Intent.CATEGORY_BROWSABLE);
        ResolveInfo defaultHandler;
        try {
            defaultHandler = manager.resolveActivity(browserProbe,
                    PackageManager.MATCH_DEFAULT_ONLY | PackageManager.GET_RESOLVED_FILTER);
        } catch (SecurityException exception) {
            return Result.UNAVAILABLE;
        }
        String defaultPackage = defaultHandler == null || defaultHandler.activityInfo == null
                ? null : defaultHandler.activityInfo.packageName;
        // Use the public SDK filter, not ResolveInfo's hidden browser flag.
        // Missing/restricted filters (including a resolver) fail closed.
        IntentFilter filter = defaultHandler == null ? null : defaultHandler.filter;
        boolean genericHttps = filter != null && BrowserPolicy.isGenericHttpsFilter(
                filter.hasDataScheme("https"), filter.countDataAuthorities(),
                filter.countDataPaths(), filter.countDataSchemeSpecificParts());
        if (!BrowserPolicy.isDefaultBrowser(defaultPackage, genericHttps)) {
            // Do not pick the first installed browser when Android has no default.
            return Result.NO_DEFAULT_BROWSER;
        }

        Uri uri = Uri.parse(origin);
        String customTabsPackage = null;
        try {
            // The empty candidate list intentionally forbids vendor fallback.
            customTabsPackage = CustomTabsClient.getPackageName(activity, Collections.emptyList());
        } catch (SecurityException exception) {
            // The already-selected default package is still the only fallback.
        }
        if (BrowserPolicy.useCustomTabs(defaultPackage, customTabsPackage)) {
            CustomTabColorSchemeParams colors = new CustomTabColorSchemeParams.Builder()
                    .setToolbarColor(activity.getColor(R.color.surface))
                    .build();
            CustomTabsIntent tab = new CustomTabsIntent.Builder()
                    .setDefaultColorSchemeParams(colors)
                    .setShowTitle(true)
                    .setUrlBarHidingEnabled(false)
                    .setEphemeralBrowsingEnabled(false)
                    .build();
            tab.intent.setPackage(defaultPackage);
            try {
                tab.launchUrl(activity, uri);
                return Result.OPENED;
            } catch (ActivityNotFoundException | SecurityException exception) {
                // Fall through only to an ordinary window of this same package.
            }
        }

        Intent fallback = new Intent(Intent.ACTION_VIEW, uri);
        fallback.addCategory(Intent.CATEGORY_BROWSABLE);
        fallback.setPackage(defaultPackage);
        try {
            activity.startActivity(fallback);
            return Result.OPENED;
        } catch (ActivityNotFoundException | SecurityException exception) {
            return Result.UNAVAILABLE;
        }
    }
}
