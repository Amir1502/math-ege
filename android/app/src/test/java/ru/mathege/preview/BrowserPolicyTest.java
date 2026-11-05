package ru.mathege.preview;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public final class BrowserPolicyTest {
    @Test
    public void permitsCustomTabsOnlyForTheChosenDefaultPackage() {
        assertTrue(BrowserPolicy.useCustomTabs("default.browser", "default.browser"));
    }

    @Test
    public void doesNotSilentlySwitchToChromeOrAnotherProvider() {
        assertFalse(BrowserPolicy.useCustomTabs("default.browser", "com.android.chrome"));
        assertFalse(BrowserPolicy.useCustomTabs("default.browser", "other.browser"));
    }

    @Test
    public void usesOrdinaryDefaultBrowserWhenCustomTabsIsMissing() {
        assertFalse(BrowserPolicy.useCustomTabs("default.browser", null));
    }

    @Test
    public void doesNotChooseAnArbitraryProviderWithoutADefault() {
        assertFalse(BrowserPolicy.useCustomTabs(null, "com.android.chrome"));
        assertFalse(BrowserPolicy.useCustomTabs("", ""));
    }

    @Test
    public void rejectsResolverAndDomainAppInsteadOfCallingThemABrowser() {
        assertFalse(BrowserPolicy.isDefaultBrowser("android", false));
        assertFalse(BrowserPolicy.isDefaultBrowser("domain.app", false));
    }

    @Test
    public void requiresAnActualBrowserPackage() {
        assertFalse(BrowserPolicy.isDefaultBrowser(null, true));
        assertFalse(BrowserPolicy.isDefaultBrowser("", true));
        assertTrue(BrowserPolicy.isDefaultBrowser("default.browser", true));
    }

    @Test
    public void acceptsAnUnrestrictedHttpsBrowserFilter() {
        assertTrue(BrowserPolicy.isGenericHttpsFilter(true, 0, 0, 0));
    }

    @Test
    public void rejectsAFilterWithoutHttps() {
        assertFalse(BrowserPolicy.isGenericHttpsFilter(false, 0, 0, 0));
    }

    @Test
    public void rejectsHostAndPathRestrictedAppLinkFilters() {
        assertFalse(BrowserPolicy.isGenericHttpsFilter(true, 1, 0, 0));
        assertFalse(BrowserPolicy.isGenericHttpsFilter(true, 0, 1, 0));
    }

    @Test
    public void rejectsSchemeSpecificAndMissingFilterDescriptors() {
        assertFalse(BrowserPolicy.isGenericHttpsFilter(true, 0, 0, 1));
        assertFalse(BrowserPolicy.isGenericHttpsFilter(true, -1, -1, -1));
    }
}
