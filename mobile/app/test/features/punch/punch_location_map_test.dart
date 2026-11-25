import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/features/punch/ui/punch_location_map.dart';

List<List<num>> _square(num left, num bottom, num right, num top) => [
  [left, bottom],
  [right, bottom],
  [right, top],
  [left, top],
  [left, bottom],
];

Map<String, Object> _feature(String name, String type, Object points) => {
  'type': 'Feature',
  'properties': {'name': name},
  'geometry': {'type': type, 'coordinates': points},
};

void main() {
  final geoJson = jsonEncode({
    'type': 'FeatureCollection',
    'features': [
      _feature('Town', 'Polygon', [
        _square(120, 13, 121, 14),
        _square(120.4, 13.4, 120.6, 13.6),
      ]),
      _feature('Islands', 'MultiPolygon', [
        [_square(122, 13, 123, 14)],
        [_square(124, 13, 125, 14)],
      ]),
      _feature('Neighbor', 'Polygon', [_square(121, 13, 122, 14)]),
    ],
  });

  String? lookup(double latitude, double longitude) => municipalityFromGeoJson(
    geoJson,
    latitude: latitude,
    longitude: longitude,
  );

  test(
    'matches realistic longitude and latitude order and detached islands',
    () {
      expect(lookup(13.1, 120.2), 'Town');
      expect(lookup(13.1, 122.2), 'Islands');
      expect(lookup(13.1, 124.2), 'Islands');
      expect(lookup(120.2, 13.1), isNull);
    },
  );

  test(
    'a polygon hole, shared boundary or outside point has no municipality',
    () {
      expect(lookup(13.5, 120.5), isNull);
      expect(lookup(13.7, 121), isNull);
      expect(lookup(13.5, 128), isNull);
      expect(lookup(double.nan, 120), isNull);
    },
  );
}
