# KlockIN mobile by Tomeku

KlockIN records attendance with a front-camera selfie and a current GPS fix. It saves each punch to the device before attempting network delivery. A device can continue recording punches after an initial authenticated sign-in.

## Run locally

The verified Flutter version is 3.50.1. Android builds need JDK 17, Android SDK 36, Android NDK 28.2.13676358, and the SDK build tools. Android release builds also use SDK CMake 3.22.1 and require signing for distribution. iOS builds need Xcode with the relevant iOS platform. The optional face-detection dependency currently limits simulator builds to x86_64. Use an iOS device build to validate its camera and background processing on Apple Silicon hosts. Run from the `app` directory.

```sh
flutter pub get
flutter run --dart-define=KLOCKIN_SERVER_URL=https://your-klockin-server.example
```

The server URL can be left out and entered at sign-in. Server settings accepts a DNS name or IP address, optional port, and the installation path for a server mounted under a URL prefix. **Test connection** checks the KlockIN mobile API before credentials are entered. Sign in with the employee’s badge ID and password, or select Username for an existing account name. The first successful mobile sign-in enrolls the installation used for punches. A different phone requires an HR device reset. Production builds require HTTPS. Debug builds support private-network HTTP while the platform and server allow it.

On Android and iOS, the first successful mobile sign-in links the installation to the employee account. The same installation ID accompanies attendance punches. Ask HR to reset the linked device before switching installations.

## iOS device build

From the `app` directory, use the same full Xcode selection for dependency resolution and compilation. Flutter generates the native plugin manifest during dependency resolution.

```sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
flutter pub get
flutter build ios --debug --no-codesign --no-pub
```

If `xcode-select -p` points to Command Line Tools, run these steps in the same shell before the commands above. The wrapper gives Flutter's native build hooks access to the full Xcode SDK.

```sh
klockin_xcode_tools=$(mktemp -d)
cat > "$klockin_xcode_tools/xcrun" <<'EOF'
#!/bin/sh
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
exec /usr/bin/xcrun "$@"
EOF
chmod +x "$klockin_xcode_tools/xcrun"
export PATH="$klockin_xcode_tools:$PATH"
```

The unsigned device build writes `build/ios/iphoneos/Runner.app`. Installation on a device requires Apple signing.

## Attendance sync

The app stores an app-private SQLite queue scoped to the server origin and employee account. Each punch keeps its UUID and original capture time while pending. The queue encrypts the GPS and selfie on the phone with a key kept in platform secure storage. Upload starts with the multipart v2 punch endpoint when no older punches are pending. The offline queue sends five punches at a time in chronological order to the v2 batch endpoint. Successful server receipts clear the locally stored photo, while terminal server refusals remain visible in **Attendance sync** on Home.

Punch confirmation shows the official punch time and the best location available. That can be a server-resolved address, an allowed work location, or GPS coordinates. **Attendance sync** shows the last successful server confirmation for the current employee and server. A configured work-location policy is cached for offline capture and checked again by the server during sync.

The app retries on reconnection, when resumed, and through Android WorkManager and iOS background processing where the operating system schedules tasks. When the access token expires, the foreground and background share a local lock while they renew the session. If renewal is unavailable, the punch queue stays on the device for a later retry or sign-in.

To verify camera capture, GPS, and OS-scheduled background execution, install a build on a physical Android phone and a signed build on an iPhone. Both devices need reachable server access for sign-in and for the reconnect test.

On a cold offline start, Home displays the last confirmed worked hours for the current site workday, with the site-local confirmation time. The displayed total stays fixed offline and expires at the server-supplied workday boundary.

## Checks

```sh
flutter analyze --no-fatal-infos
flutter test
```

## Capture preview screenshots

From `mobile/app`, run `flutter test tool/readme_screenshots.dart` to generate screenshots of the current KlockIN app using sample data. The images are written to `mobile/docs/screenshots/preview`. Set `KLOCKIN_SCREENSHOT_DIR` to choose another output folder.

[Libraries and upstream source notices](NOTICE.md)
