package com.balaji.workforce

import android.content.Context
import android.content.SharedPreferences

/**
 * Manages persistence for configurable Flask Backend URL.
 * After deployment, update DEFAULT_URL to the Render HTTPS URL.
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
            trimmed = "https://$trimmed"
        }
        if (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length - 1)
        }
        return trimmed
    }

    companion object {
        private const val PREFS_NAME = "balaji_workforce_prefs"
        private const val KEY_SERVER_URL = "backend_server_url"
        const val DEFAULT_URL = "https://balaji-workforce1.onrender.com"
        const val EMULATOR_URL = "http://10.0.2.2:5000"
    }
}
