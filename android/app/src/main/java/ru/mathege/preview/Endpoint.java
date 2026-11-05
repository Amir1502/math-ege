package ru.mathege.preview;

import java.net.IDN;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** Validates configuration as an HTTPS origin without making DNS/network calls. */
public final class Endpoint {
    public static final int MAX_INPUT_LENGTH = 2048;

    public enum Error {
        EMPTY,
        TOO_LONG,
        HTTPS_REQUIRED,
        INVALID_FORMAT,
        INVALID_HOST,
        INVALID_PORT,
        CREDENTIALS,
        PATH,
        QUERY,
        FRAGMENT
    }

    public static final class ValidationException extends Exception {
        private static final long serialVersionUID = 1L;
        private final Error error;

        private ValidationException(Error error) {
            // Never put the untrusted input or a possible pasted token in an exception.
            super(error.name());
            this.error = error;
        }

        public Error getError() {
            return error;
        }
    }

    private Endpoint() {
    }

    public static String parse(String input) throws ValidationException {
        if (input == null) {
            throw invalid(Error.EMPTY);
        }
        if (input.length() > MAX_INPUT_LENGTH) {
            throw invalid(Error.TOO_LONG);
        }
        // Ordinary surrounding spaces are harmless; controls, newlines and bidi
        // formatting characters are not silently trimmed or normalized away.
        int start = 0;
        int end = input.length();
        while (start < end && input.charAt(start) == ' ') {
            start++;
        }
        while (end > start && input.charAt(end - 1) == ' ') {
            end--;
        }
        String value = input.substring(start, end);
        if (value.isEmpty()) {
            throw invalid(Error.EMPTY);
        }
        if (hasForbiddenCharacters(value) || value.indexOf('\\') >= 0) {
            throw invalid(Error.INVALID_FORMAT);
        }

        URI uri;
        try {
            uri = new URI(value);
        } catch (URISyntaxException exception) {
            throw invalid(Error.INVALID_FORMAT);
        }
        if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.isOpaque()) {
            throw invalid(Error.HTTPS_REQUIRED);
        }
        String authority = uri.getRawAuthority();
        if (authority == null || authority.isEmpty()) {
            throw invalid(Error.INVALID_HOST);
        }
        if (uri.getRawUserInfo() != null || authority.indexOf('@') >= 0) {
            throw invalid(Error.CREDENTIALS);
        }
        if (uri.getRawQuery() != null) {
            throw invalid(Error.QUERY);
        }
        if (uri.getRawFragment() != null) {
            throw invalid(Error.FRAGMENT);
        }
        String path = uri.getRawPath();
        if (path != null && !path.isEmpty() && !"/".equals(path)) {
            // An origin, not a login/export/API URL, is the configuration unit.
            throw invalid(Error.PATH);
        }
        if (authority.indexOf('%') >= 0) {
            throw invalid(Error.INVALID_HOST);
        }

        String host;
        String portText = null;
        if (authority.startsWith("[")) {
            int close = authority.indexOf(']');
            if (close < 0) {
                throw invalid(Error.INVALID_HOST);
            }
            host = authority.substring(0, close + 1).toLowerCase(Locale.ROOT);
            String suffix = authority.substring(close + 1);
            if (!suffix.isEmpty()) {
                if (!suffix.startsWith(":")) {
                    throw invalid(Error.INVALID_HOST);
                }
                portText = suffix.substring(1);
            }
            validateIpv6(host);
        } else {
            int colon = authority.lastIndexOf(':');
            if (colon >= 0) {
                if (colon != authority.indexOf(':')) {
                    throw invalid(Error.INVALID_HOST);
                }
                portText = authority.substring(colon + 1);
                authority = authority.substring(0, colon);
            }
            host = normalizeDnsOrIpv4(authority);
        }

        int port = parsePort(portText);
        String origin = "https://" + host + (port == -1 || port == 443 ? "" : ":" + port);
        try {
            if (new URI(origin).parseServerAuthority().getHost() == null) {
                throw invalid(Error.INVALID_HOST);
            }
        } catch (URISyntaxException exception) {
            throw invalid(Error.INVALID_HOST);
        }
        return origin;
    }

    private static String normalizeDnsOrIpv4(String host) throws ValidationException {
        if (host.isEmpty() || host.indexOf('[') >= 0 || host.indexOf(']') >= 0) {
            throw invalid(Error.INVALID_HOST);
        }
        String ascii;
        try {
            ascii = IDN.toASCII(host, IDN.USE_STD3_ASCII_RULES).toLowerCase(Locale.ROOT);
        } catch (IllegalArgumentException exception) {
            throw invalid(Error.INVALID_HOST);
        }
        if (ascii.isEmpty() || ascii.length() > 253) {
            throw invalid(Error.INVALID_HOST);
        }
        String[] labels = ascii.split("\\.", -1);
        for (String label : labels) {
            if (!label.matches("[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")) {
                throw invalid(Error.INVALID_HOST);
            }
            if (label.startsWith("xn--")) {
                String unicode = IDN.toUnicode(label);
                if (unicode.equals(label) || hasForbiddenCharacters(unicode)) {
                    throw invalid(Error.INVALID_HOST);
                }
            }
        }
        String lastLabel = labels[labels.length - 1];
        if (lastLabel.matches("[0-9]+") || lastLabel.matches("0x[0-9a-f]*")) {
            // Browsers treat numeric-ending hosts as IPv4. Reject integer,
            // hexadecimal, octal and short forms so the displayed origin cannot
            // conceal a different IP address after browser normalization.
            if (!isCanonicalIpv4(ascii)) {
                throw invalid(Error.INVALID_HOST);
            }
        }
        return ascii;
    }

    private static void validateIpv6(String host) throws ValidationException {
        try {
            if (host.indexOf(':') < 0 || new URI("https://" + host).parseServerAuthority().getHost() == null) {
                throw invalid(Error.INVALID_HOST);
            }
        } catch (URISyntaxException exception) {
            throw invalid(Error.INVALID_HOST);
        }
        if (host.indexOf('.') >= 0) {
            String ipv4 = host.substring(host.lastIndexOf(':') + 1, host.length() - 1);
            if (!isCanonicalIpv4(ipv4)) {
                throw invalid(Error.INVALID_HOST);
            }
        }
    }

    private static boolean isCanonicalIpv4(String host) {
        String[] octets = host.split("\\.", -1);
        if (octets.length != 4) {
            return false;
        }
        for (String octet : octets) {
            if (!octet.matches("[0-9]{1,3}") || (octet.length() > 1 && octet.startsWith("0"))) {
                return false;
            }
            if (Integer.parseInt(octet) > 255) {
                return false;
            }
        }
        return true;
    }

    private static int parsePort(String value) throws ValidationException {
        if (value == null) {
            return -1;
        }
        if (!value.matches("[0-9]{1,5}")) {
            throw invalid(Error.INVALID_PORT);
        }
        int port = Integer.parseInt(value);
        if (port < 1 || port > 65535) {
            throw invalid(Error.INVALID_PORT);
        }
        return port;
    }

    private static boolean hasForbiddenCharacters(String value) {
        for (int offset = 0; offset < value.length();) {
            int point = value.codePointAt(offset);
            if (Character.isISOControl(point) || Character.isWhitespace(point)
                    || Character.isSpaceChar(point) || Character.getType(point) == Character.FORMAT) {
                return true;
            }
            offset += Character.charCount(point);
        }
        return false;
    }

    private static ValidationException invalid(Error error) {
        return new ValidationException(error);
    }
}
