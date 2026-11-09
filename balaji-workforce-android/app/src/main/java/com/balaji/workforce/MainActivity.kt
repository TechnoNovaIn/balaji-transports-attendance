package com.balaji.workforce

import android.Manifest
import android.annotation.SuppressLint
import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.webkit.CookieManager
import android.webkit.GeolocationPermissions
import android.webkit.JavascriptInterface
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
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.balaji.workforce.databinding.ActivityMainBinding
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var serverConfigManager: ServerConfigManager

    // HTML5 Geolocation prompt state
    private var pendingGeoOrigin: String? = null
    private var pendingGeoCallback: GeolocationPermissions.Callback? = null

    // Native Bridge Location callback state
    private var pendingBridgeLocationCallback: String? = null

    // File upload callback state
    private var filePathCallback: ValueCallback<Array<Uri>>? = null

    // ActivityResultLauncher for Location permissions (shared for Bridge & HTML5 Geolocation)
    private val locationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val fineGranted = permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true
        val coarseGranted = permissions[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        val granted = fineGranted || coarseGranted

        // 1. Resolve HTML5 Geolocation prompt if pending
        pendingGeoCallback?.invoke(pendingGeoOrigin, granted, true)
        pendingGeoCallback = null
        pendingGeoOrigin = null

        // 2. Resolve Native Bridge location request if pending
        val bridgeCb = pendingBridgeLocationCallback
        pendingBridgeLocationCallback = null

        if (granted) {
            if (bridgeCb != null) {
                retrieveAndDispatchNativeLocation(bridgeCb)
            }
        } else {
            val permanentlyDenied = !ActivityCompat.shouldShowRequestPermissionRationale(
                this,
                Manifest.permission.ACCESS_FINE_LOCATION
            )
            val errorMessage = if (permanentlyDenied) {
                "Location permission permanently denied. Please enable Location in Android Settings > Apps > Balaji Workforce."
            } else {
                "Location permission was denied. Please allow location permission to record attendance."
            }
            if (bridgeCb != null) {
                dispatchLocationToJs(bridgeCb, false, 0.0, 0.0, 0.0f, errorMessage)
            }
            Toast.makeText(this, errorMessage, Toast.LENGTH_LONG).show()
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

        // Production UI: Match Android status bar with the website's white header
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
            window.statusBarColor = ContextCompat.getColor(this, android.R.color.white)
        }

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
        binding.tvCurrentTargetUrl.text = currentUrl
    }

    private fun isUrlTrusted(url: String?): Boolean {
        if (url.isNullOrEmpty()) return false
        val reqUri = try { Uri.parse(url) } catch (e: Exception) { return false }
        val baseUri = try { Uri.parse(serverConfigManager.serverUrl) } catch (e: Exception) { null }
        val host = reqUri.host?.lowercase() ?: ""
        val baseHost = baseUri?.host?.lowercase() ?: ""

        return (baseHost.isNotEmpty() && host == baseHost) ||
                host in listOf("localhost", "127.0.0.1", "10.0.2.2") ||
                reqUri.scheme == "about"
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val webView = binding.webView
        val settings = webView.settings

        // Enable hardware acceleration layer for 60fps smooth scrolling
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null)
        webView.isNestedScrollingEnabled = true

        // Enable JavaScript and storage required for Flask session cookies & local storage
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.setGeolocationEnabled(true)
        settings.allowFileAccess = false
        settings.allowContentAccess = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.loadWithOverviewMode = true
        settings.useWideViewPort = true
        settings.builtInZoomControls = true
        settings.displayZoomControls = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        settings.cacheMode = WebSettings.LOAD_DEFAULT

        // Register Native Android Location Bridge
        webView.addJavascriptInterface(AndroidLocationBridge(), "AndroidLocationBridge")

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
                // Ensure only trusted server origin is granted geolocation permission
                if (!isUrlTrusted(origin)) {
                    callback?.invoke(origin, false, false)
                    return
                }

                val fine = ContextCompat.checkSelfPermission(
                    this@MainActivity,
                    Manifest.permission.ACCESS_FINE_LOCATION
                ) == PackageManager.PERMISSION_GRANTED

                val coarse = ContextCompat.checkSelfPermission(
                    this@MainActivity,
                    Manifest.permission.ACCESS_COARSE_LOCATION
                ) == PackageManager.PERMISSION_GRANTED

                if (fine || coarse) {
                    callback?.invoke(origin, true, true)
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

        // WebViewClient to handle page navigation, errors, session security, and external links
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val reqUri = request?.url ?: return false
                val isInternal = isUrlTrusted(reqUri.toString())

                return if (isInternal) {
                    false
                } else {
                    try {
                        startActivity(Intent(Intent.ACTION_VIEW, reqUri))
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
                binding.progressBar.visibility = View.GONE
                binding.swipeRefreshLayout.isRefreshing = false

                // If user is on the login page (after logout or initial visit),
                // clear history so Android Back button does not revisit authenticated session pages
                if (url != null && (url.contains("/login") || url.endsWith("/login"))) {
                    view?.clearHistory()
                }

                // Persist session cookies to disk
                CookieManager.getInstance().flush()
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

            @Deprecated("Deprecated in Java")
            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                binding.webView.visibility = View.GONE
                binding.errorLayout.visibility = View.VISIBLE
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
        // Coordinate vertical scrolling between SwipeRefreshLayout and WebView
        binding.swipeRefreshLayout.setOnChildScrollUpCallback { _, _ ->
            binding.webView.canScrollVertically(-1) || binding.webView.scrollY > 0
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
                val currentUrl = binding.webView.url ?: ""
                // If on login page, exit the application rather than returning to cached session pages
                if (currentUrl.contains("/login")) {
                    finish()
                    return
                }
                if (binding.webView.canGoBack()) {
                    binding.webView.goBack()
                } else {
                    finish()
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

    // ================= Native Android Location Bridge =================

    inner class AndroidLocationBridge {
        @JavascriptInterface
        fun isLocationAvailable(): Boolean {
            return true
        }

        @JavascriptInterface
        fun requestLocation(callbackName: String) {
            runOnUiThread {
                startNativeLocationCapture(callbackName)
            }
        }
    }

    private fun startNativeLocationCapture(callbackName: String) {
        val currentUrl = binding.webView.url ?: ""
        if (!isUrlTrusted(currentUrl)) {
            dispatchLocationToJs(
                callbackName,
                false,
                0.0,
                0.0,
                0.0f,
                "Location request denied: Origin is not trusted."
            )
            return
        }

        val fine = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED

        val coarse = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.ACCESS_COARSE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED

        if (fine || coarse) {
            retrieveAndDispatchNativeLocation(callbackName)
        } else {
            pendingBridgeLocationCallback = callbackName
            locationPermissionLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION
                )
            )
        }
    }

    private fun retrieveAndDispatchNativeLocation(callbackName: String) {
        val locationManager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val isGpsEnabled = locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)
        val isNetEnabled = locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)

        if (!isGpsEnabled && !isNetEnabled) {
            dispatchLocationToJs(
                callbackName,
                false,
                0.0,
                0.0,
                0.0f,
                "Device GPS/Location service is turned off. Please enable Location in Android quick settings and retry."
            )
            Toast.makeText(this, "Please turn on GPS/Location in device settings", Toast.LENGTH_LONG).show()
            return
        }

        // Try getting fresh last known location first (within 30 seconds)
        val lastGps = try { locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER) } catch (e: SecurityException) { null }
        val lastNet = try { locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER) } catch (e: SecurityException) { null }
        val bestLast = when {
            lastGps != null && lastNet != null -> if (lastGps.time >= lastNet.time) lastGps else lastNet
            lastGps != null -> lastGps
            else -> lastNet
        }

        if (bestLast != null && (System.currentTimeMillis() - bestLast.time) < 30000) {
            dispatchLocationToJs(
                callbackName,
                true,
                bestLast.latitude,
                bestLast.longitude,
                bestLast.accuracy,
                null
            )
            return
        }

        // Request single fresh location update with 15-second timeout
        val timeoutHandler = Handler(Looper.getMainLooper())
        var listener: LocationListener? = null

        val timeoutRunnable = Runnable {
            listener?.let {
                try { locationManager.removeUpdates(it) } catch (e: Exception) {}
            }
            if (bestLast != null) {
                dispatchLocationToJs(
                    callbackName,
                    true,
                    bestLast.latitude,
                    bestLast.longitude,
                    bestLast.accuracy,
                    null
                )
            } else {
                dispatchLocationToJs(
                    callbackName,
                    false,
                    0.0,
                    0.0,
                    0.0f,
                    "Location request timed out. Please ensure GPS has a clear view of the sky and retry."
                )
            }
        }

        listener = object : LocationListener {
            override fun onLocationChanged(loc: Location) {
                timeoutHandler.removeCallbacks(timeoutRunnable)
                try { locationManager.removeUpdates(this) } catch (e: Exception) {}
                dispatchLocationToJs(
                    callbackName,
                    true,
                    loc.latitude,
                    loc.longitude,
                    loc.accuracy,
                    null
                )
            }
            override fun onProviderDisabled(provider: String) {}
            override fun onProviderEnabled(provider: String) {}
            @Deprecated("Deprecated in Java")
            override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
        }

        timeoutHandler.postDelayed(timeoutRunnable, 15000)

        try {
            if (isGpsEnabled) {
                locationManager.requestLocationUpdates(
                    LocationManager.GPS_PROVIDER,
                    0L,
                    0f,
                    listener,
                    Looper.getMainLooper()
                )
            }
            if (isNetEnabled) {
                locationManager.requestLocationUpdates(
                    LocationManager.NETWORK_PROVIDER,
                    0L,
                    0f,
                    listener,
                    Looper.getMainLooper()
                )
            }
        } catch (e: SecurityException) {
            timeoutHandler.removeCallbacks(timeoutRunnable)
            dispatchLocationToJs(
                callbackName,
                false,
                0.0,
                0.0,
                0.0f,
                "Location security error: ${e.localizedMessage}"
            )
        }
    }

    private fun dispatchLocationToJs(
        callbackName: String,
        success: Boolean,
        lat: Double,
        lng: Double,
        accuracy: Float,
        errorMsg: String?
    ) {
        val errStr = if (errorMsg != null) org.json.JSONObject.quote(errorMsg) else "null"
        val js = "if (typeof window['$callbackName'] === 'function') { window['$callbackName']($success, $lat, $lng, $accuracy, $errStr); }"
        binding.webView.post {
            binding.webView.evaluateJavascript(js, null)
        }
    }

    // ================= Server Settings Dialog (Triggered from Error Screen) =================

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
