import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../../core/theme/tokens.dart';
import '../../../l10n/app_localizations.dart';
import '../../../shared/widgets/glass_surface.dart';
import '../data/place_lookup.dart';

const _municipalitiesAsset = 'Assets/maps/philippines-municipalities.geojson';
const _roadsAsset = 'Assets/maps/philippines-major-roads.geojson';
const _mapWater = Color(0xFFDDEBFA);
final _mapsByBundle = Expando<Future<_OfflineMapData>>();

/// Keeps one lookup across the location preview and its punch receipt.
class PunchAddressLookup {
  Offset? _point;
  Future<CapturedLocationPreview?>? _pending;

  Future<CapturedLocationPreview?> resolve(double latitude, double longitude) {
    final point = Offset(longitude, latitude);
    final previous = _point;
    // A fresh GPS reading can shift a few meters while the employee stands still.
    const matchingRadiusDegrees = 0.00004;
    if (previous != null &&
        (point - previous).distanceSquared <
            matchingRadiusDegrees * matchingRadiusDegrees) {
      return _pending!;
    }
    _point = point;
    return _pending = lookupCapturedLocationPreview(
      latitude: latitude,
      longitude: longitude,
    );
  }
}

/// Shows device coordinates on a bundled offline map with an optional address.
class PunchLocationMap extends StatefulWidget {
  const PunchLocationMap({
    super.key,
    required this.latitude,
    required this.longitude,
    this.address,
    this.addressLookup,
  });

  final double latitude;
  final double longitude;
  final String? address;
  final PunchAddressLookup? addressLookup;

  @override
  State<PunchLocationMap> createState() => _PunchLocationMapState();
}

class _PunchLocationMapState extends State<PunchLocationMap> {
  final _fallbackLookup = PunchAddressLookup();
  Future<CapturedLocationPreview?>? _previewFuture;

  @override
  void initState() {
    super.initState();
    _updatePreview();
  }

