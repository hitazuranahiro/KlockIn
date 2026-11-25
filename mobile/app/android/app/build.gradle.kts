// Modified for KlockIN by Tomeku, 2026-11-25.
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.tomeku.klockin"
    compileSdk = 36
    // camera_android_camerax, google_mlkit_* and several other plugins all
    // require this NDK; the flutter tool prints the exact version to pin
    // whenever a build mixes an older one in.
    ndkVersion = "28.2.13676358"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true
    }


    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.tomeku.klockin"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = 36
        // Package JNI libraries only for the Flutter engines this build contains.
        val flutterTargets = providers.gradleProperty("target-platform").orNull
        val splitPerAbi = providers.gradleProperty("split-per-abi").orNull.toBoolean()
        val disableAbiFiltering = providers.gradleProperty("disable-abi-filtering").orNull.toBoolean()
        if (flutterTargets != null && !splitPerAbi && !disableAbiFiltering) {
            val flutterAbis = mapOf(
                "android-arm" to "armeabi-v7a",
                "android-arm64" to "arm64-v8a",
                "android-x64" to "x86_64",
            )
            ndk.abiFilters.apply {
                clear()
                addAll(flutterTargets.split(",").map { flutterAbis.getValue(it.trim()) })
            }
        }
        // From pubspec (version: 2.0.0+12) rather than hardcoded: these had
        // drifted to 1.0.3/9 while pubspec said 1.0.10+11, and a release
        // needs one source of truth. versionCode must only ever increase --
        // check the Play Console before the first upload.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        getByName("release") {
            isShrinkResources = true // This requires isMinifyEnabled = true
        }
        getByName("debug") {
            // Debug builds install alongside the released app instead of
            // replacing it. Same package id would mean uninstalling the real
            // app from a tester's phone -- and a debug build that looks
            // identical to production on the launcher is its own hazard.
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
            // The launcher name comes from src/debug/res rather than a
            // resValue, which AGP 9 gates behind a build feature.
        }
    }
}

// Kotlin 2.x removed the kotlinOptions DSL that the inherited config used.
kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.JVM_17
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.0.4")
    // Add your other dependencies here
}

flutter {
    source = "../.."
}
