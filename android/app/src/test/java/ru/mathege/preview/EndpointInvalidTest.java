package ru.mathege.preview;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.Parameterized;

import java.util.Arrays;
import java.util.Collection;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.fail;

@RunWith(Parameterized.class)
public final class EndpointInvalidTest {
    @Parameterized.Parameters(name = "{index}: {1}")
    public static Collection<Object[]> cases() {
        return Arrays.asList(new Object[][] {
                {null, Endpoint.Error.EMPTY},
                {"   ", Endpoint.Error.EMPTY},
                {"http://example.test", Endpoint.Error.HTTPS_REQUIRED},
                {"example.test", Endpoint.Error.HTTPS_REQUIRED},
                {"https:example.test", Endpoint.Error.HTTPS_REQUIRED},
                {"https:///", Endpoint.Error.INVALID_HOST},
                {"https://user:fixture@example.test", Endpoint.Error.CREDENTIALS},
                {"https://@example.test", Endpoint.Error.CREDENTIALS},
                {"https://example.test?", Endpoint.Error.QUERY},
                {"https://example.test/?token=fixture", Endpoint.Error.QUERY},
                {"https://example.test#", Endpoint.Error.FRAGMENT},
                {"https://example.test/#fixture", Endpoint.Error.FRAGMENT},
                {"https://example.test/login/fixture", Endpoint.Error.PATH},
                {"https://example.test/%2f", Endpoint.Error.PATH},
                {"https://example.test//", Endpoint.Error.PATH},
                {"https://example.test:", Endpoint.Error.INVALID_PORT},
                {"https://example.test:0", Endpoint.Error.INVALID_PORT},
                {"https://example.test:65536", Endpoint.Error.INVALID_PORT},
                {"https://example.test:+443", Endpoint.Error.INVALID_PORT},
                {"https://example.test:fixture", Endpoint.Error.INVALID_PORT},
                {"https://-example.test", Endpoint.Error.INVALID_HOST},
                {"https://example-.test", Endpoint.Error.INVALID_HOST},
                {"https://example..test", Endpoint.Error.INVALID_HOST},
                {"https://example_test", Endpoint.Error.INVALID_HOST},
                {"https://example.test.", Endpoint.Error.INVALID_HOST},
                {"https://%65xample.test", Endpoint.Error.INVALID_HOST},
                {"https://example%40fixture.test", Endpoint.Error.INVALID_HOST},
                {"https://127.1", Endpoint.Error.INVALID_HOST},
                {"https://2130706433", Endpoint.Error.INVALID_HOST},
                {"https://0177.0.0.1", Endpoint.Error.INVALID_HOST},
                {"https://0x7f000001", Endpoint.Error.INVALID_HOST},
                {"https://192.0.2.256", Endpoint.Error.INVALID_HOST},
                {"https://example.123", Endpoint.Error.INVALID_HOST},
                {"https://[::1%25lo0]", Endpoint.Error.INVALID_HOST},
                {"https://2001:db8::1", Endpoint.Error.INVALID_HOST},
                {"https://example.test\\fixture", Endpoint.Error.INVALID_FORMAT},
                {"https://exam ple.test", Endpoint.Error.INVALID_FORMAT},
                {"https://example.test\n", Endpoint.Error.INVALID_FORMAT},
                {"\thttps://example.test", Endpoint.Error.INVALID_FORMAT},
                {"https://exam\u202eple.test", Endpoint.Error.INVALID_FORMAT},
                {"https://exam\u00a0ple.test", Endpoint.Error.INVALID_FORMAT},
                {"https://" + repeat('a', 64) + ".test", Endpoint.Error.INVALID_HOST},
                {"https://" + repeat('a', Endpoint.MAX_INPUT_LENGTH), Endpoint.Error.TOO_LONG}
        });
    }

    private final String input;
    private final Endpoint.Error expected;

    public EndpointInvalidTest(String input, Endpoint.Error expected) {
        this.input = input;
        this.expected = expected;
    }

    @Test
    public void rejectsUnsafeConfigurationWithoutEchoingTheInput() throws Exception {
        try {
            Endpoint.parse(input);
            fail("Unsafe endpoint was accepted");
        } catch (Endpoint.ValidationException exception) {
            assertEquals(expected, exception.getError());
            assertEquals(expected.name(), exception.getMessage());
            assertFalse(exception.getMessage().contains("fixture"));
        }
    }

    private static String repeat(char value, int count) {
        char[] characters = new char[count];
        Arrays.fill(characters, value);
        return new String(characters);
    }
}
