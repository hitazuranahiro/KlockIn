package com.tomeku.klockin

import android.content.ActivityNotFoundException
import android.content.Intent
import android.location.Address
import android.location.Geocoder
import android.net.Uri
import android.os.Build
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.IOException
import java.util.concurrent.Executors

// local_auth's Android side needs a FragmentActivity to host
// androidx.biometric.BiometricPrompt -- plain FlutterActivity isn't one and
// crashes with a ClassCastException the first time authenticate() is called.
class MainActivity : FlutterFragmentActivity() {
    private var locationPreview: MethodChannel? = null
    private val geocoderExecutor = Executors.newSingleThreadExecutor()

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val messenger = flutterEngine.dartExecutor.binaryMessenger
        locationPreview = MethodChannel(messenger, "com.tomeku.klockin/location-preview").apply {
            setMethodCallHandler { call, result ->
                when (call.method) {
                    "lookupCapturedAddress" -> lookupAddress(
                        call.argument<Double>("latitude"),
                        call.argument<Double>("longitude"),
                        result,
                    )
                    "openGoogleMaps" -> result.success(openGoogleMaps(call.argument<String>("url")))
                    else -> result.notImplemented()
                }
            }
        }
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        locationPreview?.setMethodCallHandler(null)
        locationPreview = null
        super.cleanUpFlutterEngine(flutterEngine)
    }

    override fun onDestroy() {
        geocoderExecutor.shutdownNow()
        super.onDestroy()
    }

    private fun lookupAddress(latitude: Double?, longitude: Double?, result: MethodChannel.Result) {
        if (latitude == null || longitude == null ||
            latitude !in -90.0..90.0 || longitude !in -180.0..180.0 || !Geocoder.isPresent()
        ) {
            result.success(null)
            return
        }

        val geocoder = Geocoder(applicationContext)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            geocoder.getFromLocation(latitude, longitude, 1, object : Geocoder.GeocodeListener {
                override fun onGeocode(addresses: MutableList<Address>) {
                    runOnUiThread { result.success(locationPreview(addresses.firstOrNull())) }
                }

                override fun onError(errorMessage: String?) {
                    runOnUiThread { result.success(null) }
                }
            })
        } else {
            geocoderExecutor.execute {
                val address = lookupLegacyAddress(geocoder, latitude, longitude)
                runOnUiThread { result.success(locationPreview(address)) }
            }
        }
    }

    @Suppress("DEPRECATION") // On API 32 and earlier this is the only geocoding overload.
    private fun lookupLegacyAddress(geocoder: Geocoder, latitude: Double, longitude: Double): Address? =
        try {
            geocoder.getFromLocation(latitude, longitude, 1)?.firstOrNull()
        } catch (_: IOException) {
            null
        }

    private fun locationPreview(address: Address?): Map<String, String>? {
        if (address == null) return null
        val label = address.getAddressLine(0)?.trim()?.takeIf(String::isNotEmpty)
            ?: listOfNotNull(address.thoroughfare, address.subLocality, address.locality,
                address.subAdminArea, address.adminArea, address.countryName)
                .map(String::trim)
                .filter(String::isNotEmpty)
                .distinct()
                .joinToString(", ")
                .takeIf(String::isNotEmpty)
        return label?.let { mapOf("address" to it) }
    }

    private fun openGoogleMaps(value: String?): Boolean {
        val url = value?.let(Uri::parse) ?: return false
        if (url.scheme != "https" || url.encodedAuthority != "www.google.com" ||
            url.getQueryParameter("api") != "1"
        ) return false
        val isMapSearch = url.path == "/maps/search/"
        val isStreetView = url.path == "/maps/@" && url.getQueryParameter("map_action") == "pano"
        if (!isMapSearch && !isStreetView) return false

        return try {
            startActivity(Intent(Intent.ACTION_VIEW, url))
            true
        } catch (_: ActivityNotFoundException) {
            false
        } catch (_: SecurityException) {
            false
        }
    }
}