  @override
  void didUpdateWidget(PunchLocationMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.latitude != widget.latitude ||
        oldWidget.longitude != widget.longitude ||
        oldWidget.addressLookup != widget.addressLookup) {
      _updatePreview();
    }
  }

  void _updatePreview() {
    _previewFuture = _coordinate(widget.longitude, widget.latitude) == null
        ? null
        : (widget.addressLookup ?? _fallbackLookup).resolve(
            widget.latitude,
            widget.longitude,
          );
  }

  @override
  Widget build(BuildContext context) {
    final point = _coordinate(widget.longitude, widget.latitude);
    if (point == null) return const SizedBox.shrink();
    final l10n = AppL10n.of(context);
    final bundle = DefaultAssetBundle.of(context);

    return FutureBuilder<_OfflineMapData>(
      future: _mapsByBundle[bundle] ??= _loadOfflineMap(bundle),
      builder: (context, snapshot) {
        final data = snapshot.data;
        final viewport = _near(point, latitudeRadius: 0.06);
        final places = data?.placesNear(viewport) ?? const <_Place>[];
        final roads = data?.roadsNear(viewport) ?? const <_Line>[];
        final municipality = data?.municipalityAt(point);
        final showMap = places.isNotEmpty || roads.isNotEmpty;
        final title = municipality ?? l10n.punchGpsCoordinates;

        return GlassSurface(
          padding: const EdgeInsets.all(AppSpace.x12),
          blur: 0,
          child: FutureBuilder<CapturedLocationPreview?>(
            key: ValueKey(_previewFuture),
            future: _previewFuture,
            builder: (context, previewSnapshot) {
              final preview = previewSnapshot.data;
              final appleMapImage = preview?.appleMapImage;
              final serverAddress = _cleanAddress(widget.address);
              final nativeAddress = _cleanAddress(preview?.address);
              final usesAppleLookup =
                  defaultTargetPlatform == TargetPlatform.iOS;
              final address =
                  serverAddress ??
                  (usesAppleLookup && appleMapImage == null
                      ? null
                      : nativeAddress);
              final offlineAddress =
                  serverAddress ?? (usesAppleLookup ? null : nativeAddress);
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (showMap || appleMapImage != null)
                    _MapFrame(
                      onExpand: showMap
                          ? () => _openMap(
                              context,
                              data!,
                              point,
                              title,
                              offlineAddress,
                            )
                          : null,
                      expandLabel: municipality == null
                          ? l10n.punchMapExplorePoint
                          : l10n.punchMapExploreMunicipality(municipality),
                      mapLabel: l10n.punchOfflineMap,
                      usingAppleMap: appleMapImage != null,
                      child: appleMapImage == null
                          ? _MapCanvas(
                              point: point,
                              places: places,
                              roads: roads,
                              municipality: municipality,
                              latitudeRadius: 0.025,
                            )
                          : Semantics(
                              label: l10n.punchAppleMapCenteredPoint,
                              image: true,
                              child: Image.memory(
                                appleMapImage,
                                fit: BoxFit.contain,
                              ),
                            ),
                    )
                  else
                    Container(
                      padding: const EdgeInsets.all(AppSpace.x12),
                      decoration: BoxDecoration(
                        color: AppColors.brandTint,
                        borderRadius: BorderRadius.circular(AppRadii.field),
                      ),
                      child: Row(
                        children: [
                          const Icon(
                            Icons.location_on_rounded,
                            size: 21,
                            color: AppColors.brandStrong,
                          ),
                          const SizedBox(width: AppSpace.x8),
                          Expanded(
                            child: Text(
                              snapshot.connectionState ==
                                      ConnectionState.waiting
                                  ? l10n.punchOfflineMapLoading
                                  : l10n.punchOfflineMapUnavailable,
                              style: AppText.meta.copyWith(
                                color: AppColors.ink2,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 13, 4, 5),
                    child: _LocationDetails(
                      point: point,
                      municipality: municipality,
                      address: address,
                      resolvingAddress:
                          address == null &&
                          previewSnapshot.connectionState ==
                              ConnectionState.waiting,
                    ),
                  ),
                  if (showMap && appleMapImage == null)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(4, 3, 4, 0),
                      child: Text(
                        _credit(roads.isNotEmpty),
                        style: AppText.meta,
                      ),
                    ),
                  if (_canOpenGoogleMaps) ...[
                    const SizedBox(height: AppSpace.x8),
                    _GoogleMapsActions(point: point),
                  ],
                ],
              );
            },
          ),
        );
      },
    );
  }
}

class _MapFrame extends StatelessWidget {
  const _MapFrame({
    required this.expandLabel,
    required this.mapLabel,
    required this.usingAppleMap,
    required this.child,
    this.onExpand,
  });

