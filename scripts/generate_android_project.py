import os

TARGET_DIR = r"E:\Balaji_Workforce_System\balaji-workforce-android"

files = {}

# 1. local.properties
files["local.properties"] = """sdk.dir=C\\:\\\\Users\\\\darsh\\\\AppData\\\\Local\\\\Android\\\\Sdk
"""

# 2. gradle.properties
files["gradle.properties"] = """# JVM arguments and modern Android settings
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.useAndroidX=true
android.enableJetifier=true
android.nonTransitiveRClass=true

# Force Gradle to compile using Java 17 Temurin LTS
org.gradle.java.home=C:/Program Files/Eclipse Adoptium/jdk-17.0.20.101-hotspot
"""

# 3. gradle-wrapper.properties
files[os.path.join("gradle", "wrapper", "gradle-wrapper.properties")] = """distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.9-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
"""

# 4. settings.gradle.kts
files["settings.gradle.kts"] = """pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\\\.android.*")
                includeGroupByRegex("com\\\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "BalajiWorkforce"
include(":app")
"""

# 5. Root build.gradle.kts
files["build.gradle.kts"] = """plugins {
    id("com.android.application") version "8.6.0" apply false
    id("org.jetbrains.kotlin.android") version "2.0.20" apply false
}
"""

# 6. app/build.gradle.kts
files[os.path.join("app", "build.gradle.kts")] = """plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.balaji.workforce"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.balaji.workforce"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            isMinifyEnabled = false
            isDebuggable = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("androidx.activity:activity-ktx:1.9.2")
}
"""

# 7. app/proguard-rules.pro
files[os.path.join("app", "proguard-rules.pro")] = """# Balaji Workforce Android WebView Proguard Rules
-keepattributes JavascriptInterface
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
"""

