// Modified for KlockIN by Tomeku, 2026-11-25.
import Contacts
import CoreLocation
import Flutter
import MapKit
import UIKit
import workmanager_apple

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    WorkmanagerPlugin.registerBGProcessingTask(withIdentifier: "com.tomeku.klockin.attendance-sync")
    WorkmanagerPlugin.setPluginRegistrantCallback { (registry: FlutterPluginRegistry) in
      GeneratedPluginRegistrant.register(with: registry)
      AppDelegate.registerAttendanceStorage(with: registry)
    }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    AppDelegate.registerAttendanceStorage(with: engineBridge.pluginRegistry)
    AppDelegate.registerLocationPreview(with: engineBridge.pluginRegistry)
  }

  private static func registerLocationPreview(with registry: FlutterPluginRegistry) {
    guard let registrar = registry.registrar(forPlugin: "KlockINLocationPreview") else { return }
    let channel = FlutterMethodChannel(
      name: "com.tomeku.klockin/location-preview", binaryMessenger: registrar.messenger())
    channel.setMethodCallHandler { call, result in
      let arguments = call.arguments as? [String: Any]
      switch call.method {
      case "lookupCapturedAddress":
        guard let latitude = arguments?["latitude"] as? Double,
          let longitude = arguments?["longitude"] as? Double,
          latitude.isFinite, longitude.isFinite,
          CLLocationCoordinate2DIsValid(CLLocationCoordinate2D(latitude: latitude, longitude: longitude))
        else {
          result(nil)
          return
        }
        let location = CLLocation(latitude: latitude, longitude: longitude)
        Task { @MainActor in await AppDelegate.locationPreview(for: location, result: result) }
      case "openGoogleMaps":
        AppDelegate.openGoogleMaps(arguments?["url"] as? String, result: result)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  @MainActor
  private static func locationPreview(for location: CLLocation, result: FlutterResult) async {
    do {
      async let address = resolvedAddress(for: location)
      async let snapshot = mapSnapshot(for: location.coordinate)
      // Display addresses returned by Apple alongside the corresponding Apple map.
      guard let label = try await address, !label.isEmpty,
        let image = try await snapshot
      else {
        result(nil)
        return
      }
      result(["address": label, "appleMapImage": FlutterStandardTypedData(bytes: image)])
    } catch {
      result(nil)
    }
  }

  @MainActor
  private static func resolvedAddress(for location: CLLocation) async throws -> String? {
    if #available(iOS 26.0, *) {
      guard let request = MKReverseGeocodingRequest(location: location),
        let item = try await request.mapItems.first
      else { return nil }
      return item.addressRepresentations?.fullAddress(includingRegion: true, singleLine: true)
        ?? item.address?.fullAddress
    }
    return try await legacyAddress(for: location)
  }

  @available(iOS, deprecated: 26.0)
  @MainActor
  private static func legacyAddress(for location: CLLocation) async throws -> String? {
    let geocoder = CLGeocoder()
    guard let placemark = try await geocoder.reverseGeocodeLocation(location).first else { return nil }
    if let postalAddress = placemark.postalAddress {
      return CNPostalAddressFormatter.string(from: postalAddress, style: .mailingAddress)
    }
    return [placemark.thoroughfare, placemark.locality, placemark.administrativeArea, placemark.country]
      .compactMap { $0 }
      .joined(separator: ", ")
  }

  @MainActor
  private static func mapSnapshot(for coordinate: CLLocationCoordinate2D) async throws -> Data? {
    let options = MKMapSnapshotter.Options()
    options.region = MKCoordinateRegion(center: coordinate, latitudinalMeters: 500, longitudinalMeters: 1_050)
    options.size = CGSize(width: 420, height: 200)
    options.traitCollection = UITraitCollection(traitsFrom: [
      UITraitCollection(userInterfaceStyle: .light), UITraitCollection(displayScale: 2),
    ])
    let snapshotter = MKMapSnapshotter(options: options)
    let snapshot = try await snapshotter.start()
    return snapshot.image.pngData()
  }

  private static func openGoogleMaps(_ value: String?, result: @escaping FlutterResult) {
    guard let value,
      let components = URLComponents(string: value),
      components.scheme == "https", components.host == "www.google.com",
      components.port == nil, components.user == nil, components.password == nil,
      components.queryItems?.contains(URLQueryItem(name: "api", value: "1")) == true,
      let url = components.url
    else {
      result(false)
      return
    }
    let isMapSearch = components.path == "/maps/search/"
    let isStreetView = components.path == "/maps/@"
      && components.queryItems?.contains(URLQueryItem(name: "map_action", value: "pano")) == true
    guard isMapSearch || isStreetView else {
      result(false)
      return
    }
    UIApplication.shared.open(url, options: [:]) { opened in result(opened) }
  }

  private static func registerAttendanceStorage(with registry: FlutterPluginRegistry) {
    guard let registrar = registry.registrar(forPlugin: "KlockINAttendanceStorage") else { return }
    let channel = FlutterMethodChannel(name: "com.tomeku.klockin/attendance-storage", binaryMessenger: registrar.messenger())
    channel.setMethodCallHandler { call, result in
      guard call.method == "privateQueuePath" else {
        result(FlutterMethodNotImplemented)
        return
      }
      do {
        let manager = FileManager.default
        let support = try manager.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                      appropriateFor: nil, create: true)
        var directory = support.appendingPathComponent("AttendanceQueue", isDirectory: true)
        try manager.createDirectory(at: directory, withIntermediateDirectories: true,
                                    attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var resources = URLResourceValues()
        resources.isExcludedFromBackup = true
        try directory.setResourceValues(resources)
        result(directory.appendingPathComponent("klockin-punches.sqlite").path)
      } catch {
        result(FlutterError(code: "queue_unavailable", message: "Attendance storage is unavailable.", details: nil))
      }
    }
  }
}