  final String expandLabel;
  final String mapLabel;
  final bool usingAppleMap;
  final Widget child;
  final VoidCallback? onExpand;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: _mapWater,
      borderRadius: BorderRadius.circular(AppRadii.field),
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        height: 158,
        child: Stack(
          fit: StackFit.expand,
          children: [
            child,
            if (usingAppleMap)
              const Center(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.brandStrong,
                    shape: BoxShape.circle,
                    border: Border.fromBorderSide(
                      BorderSide(color: AppColors.surface, width: 2),
                    ),
                    boxShadow: [
                      BoxShadow(color: Color(0x4D104FCE), blurRadius: 7),
                    ],
                  ),
                  child: SizedBox.square(dimension: 14),
                ),
              )
            else
              PositionedDirectional(
                bottom: 9,
                start: 9,
                child: GlassSurface(
                  radius: AppRadii.pill,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 9,
                    vertical: 5,
                  ),
                  child: Text(
                    mapLabel,
                    style: AppText.meta.copyWith(
                      color: AppColors.ink,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            if (onExpand != null)
              Positioned.fill(
                child: Semantics(
                  label: expandLabel,
                  button: true,
                  excludeSemantics: true,
                  onTap: onExpand,
                  child: InkWell(onTap: onExpand),
                ),
              ),
            if (onExpand != null)
              const PositionedDirectional(
                top: 9,
                end: 9,
                child: IgnorePointer(
                  child: GlassSurface(
                    radius: 12,
                    padding: EdgeInsets.all(8),
                    child: Icon(
                      Icons.open_in_full_rounded,
                      size: 16,
                      color: AppColors.ink,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

String? _cleanAddress(String? address) {
  final value = address?.trim();
  return value == null || value.isEmpty ? null : value;
}

class _LocationDetails extends StatelessWidget {
  const _LocationDetails({
    required this.point,
    this.municipality,
    this.address,
    this.resolvingAddress = false,
  });

  final Offset point;
  final String? municipality;
  final String? address;
  final bool resolvingAddress;

  @override
  Widget build(BuildContext context) {
    final l10n = AppL10n.of(context);
    final (label, value) = switch ((address, municipality)) {
      (final street?, _) => (l10n.punchDetectedAddress, street),
      (null, final city?) => (l10n.punchApproximateMunicipality, city),
      _ => (l10n.punchDetectedLocation, l10n.punchGpsCoordinates),
    };

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: AppText.meta.copyWith(
            color: AppColors.ink3,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 3),
        Text(value, style: AppText.cardTitle.copyWith(color: AppColors.ink)),
        const SizedBox(height: 4),
        Text(
          _coordinateText(point),
          style: AppText.mono.copyWith(color: AppColors.ink3),
        ),
        if (resolvingAddress) ...[
          const SizedBox(height: 4),
          Text(l10n.punchAddressLookingUp, style: AppText.meta),
        ],
      ],
    );
  }
}

bool get _canOpenGoogleMaps =>
    !kIsWeb &&
    (defaultTargetPlatform == TargetPlatform.iOS ||
        defaultTargetPlatform == TargetPlatform.android);

class _GoogleMapsActions extends StatelessWidget {
  const _GoogleMapsActions({required this.point});

  final Offset point;

  Future<void> _open(BuildContext context, {required bool streetView}) async {
    final open = streetView
        ? openCapturedLocationInGoogleStreetView
        : openCapturedLocationInGoogleMaps;
    final opened = await open(latitude: point.dy, longitude: point.dx);
    if (opened || !context.mounted) return;
    final l10n = AppL10n.of(context);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          streetView
              ? l10n.punchStreetViewOpenFailure
              : l10n.punchGoogleMapsOpenFailure,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppL10n.of(context);
    final style = TextButton.styleFrom(
      foregroundColor: AppColors.brandStrong,
      backgroundColor: AppColors.brandTint,
      minimumSize: const Size.fromHeight(46),
      padding: const EdgeInsets.symmetric(horizontal: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadii.field - 2),
      ),
    );
    return Wrap(
      spacing: AppSpace.x8,
      runSpacing: AppSpace.x4,
      children: [
        TextButton.icon(
          onPressed: () => _open(context, streetView: false),
          icon: const Icon(Icons.open_in_new_rounded, size: 16),
          label: Text(l10n.punchOpenGoogleMaps),
          style: style,
        ),
        TextButton.icon(
          onPressed: () => _open(context, streetView: true),
          icon: const Icon(Icons.streetview_rounded, size: 16),
          label: Text(l10n.punchOpenStreetView),
          style: style,
        ),
      ],
    );
  }
}

String _coordinateText(Offset point) =>
    '${point.dy.toStringAsFixed(6)}, ${point.dx.toStringAsFixed(6)}';

String _credit(bool showsRoads) => showsRoads
    ? 'geoBoundaries / NAMRIA / PSA / OCHA · Roads: Natural Earth'
    : 'geoBoundaries / NAMRIA / PSA / OCHA';

Future<void> _openMap(
  BuildContext context,
  _OfflineMapData data,
  Offset point,
  String title,
  String? address,
) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  useSafeArea: true,
  showDragHandle: true,
  backgroundColor: AppColors.bg,
  builder: (context) {
    final l10n = AppL10n.of(context);
    final expandedBounds = _near(point, latitudeRadius: 0.12);
    final nearbyRoads = data.roadsNear(expandedBounds);
    final municipality = data.municipalityAt(point);
    return SafeArea(
      top: false,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: AppText.appBarTitle.copyWith(fontSize: 20),
                  ),
                ),
                IconButton(
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.close_rounded),
                  tooltip: l10n.punchMapClose,
                ),
              ],
            ),
            GlassSurface(
              blur: 0,
              padding: const EdgeInsets.all(AppSpace.x12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(AppRadii.field),
                    child: SizedBox(
                      height: 290,
                      child: InteractiveViewer(
                        minScale: 1,
                        maxScale: 4,
                        child: Semantics(
                          label: l10n.punchMapCenteredPoint,
                          image: true,
                          child: _MapCanvas(
                            point: point,
                            places: data.placesNear(expandedBounds),
                            roads: nearbyRoads,
                            municipality: municipality,
                            latitudeRadius: 0.045,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: AppSpace.x12),
                  _LocationDetails(
                    point: point,
                    municipality: municipality,
                    address: address,
                  ),
                  const SizedBox(height: AppSpace.x8),
                  Text(l10n.punchMapZoomHelp, style: AppText.meta),
                  const SizedBox(height: AppSpace.x4),
                  Text(_credit(nearbyRoads.isNotEmpty), style: AppText.meta),
                  if (_canOpenGoogleMaps) ...[
                    const SizedBox(height: AppSpace.x8),
                    _GoogleMapsActions(point: point),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  },
);

class _MapCanvas extends StatelessWidget {
  const _MapCanvas({
    required this.point,
    required this.places,
    required this.roads,
    required this.municipality,
    required this.latitudeRadius,
  });

  final Offset point;
  final List<_Place> places;
  final List<_Line> roads;
  final String? municipality;
  final double latitudeRadius;

  @override
  Widget build(BuildContext context) => CustomPaint(
    painter: _MapPainter(
      point: point,
      places: places,
      roads: roads,
      municipality: municipality,
      latitudeRadius: latitudeRadius,
    ),
    child: const SizedBox.expand(),
  );
}

class _MapPainter extends CustomPainter {
  const _MapPainter({
    required this.point,
    required this.places,
    required this.roads,
    required this.municipality,
    required this.latitudeRadius,
  });

  final Offset point;
  final List<_Place> places;
  final List<_Line> roads;
  final String? municipality;
  final double latitudeRadius;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final scale = size.height / (2 * latitudeRadius);
    final longitudeScale = scale * math.cos(point.dy * math.pi / 180);
    final center = size.center(Offset.zero);
    final frame = Offset.zero & size;

    Offset project(Offset p) => Offset(
      center.dx + (p.dx - point.dx) * longitudeScale,
      center.dy - (p.dy - point.dy) * scale,
    );

    void appendLine(Path path, _Line line, {bool close = false}) {
      final start = project(line.points.first);
      path.moveTo(start.dx, start.dy);
      for (final p in line.points.skip(1)) {
        final projected = project(p);
        path.lineTo(projected.dx, projected.dy);
      }
      if (close) path.close();
    }

    canvas.save();
    canvas.clipRect(frame);
    canvas.drawRect(frame, Paint()..color = _mapWater);

    final boundary = Paint()
      ..color = const Color(0xFFA3B9AC)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.85;
    for (final place in places) {
      final path = Path()..fillType = PathFillType.evenOdd;
      for (final polygon in place.polygons) {
        appendLine(path, polygon.outline, close: true);
        for (final hole in polygon.holes) {
          appendLine(path, hole, close: true);
        }
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = place.name == municipality
              ? const Color(0xFFDDE9D2)
              : const Color(0xFFF1F3E8),
      );
      canvas.drawPath(path, boundary);
    }

    final routes = Path();
    for (final road in roads) {
      appendLine(routes, road);
    }
    canvas.drawPath(
      routes,
      Paint()
        ..color = AppColors.surface
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3.3
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );
    canvas.drawPath(
      routes,
      Paint()
        ..color = const Color(0xFF9CACC1)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.35
        ..strokeCap = StrokeCap.round
        ..strokeJoin = StrokeJoin.round,
    );

    canvas.drawCircle(
      center,
      13,
      Paint()..color = AppColors.brandStrong.withValues(alpha: 0.19),
    );
    canvas.drawCircle(center, 7.5, Paint()..color = AppColors.surface);
    canvas.drawCircle(center, 5.1, Paint()..color = AppColors.brandStrong);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _MapPainter oldDelegate) =>
      oldDelegate.point != point ||
      oldDelegate.places != places ||
      oldDelegate.roads != roads ||
      oldDelegate.municipality != municipality ||
      oldDelegate.latitudeRadius != latitudeRadius;
}

Future<String?> _optionalAsset(AssetBundle bundle, String key) async {
  try {
    return await bundle.loadString(key);
  } on FlutterError {
    return null;
  }
}

Future<_OfflineMapData> _loadOfflineMap(AssetBundle bundle) async {
  final assets = await Future.wait([
    _optionalAsset(bundle, _municipalitiesAsset),
    _optionalAsset(bundle, _roadsAsset),
  ]);
  return compute(_parseOfflineMap, (assets[0], assets[1]));
}

Iterable<Map<String, dynamic>> _features(String? source) {
  if (source == null) return const [];
  try {
    final decoded = jsonDecode(source);
    if (decoded is Map<String, dynamic> && decoded['features'] is List) {
      return (decoded['features'] as List).whereType<Map<String, dynamic>>();
    }
  } on FormatException {
    return const [];
  }
  return const [];
}

_OfflineMapData _parseOfflineMap((String?, String?) sources) {
  final places = <_Place>[];
  for (final feature in _features(sources.$1)) {
    final properties = feature['properties'];
    final geometry = feature['geometry'];
    if (properties is! Map || geometry is! Map) continue;
    final rawName = properties['name'] ?? properties['shapeName'];
    if (rawName is! String || rawName.trim().isEmpty) continue;
    final coordinates = geometry['coordinates'];
    if (coordinates is! List) continue;
    final shapes = switch (geometry['type']) {
      'Polygon' => [coordinates],
      'MultiPolygon' => coordinates,
      _ => const [],
    };
    final polygons = shapes.map(_polygon).whereType<_Polygon>().toList();
    if (polygons.isNotEmpty) {
      places.add(_Place(rawName.trim(), polygons));
    }
  }

  final roads = <_Line>[];
  for (final feature in _features(sources.$2)) {
    final geometry = feature['geometry'];
    if (geometry is! Map) continue;
    final coordinates = geometry['coordinates'];
    if (coordinates is! List) continue;
    final lines = switch (geometry['type']) {
      'LineString' => [coordinates],
      'MultiLineString' => coordinates,
      _ => const [],
    };
    roads.addAll(
      lines.map((line) => _line(line, minimum: 2)).whereType<_Line>(),
    );
  }
  return _OfflineMapData(places, roads);
}

Offset? _coordinate(Object? longitude, Object? latitude) {
  if (longitude is! num || latitude is! num) return null;
  if (!longitude.isFinite || !latitude.isFinite) return null;
  if (longitude.abs() > 180 || latitude.abs() > 90) return null;
  return Offset(longitude.toDouble(), latitude.toDouble());
}

_Line? _line(Object? source, {required int minimum}) {
  if (source is! List) return null;
  final points = <Offset>[];
  for (final item in source) {
    if (item is! List || item.length < 2) return null;
    final point = _coordinate(item[0], item[1]);
    if (point == null) return null;
    points.add(point);
  }
  if (points.length < minimum) return null;
  var bounds = Rect.fromPoints(points.first, points.last);
  for (final point in points.skip(1)) {
    bounds = bounds.expandToInclude(Rect.fromPoints(point, point));
  }
  return _Line(points, bounds);
}

_Polygon? _polygon(Object? source) {
  if (source is! List || source.isEmpty) return null;
  final outline = _line(source.first, minimum: 4);
  if (outline == null) return null;
  final holes = <_Line>[];
  for (final ring in source.skip(1)) {
    final hole = _line(ring, minimum: 4);
    if (hole == null) return null;
    holes.add(hole);
  }
  return _Polygon(outline, holes);
}

Rect _near(Offset point, {required double latitudeRadius}) {
  final longitudeRadius =
      latitudeRadius * 3 / math.max(0.01, math.cos(point.dy * math.pi / 180));
  return Rect.fromCenter(
    center: point,
    width: longitudeRadius * 2,
    height: latitudeRadius * 2,
  );
}

bool _covers(Rect bounds, Offset point) =>
    point.dx >= bounds.left &&
    point.dx <= bounds.right &&
    point.dy >= bounds.top &&
    point.dy <= bounds.bottom;

enum _LocationHit { outside, inside, edge }

class _Line {
  const _Line(this.points, this.bounds);

  final List<Offset> points;
  final Rect bounds;

  _LocationHit hit(Offset point) {
    if (!_covers(bounds, point)) return _LocationHit.outside;
    var inside = false;
    var previous = points.last;
    for (final next in points) {
      final dx = next.dx - previous.dx;
      final dy = next.dy - previous.dy;
      if (dx != 0 || dy != 0) {
        final cross =
            (point.dx - previous.dx) * dy - (point.dy - previous.dy) * dx;
        if (cross.abs() <= (dx.abs() + dy.abs()) * 1e-10 &&
            _covers(Rect.fromPoints(previous, next), point)) {
          return _LocationHit.edge;
        }
        if ((previous.dy > point.dy) != (next.dy > point.dy) &&
            point.dx < previous.dx + (point.dy - previous.dy) * dx / dy) {
          inside = !inside;
        }
      }
      previous = next;
    }
    return inside ? _LocationHit.inside : _LocationHit.outside;
  }
}

class _Polygon {
  const _Polygon(this.outline, this.holes);

  final _Line outline;
  final List<_Line> holes;

  _LocationHit hit(Offset point) {
    final outer = outline.hit(point);
    if (outer != _LocationHit.inside) return outer;
    for (final hole in holes) {
      switch (hole.hit(point)) {
        case _LocationHit.edge:
          return _LocationHit.edge;
        case _LocationHit.inside:
          return _LocationHit.outside;
        case _LocationHit.outside:
          continue;
      }
    }
    return _LocationHit.inside;
  }
}

class _Place {
  _Place(this.name, this.polygons)
    : bounds = polygons
          .map((p) => p.outline.bounds)
          .reduce((left, right) => left.expandToInclude(right));

  final String name;
  final List<_Polygon> polygons;
  final Rect bounds;
}

class _OfflineMapData {
  const _OfflineMapData(this.places, this.roads);

  final List<_Place> places;
  final List<_Line> roads;

  List<_Place> placesNear(Rect viewport) =>
      places.where((place) => place.bounds.overlaps(viewport)).toList();

  List<_Line> roadsNear(Rect viewport) =>
      roads.where((road) => road.bounds.overlaps(viewport)).toList();

  String? municipalityAt(Offset point) {
    String? match;
    for (final place in places) {
      if (!_covers(place.bounds, point)) continue;
      if (!place.polygons.any(
        (polygon) => polygon.hit(point) != _LocationHit.outside,
      )) {
        continue;
      }
      if (match != null && match != place.name) return null;
      match = place.name;
    }
    return match;
  }
}

@visibleForTesting
String? municipalityFromGeoJson(
  String geoJson, {
  required double latitude,
  required double longitude,
}) {
  final point = _coordinate(longitude, latitude);
  return point == null
      ? null
      : _parseOfflineMap((geoJson, null)).municipalityAt(point);
}
