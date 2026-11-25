// Modified for KlockIN by Tomeku, 2026-11-25.
/// Turning what someone typed into a base URL.
///
/// People type `hr.company.com`, `HR.Company.com/`, `http://192.168.1.9:8000`
/// and `https://hr.company.com/site/api/v1/`. Getting
/// this wrong surfaces later as a confusing auth error, so it is normalised
/// once, here, and tested.
library;

/// Cleartext policy.
///
/// `http://` is permitted, but only for private addresses — LAN and
/// `.local` self-hosted installs, which are a real part of this product's
/// deployment story. Allowing it for *any* host a user types would not be a
/// concession, it would be a hole: every token and payslip in the clear on
/// whatever network they happen to be on.
class HostNormalisationResult {
  const HostNormalisationResult._({
    required this.host,
    required this.isCleartext,
  }) : error = null;

  const HostNormalisationResult.failure(String message)
    : host = '',
      isCleartext = false,
      error = message;

  /// Normalised server base, e.g. `https://hr.company.com/site`.
  final String host;

  /// True when this resolves to plain `http://`, so the UI can warn.
  final bool isCleartext;

  final String? error;

  bool get isValid => error == null;
}

/// RFC1918 and friends, plus `.local` and loopback.
bool isPrivateHost(String hostname) {
  final name = hostname.toLowerCase();
  if (name == 'localhost' || name == '::1' || name.endsWith('.local'))
    return true;

  final parts = name.split('.');
  if (parts.length != 4) return false;
  final octets = parts.map(int.tryParse).toList();
  if (octets.any((o) => o == null || o < 0 || o > 255)) return false;

  final [a!, b!, _, _] = octets;
  if (a == 10) return true;
  if (a == 127) return true;
  if (a == 192 && b == 168) return true;
  if (a == 172 && b >= 16 && b <= 31) return true;
  // Link-local.
  if (a == 169 && b == 254) return true;
  return false;
}

HostNormalisationResult normaliseHost(String input) {
  var text = input.trim();
  if (text.isEmpty) {
    return const HostNormalisationResult.failure('Enter your server address.');
  }

  // Default to https. Never silently downgrade.
  if (!text.contains('://')) text = 'https://$text';

  final uri = Uri.tryParse(text);
  if (uri == null ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.hasPort && (uri.port <= 0 || uri.port > 65535))) {
    return const HostNormalisationResult.failure(
      "That doesn't look like a server address.",
    );
  }

  final scheme = uri.scheme.toLowerCase();
  if (scheme != 'http' && scheme != 'https') {
    return const HostNormalisationResult.failure('Use http:// or https://');
  }

  if (scheme == 'http' && !isPrivateHost(uri.host)) {
    return const HostNormalisationResult.failure(
      'Public servers must use https:// — http is only allowed on a local '
      'network.',
    );
  }

  final port = uri.hasPort ? ':${uri.port}' : '';
  final name = uri.host.toLowerCase();
  final hostname = name.contains(':') ? '[$name]' : name;
  final segments = uri.pathSegments.toList();
  while (segments.isNotEmpty && segments.last.isEmpty) {
    segments.removeLast();
  }
  final version = RegExp(r'^v[0-9]+$');
  if (segments.length >= 2 &&
      segments[segments.length - 2] == 'api' &&
      version.hasMatch(segments.last)) {
    segments.removeLast();
  }
  if (segments.isNotEmpty && segments.last == 'api') segments.removeLast();

  // Deployment prefixes are path segments, never nested URLs or query data.
  final validSegment = RegExp(r'^[A-Za-z0-9_~.-]+$');
  if (segments.any(
    (segment) =>
        !validSegment.hasMatch(segment) || segment == '.' || segment == '..',
  )) {
    return const HostNormalisationResult.failure(
      'Enter the KlockIN server base URL.',
    );
  }
  final prefix = segments.isEmpty ? '' : '/${segments.join('/')}';
  return HostNormalisationResult._(
    host: '$scheme://$hostname$port$prefix',
    isCleartext: scheme == 'http',
  );
}

/// Limit authentication to the selected origin and deployed KlockIN instance.
bool isWithinServerBase(Uri target, String base) {
  final server = Uri.tryParse(base);
  return server != null &&
      server.hasAuthority &&
      target.hasAuthority &&
      target.userInfo.isEmpty &&
      (target.scheme == 'https' || target.scheme == 'http') &&
      target.origin == server.origin &&
      target.pathSegments.every(
        (segment) =>
            segment != '.' &&
            segment != '..' &&
            !segment.contains('/') &&
            !segment.contains('\\'),
      ) &&
      (server.path.isEmpty ||
          server.path == '/' ||
          target.path == server.path ||
          target.path.startsWith('${server.path}/'));
}
