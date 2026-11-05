package ru.mathege.preview;

import android.app.Activity;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

/** One native configuration screen. Browser sessions and web data stay outside it. */
public final class MainActivity extends Activity {
    private static final String PREFERENCES = "preview_configuration";
    private static final String ENDPOINT_KEY = "https_origin";
    private static final String STATE_EDITING = "editing_configuration";

    private SharedPreferences preferences;
    private String origin;
    private boolean editing;
    private View formGroup;
    private View readyGroup;
    private LinearLayout content;
    private EditText endpointField;
    private TextView fieldError;
    private TextView originValue;
    private TextView browserError;
    private Button cancelButton;
    private Button openButton;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        setContentView(R.layout.activity_main);

        content = findViewById(R.id.content);
        formGroup = findViewById(R.id.configuration_group);
        readyGroup = findViewById(R.id.ready_group);
        endpointField = findViewById(R.id.endpoint_input);
        fieldError = findViewById(R.id.endpoint_error);
        originValue = findViewById(R.id.endpoint_value);
        browserError = findViewById(R.id.browser_error);
        cancelButton = findViewById(R.id.cancel_button);
        openButton = findViewById(R.id.open_button);

        configureInsets();
        configureAccessibility();
        configureInput();

        preferences = getSharedPreferences(PREFERENCES, MODE_PRIVATE);
        origin = readValidatedOrigin();
        boolean restoreEditing = savedInstanceState != null
                && savedInstanceState.getBoolean(STATE_EDITING, false);
        showScreen(origin == null || restoreEditing, false);

