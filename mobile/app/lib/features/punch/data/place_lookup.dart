import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/services.dart';

const _locationPreview = MethodChannel('com.tomeku.klockin/location-preview');

class CapturedLocationPreview {
  const CapturedLocationPreview({required this.address, this.appleMapImage});

  final String? address;
  final Uint8List? appleMapImage;
}

/// Resolves the position already captured by the attendance flow when the
/// device has a geocoding service. Keep an Apple address with its map image.
Future<CapturedLocationPreview?> lookupCapturedLocationPreview({
  required double latitude,
  required double longitude,
}) async {
  if (!_validCoordinates(latitude, longitude)) return null;
  final preview = await _invokeLocationPreview('lookupCapturedAddress', {
    'latitude': latitude,
    'longitude': longitude,
  });
  if (preview is! Map<Object?, Object?>) return null;
  final address = preview['address'];
  final image = preview['appleMapImage'];
  if (address is! String || (image != null && image is! Uint8List)) return null;
  final formatted = address
      .split(RegExp(r'[\r\n]+'))
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty)
      .join(', ');
  if (formatted.isEmpty) return null;
  return CapturedLocationPreview(
    address: formatted,
    appleMapImage: preview['appleMapImage'] as Uint8List?,
  );
}

/// Opens Google Maps on request, using its public Maps URL with no API key.
Future<bool> openCapturedLocationInGoogleMaps({
  required double latitude,
  required double longitude,
}) async {
  if (!_validCoordinates(latitude, longitude)) return false;
  return _openGoogleMaps('/maps/search/', {
    'api': '1',
    'query': '$latitude,$longitude',
  });
}

/// Opens the nearest Google Street View panorama where imagery is available.
Future<bool> openCapturedLocationInGoogleStreetView({
  required double latitude,
  required double longitude,
}) async {
  if (!_validCoordinates(latitude, longitude)) return false;
  return _openGoogleMaps('/maps/@', {
    'api': '1',
    'map_action': 'pano',
    'viewpoint': '$latitude,$longitude',
  });
}

Future<bool> _openGoogleMaps(
  String path,
  Map<String, String> parameters,
) async {
  final url = Uri.https('www.google.com', path, parameters);
  return await _invokeLocationPreview('openGoogleMaps', {
        'url': url.toString(),
      }) ==
      true;
}

bool _validCoordinates(double latitude, double longitude) =>
    latitude.isFinite &&
    longitude.isFinite &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180;

Future<Object?> _invokeLocationPreview(String method, Object arguments) async {
  try {
    return await _locationPreview
        .invokeMethod<Object>(method, arguments)
        .timeout(const Duration(seconds: 8));
  } on PlatformException {
    return null;
  } on MissingPluginException {
    return null;
  } on TimeoutException {
    return null;
  }
}
