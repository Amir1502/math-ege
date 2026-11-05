package ru.mathege.preview;

/** Browser continuity is a policy, not a preference for a particular vendor. */
public final class BrowserPolicy {
    private BrowserPolicy() {
    }

    public static boolean isDefaultBrowser(String packageName, boolean handlesAllWebData) {
        return packageName != null && !packageName.isEmpty() && handlesAllWebData;
    }

    public static boolean isGenericHttpsFilter(boolean handlesHttps, int authorityCount,
            int pathCount, int schemeSpecificPartCount) {
        return handlesHttps && authorityCount == 0 && pathCount == 0
                && schemeSpecificPartCount == 0;
    }

    public static boolean useCustomTabs(String defaultPackage, String customTabsPackage) {
        return defaultPackage != null && !defaultPackage.isEmpty()
                && defaultPackage.equals(customTabsPackage);
    }
}
