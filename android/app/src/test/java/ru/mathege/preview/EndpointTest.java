package ru.mathege.preview;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public final class EndpointTest {
    @Test
    public void acceptsAnHttpsDnsOrigin() throws Exception {
        assertEquals("https://example.test", Endpoint.parse("https://example.test"));
    }

    @Test
    public void canonicalizesCaseDefaultPortAndRootSlash() throws Exception {
        assertEquals("https://example.test", Endpoint.parse(" HTTPS://EXAMPLE.TEST:443/ "));
    }

    @Test
    public void keepsANonDefaultPort() throws Exception {
        assertEquals("https://example.test:8443", Endpoint.parse("https://example.test:08443/"));
    }

    @Test
    public void acceptsPortBounds() throws Exception {
        assertEquals("https://example.test:1", Endpoint.parse("https://example.test:1"));
        assertEquals("https://example.test:65535", Endpoint.parse("https://example.test:65535"));
    }

    @Test
    public void showsIdnAsAsciiBeforeOpening() throws Exception {
        assertEquals("https://xn--e1afmkfd.test", Endpoint.parse("https://пример.test/"));
        assertEquals("https://xn--e1afmkfd.test", Endpoint.parse("https://xn--e1afmkfd.test"));
    }

    @Test
    public void acceptsCanonicalIpv4WithoutNetworkResolution() throws Exception {
        assertEquals("https://192.0.2.1:8443", Endpoint.parse("https://192.0.2.1:8443"));
    }

    @Test
    public void acceptsAnIpv6Literal() throws Exception {
        assertEquals("https://[2001:db8::1]", Endpoint.parse("https://[2001:DB8::1]/"));
        assertEquals("https://[::1]:8443", Endpoint.parse("https://[::1]:8443"));
    }

    @Test
    public void acceptsCanonicalIpv4EmbeddedInIpv6() throws Exception {
        assertEquals("https://[::ffff:192.0.2.1]", Endpoint.parse("https://[::ffff:192.0.2.1]"));
    }

    @Test
    public void acceptsAnExplicitSingleLabelHost() throws Exception {
        assertEquals("https://localhost:8443", Endpoint.parse("https://localhost:8443"));
    }
}
