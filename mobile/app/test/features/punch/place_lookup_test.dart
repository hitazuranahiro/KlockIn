import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/features/punch/data/place_lookup.dart';

void main() {
  const channel = MethodChannel('com.tomeku.klockin/location-preview');
  final messenger =
      TestWidgetsFlutterBinding.ensureInitialized().defaultBinaryMessenger;

  tearDown(() => messenger.setMockMethodCallHandler(channel, null));

  test('invalid coordinates never reach the device channel', () async {
    final calls = <MethodCall>[];
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      return null;
    });

    expect(
      await lookupCapturedLocationPreview(latitude: double.nan, longitude: 120),
      isNull,
    );
    expect(
      await openCapturedLocationInGoogleMaps(latitude: 14, longitude: -181),
      isFalse,
    );
    expect(
      await openCapturedLocationInGoogleStreetView(
        latitude: double.infinity,
        longitude: 120,
      ),
      isFalse,
    );
    expect(calls, isEmpty);
  });

  test('Street View opens with the captured point as its viewpoint', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'openGoogleMaps');
      expect(
        call.arguments['url'],
        'https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=14.5%2C120.9',
      );
      return true;
    });

    expect(
      await openCapturedLocationInGoogleStreetView(
        latitude: 14.5,
        longitude: 120.9,
      ),
      isTrue,
    );
  });

  test('normalizes the address and retains its paired Apple map', () async {
    final bytes = Uint8List.fromList([1, 2, 3]);
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'lookupCapturedAddress');
      expect(call.arguments, {'latitude': 14.5, 'longitude': 120.9});
      return {'address': '  Main Road\r\n\n  Manila  ', 'appleMapImage': bytes};
    });

    final location = await lookupCapturedLocationPreview(
      latitude: 14.5,
      longitude: 120.9,
    );
    expect(location?.address, 'Main Road, Manila');
    expect(location?.appleMapImage, bytes);
  });

  test('malformed results and unavailable native services fall back', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      if (call.method == 'openGoogleMaps') {
        throw PlatformException(code: 'unavailable');
      }
      return {'address': 'Main Road', 'appleMapImage': 'invalid'};
    });

    expect(
      await lookupCapturedLocationPreview(latitude: 14, longitude: 120),
      isNull,
    );
    expect(
      await openCapturedLocationInGoogleMaps(latitude: 14, longitude: 120),
      isFalse,
    );
  });
}