        findViewById(R.id.save_button).setOnClickListener(view -> saveOrigin());
        findViewById(R.id.change_button).setOnClickListener(view -> showScreen(true, true));
        cancelButton.setOnClickListener(view -> showScreen(false, true));
        openButton.setOnClickListener(view -> openBrowser());
    }

    private void configureInsets() {
        ScrollView scroll = findViewById(R.id.preview_scroll);
        WindowInsetsControllerCompat controller = WindowCompat.getInsetsController(
                getWindow(), getWindow().getDecorView());
        controller.setAppearanceLightStatusBars(true);
        // API 23-26 use the base graphite navigation-bar theme and light icons.
        controller.setAppearanceLightNavigationBars(Build.VERSION.SDK_INT >= 27);

        ViewCompat.setOnApplyWindowInsetsListener(scroll, (view, windowInsets) -> {
            Insets insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars()
                    | WindowInsetsCompat.Type.displayCutout() | WindowInsetsCompat.Type.ime());
            view.setPadding(insets.left, insets.top, insets.right, insets.bottom);
            return windowInsets;
        });
        scroll.addOnLayoutChangeListener((view, left, top, right, bottom,
                oldLeft, oldTop, oldRight, oldBottom) -> {
            int available = view.getWidth() - view.getPaddingLeft() - view.getPaddingRight();
            int maximum = getResources().getDimensionPixelSize(R.dimen.content_max_width);
            int width = Math.min(available, maximum);
            ScrollView.LayoutParams params = (ScrollView.LayoutParams) content.getLayoutParams();
            if (width > 0 && params.width != width) {
                params.width = width;
                params.gravity = Gravity.CENTER_HORIZONTAL;
                content.setLayoutParams(params);
            }
        });
        ViewCompat.requestApplyInsets(scroll);
    }

    private void configureAccessibility() {
        ViewCompat.setAccessibilityHeading(findViewById(R.id.product_heading), true);
        ViewCompat.setAccessibilityHeading(findViewById(R.id.configuration_heading), true);
        ViewCompat.setAccessibilityHeading(findViewById(R.id.ready_heading), true);
        ViewCompat.setAccessibilityPaneTitle(formGroup, getString(R.string.configuration_heading));
        ViewCompat.setAccessibilityPaneTitle(readyGroup, getString(R.string.ready_heading));
    }

    private void configureInput() {
        // A pasted login URL must not become an Activity-state/autofill draft.
        endpointField.setSaveEnabled(false);
        endpointField.setSaveFromParentEnabled(false);
        if (Build.VERSION.SDK_INT >= 26) {
            endpointField.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
            endpointField.setImeOptions(endpointField.getImeOptions()
                    | EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING);
        }
        endpointField.setOnEditorActionListener((view, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                saveOrigin();
                return true;
            }
            return false;
        });
        endpointField.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence text, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence text, int start, int before, int count) {
                clearFieldError();
            }

            @Override
            public void afterTextChanged(Editable text) {
            }
        });
    }

    private String readValidatedOrigin() {
        String stored;
        try {
            stored = preferences.getString(ENDPOINT_KEY, null);
        } catch (ClassCastException exception) {
            preferences.edit().remove(ENDPOINT_KEY).apply();
            return null;
        }
        if (stored == null) {
            return null;
        }
        try {
            String validated = Endpoint.parse(stored);
            if (!validated.equals(stored)) {
                preferences.edit().putString(ENDPOINT_KEY, validated).apply();
            }
            return validated;
        } catch (Endpoint.ValidationException exception) {
            // Only this launcher's own invalid configuration key is removed.
            preferences.edit().remove(ENDPOINT_KEY).apply();
            return null;
        }
    }

    private void saveOrigin() {
        try {
            String validated = Endpoint.parse(endpointField.getText().toString());
            preferences.edit().putString(ENDPOINT_KEY, validated).apply();
            origin = validated;
            // Saving is separate from launching: the canonical address is shown first.
            showScreen(false, true);
        } catch (Endpoint.ValidationException exception) {
            String message = getString(errorMessage(exception.getError()));
            endpointField.setBackgroundResource(R.drawable.endpoint_field_error);
            endpointField.setError(message);
            fieldError.setText(message);
            fieldError.setVisibility(View.VISIBLE);
            endpointField.requestFocus();
        }
    }

    private void showScreen(boolean showConfiguration, boolean moveFocus) {
        editing = showConfiguration || origin == null;
        clearFieldError();
        browserError.setText(null);
        browserError.setVisibility(View.GONE);
        // Unsaved input is never restored. A change starts from validated configuration.
        endpointField.setText(editing && origin != null ? origin : "");
        endpointField.setSelection(endpointField.length());
        originValue.setText(origin == null ? "" : origin);
        formGroup.setVisibility(editing ? View.VISIBLE : View.GONE);
        readyGroup.setVisibility(editing ? View.GONE : View.VISIBLE);
        cancelButton.setVisibility(origin == null ? View.GONE : View.VISIBLE);
        content.requestFocus();
        hideKeyboard();
        if (moveFocus) {
            if (editing) {
                endpointField.requestFocus();
            } else {
                openButton.requestFocus();
            }
        }
    }

    private void clearFieldError() {
        endpointField.setError(null);
        endpointField.setBackgroundResource(R.drawable.endpoint_field);
        fieldError.setText(null);
        fieldError.setVisibility(View.GONE);
    }

    private void hideKeyboard() {
        InputMethodManager keyboard = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
        if (keyboard != null) {
            keyboard.hideSoftInputFromWindow(endpointField.getWindowToken(), 0);
        }
    }

    private void openBrowser() {
        if (origin == null) {
            showScreen(true, true);
            return;
        }
        browserError.setText(null);
        browserError.setVisibility(View.GONE);
        BrowserLauncher.Result result = BrowserLauncher.open(this, origin);
        if (result != BrowserLauncher.Result.OPENED) {
            browserError.setText(result == BrowserLauncher.Result.NO_DEFAULT_BROWSER
                    ? R.string.error_no_default_browser : R.string.error_browser_unavailable);
            browserError.setVisibility(View.VISIBLE);
        }
    }

    private static int errorMessage(Endpoint.Error error) {
        switch (error) {
            case EMPTY:
                return R.string.error_endpoint_empty;
            case TOO_LONG:
                return R.string.error_endpoint_too_long;
            case HTTPS_REQUIRED:
                return R.string.error_endpoint_https;
            case INVALID_HOST:
                return R.string.error_endpoint_host;
            case INVALID_PORT:
                return R.string.error_endpoint_port;
            case CREDENTIALS:
                return R.string.error_endpoint_credentials;
            case PATH:
                return R.string.error_endpoint_path;
            case QUERY:
                return R.string.error_endpoint_query;
            case FRAGMENT:
                return R.string.error_endpoint_fragment;
            case INVALID_FORMAT:
            default:
                return R.string.error_endpoint_format;
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        // Restore only the screen choice, never the field or any error containing input.
        outState.putBoolean(STATE_EDITING, editing && origin != null);
        super.onSaveInstanceState(outState);
    }
}