# 8. AndroidManifest.xml
files[os.path.join("app", "src", "main", "AndroidManifest.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">

    <!-- Permissions required for WebView and GPS Attendance -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" android:maxSdkVersion="32" />

    <uses-feature android:name="android.hardware.location.gps" android:required="false" />
    <uses-feature android:name="android.hardware.camera" android:required="false" />

    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:roundIcon="@mipmap/ic_launcher_round"
        android:supportsRtl="true"
        android:theme="@style/Theme.BalajiWorkforce"
        android:usesCleartextTraffic="true"
        android:networkSecurityConfig="@xml/network_security_config"
        tools:targetApi="35">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:configChanges="orientation|screenSize|keyboardHidden"
            android:windowSoftInputMode="adjustResize">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <!-- Provider for sharing downloaded Excel reports -->
        <provider
            android:name="androidx.core.content.FileProvider"
            android:authorities="${applicationId}.fileprovider"
            android:exported="false"
            android:grantUriPermissions="true">
            <meta-data
                android:name="android.support.FILE_PROVIDER_PATHS"
                android:resource="@xml/file_paths" />
        </provider>

    </application>

</manifest>
"""

# 9. network_security_config.xml
files[os.path.join("app", "src", "main", "res", "xml", "network_security_config.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <!-- Allow cleartext HTTP connections for localhost, 10.0.2.2, and local LAN IPs -->
    <base-config cleartextTrafficPermitted="true">
        <trust-anchors>
            <certificates src="system" />
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>
"""

# 10. file_paths.xml
files[os.path.join("app", "src", "main", "res", "xml", "file_paths.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<paths>
    <external-path name="external_files" path="." />
    <external-files-path name="external_files_path" path="." />
    <files-path name="files" path="." />
    <cache-path name="cache" path="." />
    <external-cache-path name="external_cache" path="." />
</paths>
"""

# 11. values/strings.xml
files[os.path.join("app", "src", "main", "res", "values", "strings.xml")] = """<resources>
    <string name="app_name">Balaji Workforce</string>
    <string name="action_settings">Server Settings</string>
    <string name="action_refresh">Refresh Page</string>
    <string name="server_settings_title">Backend Server Configuration</string>
    <string name="server_url_hint">e.g. http://10.0.2.2:5000 or http://localhost:5000</string>
    <string name="btn_save">Connect &amp; Save</string>
    <string name="btn_cancel">Cancel</string>
    <string name="btn_preset_reverse">USB / Reverse (localhost:5000)</string>
    <string name="btn_preset_emulator">Emulator (10.0.2.2:5000)</string>
    <string name="connection_error_title">Unable to Connect</string>
    <string name="connection_error_desc">Could not reach the Flask server. Please make sure the server is running on your laptop and check your connection settings.</string>
    <string name="btn_retry">Retry Connection</string>
    <string name="location_permission_rationale">Balaji Attendance requires precise location permissions to record GPS coordinates for punch-in and geofencing.</string>
</resources>
"""

# 12. values/colors.xml
files[os.path.join("app", "src", "main", "res", "values", "colors.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="primary">#1E3A8A</color>
    <color name="primary_dark">#172554</color>
    <color name="accent">#0284C7</color>
    <color name="background">#F8FAFC</color>
    <color name="surface">#FFFFFF</color>
    <color name="text_primary">#0F172A</color>
    <color name="text_secondary">#475569</color>
    <color name="error">#DC2626</color>
    <color name="white">#FFFFFF</color>
</resources>
"""

# 13. values/themes.xml
files[os.path.join("app", "src", "main", "res", "values", "themes.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.BalajiWorkforce" parent="Theme.Material3.DayNight.NoActionBar">
        <item name="colorPrimary">@color/primary</item>
        <item name="colorPrimaryDark">@color/primary_dark</item>
        <item name="colorSecondary">@color/accent</item>
        <item name="android:statusBarColor">@color/primary_dark</item>
        <item name="android:windowBackground">@color/background</item>
    </style>
</resources>
"""

# 14. menu/main_menu.xml
files[os.path.join("app", "src", "main", "res", "menu", "main_menu.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<menu xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto">
    <item
        android:id="@+id/action_refresh"
        android:icon="@android:drawable/ic_popup_sync"
        android:title="@string/action_refresh"
        app:showAsAction="ifRoom" />
    <item
        android:id="@+id/action_settings"
        android:icon="@android:drawable/ic_menu_preferences"
        android:title="@string/action_settings"
        app:showAsAction="always" />
</menu>
"""

# 15. layout/activity_main.xml
files[os.path.join("app", "src", "main", "res", "layout", "activity_main.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<androidx.coordinatorlayout.widget.CoordinatorLayout 
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="@color/background">

    <com.google.android.material.appbar.AppBarLayout
        android:id="@+id/appBarLayout"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:theme="@style/ThemeOverlay.MaterialComponents.Dark.ActionBar">

        <com.google.android.material.appbar.MaterialToolbar
            android:id="@+id/toolbar"
            android:layout_width="match_parent"
            android:layout_height="?attr/actionBarSize"
            android:background="@color/primary"
            app:title="@string/app_name"
            app:titleTextColor="@color/white"
            app:subtitleTextColor="#CBD5E1" />

        <com.google.android.material.progressindicator.LinearProgressIndicator
            android:id="@+id/progressBar"
            android:layout_width="match_parent"
            android:layout_height="3dp"
            android:indeterminate="true"
            android:visibility="gone"
            app:indicatorColor="@color/accent"
            app:trackColor="@color/primary_dark" />

    </com.google.android.material.appbar.AppBarLayout>

    <androidx.swiperefreshlayout.widget.SwipeRefreshLayout
        android:id="@+id/swipeRefreshLayout"
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        app:layout_behavior="@string/appbar_scrolling_view_behavior">

        <FrameLayout
            android:layout_width="match_parent"
            android:layout_height="match_parent">

            <WebView
                android:id="@+id/webView"
                android:layout_width="match_parent"
                android:layout_height="match_parent" />

            <!-- Connection Error State Layout -->
            <LinearLayout
                android:id="@+id/errorLayout"
                android:layout_width="match_parent"
                android:layout_height="match_parent"
                android:orientation="vertical"
                android:gravity="center"
                android:padding="24dp"
                android:visibility="gone"
                android:background="@color/background">

                <ImageView
                    android:layout_width="64dp"
                    android:layout_height="64dp"
                    android:src="@android:drawable/stat_notify_error"
                    app:tint="@color/error"
                    android:contentDescription="@null" />

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="16dp"
                    android:text="@string/connection_error_title"
                    android:textSize="20sp"
                    android:textStyle="bold"
                    android:textColor="@color/text_primary" />

                <TextView
                    android:id="@+id/tvCurrentTargetUrl"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="8dp"
                    android:text="http://localhost:5000"
                    android:textSize="13sp"
                    android:textStyle="italic"
                    android:textColor="@color/accent" />

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="12dp"
                    android:text="@string/connection_error_desc"
                    android:textAlignment="center"
                    android:textSize="14sp"
                    android:textColor="@color/text_secondary" />

                <LinearLayout
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:orientation="horizontal"
                    android:layout_marginTop="24dp">

                    <com.google.android.material.button.MaterialButton
                        android:id="@+id/btnRetry"
                        android:layout_width="wrap_content"
                        android:layout_height="wrap_content"
                        android:text="@string/btn_retry"
                        app:backgroundTint="@color/primary" />

                    <com.google.android.material.button.MaterialButton
                        android:id="@+id/btnChangeServer"
                        style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                        android:layout_width="wrap_content"
                        android:layout_height="wrap_content"
                        android:layout_marginStart="12dp"
                        android:text="@string/action_settings"
                        android:textColor="@color/primary"
                        app:strokeColor="@color/primary" />
                </LinearLayout>

            </LinearLayout>

        </FrameLayout>

    </androidx.swiperefreshlayout.widget.SwipeRefreshLayout>

</androidx.coordinatorlayout.widget.CoordinatorLayout>
"""

# 16. layout/dialog_server_url.xml
files[os.path.join("app", "src", "main", "res", "layout", "dialog_server_url.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:orientation="vertical"
    android:padding="20dp">

    <TextView
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Enter the URL where your Balaji Transport Flask app is running:"
        android:textColor="@color/text_secondary"
        android:textSize="14sp"
        android:layout_marginBottom="12dp" />

    <com.google.android.material.textfield.TextInputLayout
        android:id="@+id/tilServerUrl"
        style="@style/Widget.MaterialComponents.TextInputLayout.OutlinedBox"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:hint="Flask Server URL"
        app:boxStrokeColor="@color/primary">

        <com.google.android.material.textfield.TextInputEditText
            android:id="@+id/etServerUrl"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:inputType="textUri"
            android:singleLine="true" />

    </com.google.android.material.textfield.TextInputLayout>

    <TextView
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="Quick Presets:"
        android:textStyle="bold"
        android:textColor="@color/text_primary"
        android:textSize="13sp"
        android:layout_marginTop="16dp"
        android:layout_marginBottom="8dp" />

    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="horizontal">

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btnPresetLocalhost"
            style="@style/Widget.MaterialComponents.Button.TextButton"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="localhost:5000\\n(USB / ADB)"
            android:textSize="11sp" />

        <com.google.android.material.button.MaterialButton
            android:id="@+id/btnPresetEmulator"
            style="@style/Widget.MaterialComponents.Button.TextButton"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:text="10.0.2.2:5000\\n(Emulator)"
            android:textSize="11sp" />

    </LinearLayout>

    <TextView
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:layout_marginTop="8dp"
        android:text="Tip: For phone via USB, connect phone, run 'adb reverse tcp:5000 tcp:5000', and select localhost."
        android:textSize="11sp"
        android:textColor="@color/text_secondary" />

</LinearLayout>
"""

# 17. ServerConfigManager.kt
files[os.path.join("app", "src", "main", "java", "com", "balaji", "workforce", "ServerConfigManager.kt")] = """package com.balaji.workforce

import android.content.Context
import android.content.SharedPreferences

/**
 * Manages persistence for configurable Flask Backend URL.
 * Defaults to http://localhost:5000 for seamless USB Debugging with `adb reverse tcp:5000 tcp:5000`.
 */
class ServerConfigManager(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var serverUrl: String
        get() {
            val url = prefs.getString(KEY_SERVER_URL, DEFAULT_URL) ?: DEFAULT_URL
            return sanitizeUrl(url)
        }
        set(value) {
            val sanitized = sanitizeUrl(value)
            prefs.edit().putString(KEY_SERVER_URL, sanitized).apply()
        }

    fun isConfigured(): Boolean {
        return prefs.contains(KEY_SERVER_URL)
    }

    private fun sanitizeUrl(raw: String): String {
        var trimmed = raw.trim()
        if (trimmed.isEmpty()) {
            return DEFAULT_URL
        }
        if (!trimmed.startsWith("http://") && !trimmed.startsWith("https://")) {
            trimmed = "http://$trimmed"
        }
        if (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length - 1)
        }
        return trimmed
    }

    companion object {
        private const val PREFS_NAME = "balaji_workforce_prefs"
        private const val KEY_SERVER_URL = "backend_server_url"
        const val DEFAULT_URL = "http://localhost:5000"
        const val EMULATOR_URL = "http://10.0.2.2:5000"
    }
}
"""

# 18. MainActivity.kt
files[os.path.join("app", "src", "main", "java", "com", "balaji", "workforce", "MainActivity.kt")] = """package com.balaji.workforce

import android.Manifest
import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.view.LayoutInflater
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.CookieManager
import android.webkit.GeolocationPermissions
import android.webkit.URLUtil
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.balaji.workforce.databinding.ActivityMainBinding
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var serverConfigManager: ServerConfigManager

    // Geolocation callback state
    private var pendingGeoOrigin: String? = null
    private var pendingGeoCallback: GeolocationPermissions.Callback? = null

    // File upload callback state
    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    // ActivityResultLauncher for Location permissions
    private val locationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val fineGranted = permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true
        val coarseGranted = permissions[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        val granted = fineGranted || coarseGranted

        pendingGeoCallback?.invoke(pendingGeoOrigin, granted, false)
        pendingGeoCallback = null
        pendingGeoOrigin = null

        if (!granted) {
            Toast.makeText(
                this,
                "Location permission denied. Geofence attendance cannot be verified.",
                Toast.LENGTH_LONG
            ).show()
        }
    }

    // ActivityResultLauncher for File Chooser (Uploads/Photos)
    private val fileChooserLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (filePathCallback == null) return@registerForActivityResult
        val results: Array<Uri>? = if (result.resultCode == RESULT_OK && result.data != null) {
            val clipData = result.data?.clipData
            if (clipData != null) {
                Array(clipData.itemCount) { i -> clipData.getItemAt(i).uri }
            } else {
                result.data?.data?.let { arrayOf(it) }
            }
        } else {
            null
        }
        filePathCallback?.onReceiveValue(results)
        filePathCallback = null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setSupportActionBar(binding.toolbar)
        serverConfigManager = ServerConfigManager(this)

        updateToolbarSubtitle()
        setupWebView()
        setupSwipeRefresh()
        setupErrorHandling()
        setupBackNavigation()

        // Load the configured Flask server URL
        loadCurrentUrl()
    }

    private fun updateToolbarSubtitle() {
        val currentUrl = serverConfigManager.serverUrl
        binding.toolbar.subtitle = currentUrl
        binding.tvCurrentTargetUrl.text = currentUrl
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val webView = binding.webView
        val settings = webView.settings

        // Enable JavaScript and storage required for Flask session cookies & local storage
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.setGeolocationEnabled(true)
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.loadWithOverviewMode = true
        settings.useWideViewPort = true
        settings.builtInZoomControls = true
        settings.displayZoomControls = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        settings.cacheMode = WebSettings.LOAD_DEFAULT

        // Cookie Manager for Flask session preservation
        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        cookieManager.setAcceptThirdPartyCookies(webView, true)

        // WebChromeClient to handle HTML5 Geolocation, File Choosing, and Progress
        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                if (newProgress < 100) {
                    binding.progressBar.visibility = View.VISIBLE
                    binding.progressBar.progress = newProgress
                } else {
                    binding.progressBar.visibility = View.GONE
                    binding.swipeRefreshLayout.isRefreshing = false
                }
            }

            override fun onGeolocationPermissionsShowPrompt(
                origin: String?,
                callback: GeolocationPermissions.Callback?
            ) {
                val fine = ContextCompat.checkSelfPermission(
                    this@MainActivity,
                    Manifest.permission.ACCESS_FINE_LOCATION
                ) == PackageManager.PERMISSION_GRANTED

                val coarse = ContextCompat.checkSelfPermission(
                    this@MainActivity,
                    Manifest.permission.ACCESS_COARSE_LOCATION
                ) == PackageManager.PERMISSION_GRANTED

                if (fine || coarse) {
                    callback?.invoke(origin, true, false)
                } else {
                    pendingGeoOrigin = origin
                    pendingGeoCallback = callback
                    locationPermissionLauncher.launch(
                        arrayOf(
                            Manifest.permission.ACCESS_FINE_LOCATION,
                            Manifest.permission.ACCESS_COARSE_LOCATION
                        )
                    )
                }
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                this@MainActivity.filePathCallback?.onReceiveValue(null)
                this@MainActivity.filePathCallback = filePathCallback

                val intent = fileChooserParams?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                    type = "*/*"
                    addCategory(Intent.CATEGORY_OPENABLE)
                }
                try {
                    fileChooserLauncher.launch(intent)
                } catch (e: Exception) {
                    this@MainActivity.filePathCallback = null
                    return false
                }
                return true
            }
        }

        // WebViewClient to handle page navigation, errors, and external links
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val url = request?.url?.toString() ?: return false
                val base = serverConfigManager.serverUrl

                // Keep same host inside the WebView, open external links in browser
                return if (url.startsWith(base) || url.startsWith("http://localhost") || url.startsWith("http://127.0.0.1") || url.startsWith("http://10.0.2.2")) {
                    false
                } else {
                    try {
                        startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                    } catch (e: Exception) {
                        // ignore
                    }
                    true
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                binding.errorLayout.visibility = View.GONE
                binding.webView.visibility = View.VISIBLE
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) {
                    binding.webView.visibility = View.GONE
                    binding.errorLayout.visibility = View.VISIBLE
                }
            }
        }

        // Handle Download Listener for Excel Reports / Attendance CSVs
        webView.setDownloadListener { url, userAgent, contentDisposition, mimetype, _ ->
            try {
                val request = DownloadManager.Request(Uri.parse(url)).apply {
                    setMimeType(mimetype)
                    val cookies = CookieManager.getInstance().getCookie(url)
                    addRequestHeader("cookie", cookies)
                    addRequestHeader("User-Agent", userAgent)
                    setDescription("Downloading attendance report...")
                    val filename = URLUtil.guessFileName(url, contentDisposition, mimetype)
                    setTitle(filename)
                    setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                    setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)
                }
                val dm = getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
                dm.enqueue(request)
                Toast.makeText(this, "Downloading attendance report to Downloads folder...", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(this, "Download failed: ${e.localizedMessage}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun setupSwipeRefresh() {
        binding.swipeRefreshLayout.setColorSchemeColors(
            ContextCompat.getColor(this, R.color.primary),
            ContextCompat.getColor(this, R.color.accent)
        )
        binding.swipeRefreshLayout.setOnRefreshListener {
            binding.webView.reload()
        }
    }

    private fun setupErrorHandling() {
        binding.btnRetry.setOnClickListener {
            loadCurrentUrl()
        }
        binding.btnChangeServer.setOnClickListener {
            showServerSettingsDialog()
        }
    }

    private fun setupBackNavigation() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (binding.webView.canGoBack()) {
                    binding.webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }

    private fun loadCurrentUrl() {
        val targetUrl = serverConfigManager.serverUrl
        updateToolbarSubtitle()
        binding.errorLayout.visibility = View.GONE
        binding.webView.visibility = View.VISIBLE
        binding.progressBar.visibility = View.VISIBLE
        binding.webView.loadUrl(targetUrl)
    }

    override fun onCreateOptionsMenu(menu: Menu?): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_refresh -> {
                binding.webView.reload()
                true
            }
            R.id.action_settings -> {
                showServerSettingsDialog()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private fun showServerSettingsDialog() {
        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_server_url, null)
        val etUrl = dialogView.findViewById<EditText>(R.id.etServerUrl)
        val btnPresetLocalhost = dialogView.findViewById<MaterialButton>(R.id.btnPresetLocalhost)
        val btnPresetEmulator = dialogView.findViewById<MaterialButton>(R.id.btnPresetEmulator)

        etUrl.setText(serverConfigManager.serverUrl)

        btnPresetLocalhost.setOnClickListener {
            etUrl.setText(ServerConfigManager.DEFAULT_URL)
        }

        btnPresetEmulator.setOnClickListener {
            etUrl.setText(ServerConfigManager.EMULATOR_URL)
        }

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.server_settings_title)
            .setView(dialogView)
            .setPositiveButton(R.string.btn_save) { dialog, _ ->
                val newUrl = etUrl.text.toString().trim()
                if (newUrl.isNotEmpty()) {
                    serverConfigManager.serverUrl = newUrl
                    updateToolbarSubtitle()
                    loadCurrentUrl()
                    Toast.makeText(this, "Connecting to $newUrl", Toast.LENGTH_SHORT).show()
                }
                dialog.dismiss()
            }
            .setNegativeButton(R.string.btn_cancel) { dialog, _ ->
                dialog.dismiss()
            }
            .show()
    }
}
"""

# Launcher icons: generate standard XML adaptive icons so it builds without missing drawable errors
files[os.path.join("app", "src", "main", "res", "drawable", "ic_launcher_background.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#1E3A8A"
        android:pathData="M0,0h108v108h-108z" />
</vector>
"""

files[os.path.join("app", "src", "main", "res", "drawable", "ic_launcher_foreground.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="108dp"
    android:height="108dp"
    android:viewportWidth="108"
    android:viewportHeight="108">
    <path
        android:fillColor="#FFFFFF"
        android:pathData="M54,20A34,34 0 1,0 88,54A34,34 0 0,0 54,20ZM54,32A22,22 0 1,1 32,54A22,22 0 0,1 54,32ZM51,40L51,56L65,65L68,60L56,53L56,40Z" />
</vector>
"""

files[os.path.join("app", "src", "main", "res", "mipmap-anydpi-v26", "ic_launcher.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
"""

files[os.path.join("app", "src", "main", "res", "mipmap-anydpi-v26", "ic_launcher_round.xml")] = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background" />
    <foreground android:drawable="@drawable/ic_launcher_foreground" />
</adaptive-icon>
"""

# Write all files
for rel_path, content in files.items():
    full_path = os.path.join(TARGET_DIR, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Created: {rel_path}")

print("\\nAll project files generated successfully.")
