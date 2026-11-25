import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sqflite_common/sqlite_api.dart';

import '../../../core/auth/session.dart';
import 'punch_evidence_cipher.dart';
import 'punch_queue_factory.dart';

enum PunchSyncState { pending, synced, review, rejected }

typedef PunchQueueObservation = ({
  int pendingCount,
  DateTime observedAt,
  String? pendingDeviceId,
});

class PunchReceipt {
  const PunchReceipt(
    this.state, {
    this.detectedAddress,
    this.punchedAt,
    this.syncedAt,
  });

  final PunchSyncState state;
  final String? detectedAddress;
  final DateTime? punchedAt;
  final DateTime? syncedAt;
}

class QueuedPunch {
  const QueuedPunch({
    required this.uuid,
    required this.isClockingIn,
    required this.at,
    required this.deviceId,
    required this.latitude,
    required this.longitude,
    required this.selfie,
    this.state = PunchSyncState.pending,
    this.error,
    this.detectedAddress,
    this.punchedAt,
    this.syncedAt,
  });

  final String uuid;
  final bool isClockingIn;
  final DateTime at;
  final String deviceId;
  final double latitude;
  final double longitude;
  final Uint8List? selfie;
  final PunchSyncState state;
  final String? error;
  final String? detectedAddress;

  final DateTime? punchedAt;
  final DateTime? syncedAt;

  DateTime get displayedAt => punchedAt ?? at;

  Map<String, String> get fields => {
    'punch_uuid': uuid,
    'punch_type': isClockingIn ? 'CLOCK_IN' : 'CLOCK_OUT',
    'punched_at': at.toUtc().toIso8601String(),
    'device_id': deviceId,
    'gps_lat': latitude.toStringAsFixed(6),
    'gps_long': longitude.toStringAsFixed(6),
  };

  static DateTime? _timestamp(Object? value) => value is int
      ? DateTime.fromMicrosecondsSinceEpoch(value, isUtc: true)
      : null;

  static QueuedPunch fromRow(
    Map<String, Object?> row, {
    PunchEvidence? evidence,
    String? address,
  }) => QueuedPunch(
    uuid: row['uuid'] as String,
    isClockingIn: row['clock_in'] == 1,
    at: DateTime.fromMicrosecondsSinceEpoch(
      row['punched_at'] as int,
      isUtc: true,
    ),
    deviceId: row['device_id'] as String,
    latitude: evidence?.latitude ?? 0,
    longitude: evidence?.longitude ?? 0,
    selfie: evidence?.selfie,
    state: PunchSyncState.values.byName(row['sync_state'] as String),
    error: row['error'] as String?,
    detectedAddress: address,
    punchedAt: _timestamp(row['confirmed_punch_at']),
    syncedAt: _timestamp(row['synced_at']),
  );
}

String punchQueueAccount(Session session) => sha256
    .convert(utf8.encode('${session.host}\n${session.user.id}'))
    .toString();

abstract interface class PunchQueue {
  Future<void> add(String account, QueuedPunch punch);
  Future<List<QueuedPunch>> pending(String account, {int limit = 5});
  Future<List<QueuedPunch>> recent(String account);
  Future<int> pendingCount(String account);
  Future<DateTime?> lastSuccessfulSync(String account);
  Future<PunchQueueObservation> observePending(String account);
  Future<void> defer(String account, String uuid, String reason);
  Future<void> finish(
    String account,
    String uuid,
    PunchSyncState state, {
    String? error,
    String? detectedAddress,
    DateTime? punchedAt,
    DateTime? syncedAt,
  });
}

class SqlitePunchQueue implements PunchQueue {
  SqlitePunchQueue(this._database, this._cipher);

  final Future<Database> _database;
  final PunchEvidenceCipher _cipher;

  static Future<Database> open(
    DatabaseFactory factory,
    String path,
    PunchEvidenceCipher cipher,
  ) => factory.openDatabase(
    path,
    options: OpenDatabaseOptions(
      version: 3,
      onConfigure: (db) async {
        await db.rawQuery('PRAGMA secure_delete = ON');
      },
      onUpgrade: (db, oldVersion, _) async {
        if (oldVersion < 2) {
          await db.execute(
            'ALTER TABLE punches ADD COLUMN detected_address TEXT',
          );
        }
        if (oldVersion < 3) {
          await db.execute('ALTER TABLE punches ADD COLUMN evidence BLOB');
          await db.execute(
            'ALTER TABLE punches ADD COLUMN protected_address BLOB',
          );
          await db.execute(
            'ALTER TABLE punches ADD COLUMN confirmed_punch_at INTEGER',
          );
          await db.execute('ALTER TABLE punches ADD COLUMN synced_at INTEGER');
          await _sealLegacyEvidence(db, cipher);
        }
      },
      onCreate: (db, _) async {
        await db.execute('''
            CREATE TABLE punches (
              uuid TEXT PRIMARY KEY,
              account TEXT NOT NULL,
              clock_in INTEGER NOT NULL,
              punched_at INTEGER NOT NULL,
              device_id TEXT NOT NULL,
              latitude REAL NOT NULL,
              longitude REAL NOT NULL,
              selfie BLOB,
              sync_state TEXT NOT NULL CHECK (sync_state IN ('pending', 'synced', 'review', 'rejected')),
              error TEXT,
              detected_address TEXT,
              evidence BLOB,
              protected_address BLOB,
              confirmed_punch_at INTEGER,
              synced_at INTEGER
            )
          ''');
        await db.execute(
          'CREATE INDEX punches_account_queue ON punches(account, sync_state, punched_at)',
        );
      },
    ),
  );

  static Future<void> _sealLegacyEvidence(
    Database db,
    PunchEvidenceCipher cipher,
  ) async {
    // Process one bounded batch at a time. onUpgrade is transactional, so a
    // locked key store or interrupted migration leaves the old queue intact.
    const pending = 'pending';
    while (true) {
      final rows = await db.query(
        'punches',
        where: 'sync_state = ? AND evidence IS NULL',
        whereArgs: [pending],
        limit: 5,
      );
      if (rows.isEmpty) break;
      for (final row in rows) {
        final uuid = row['uuid'] as String;
        final account = row['account'] as String;
        final selfie = row['selfie'] as Uint8List?;
        if (selfie == null || selfie.isEmpty) {
          throw const FormatException(
            'Incomplete pending punch in attendance storage',
          );
        }
        final evidence = await cipher.seal(account, uuid, (
          latitude: (row['latitude'] as num).toDouble(),
          longitude: (row['longitude'] as num).toDouble(),
          selfie: selfie,
        ));
        await db.update(
          'punches',
          {'evidence': evidence, 'latitude': 0, 'longitude': 0, 'selfie': null},
          where: 'account = ? AND uuid = ?',
          whereArgs: [account, uuid],
        );
      }
    }
    while (true) {
      final rows = await db.query(
        'punches',
        columns: ['uuid', 'account', 'detected_address'],
        where: 'detected_address IS NOT NULL',
        limit: 20,
      );
      if (rows.isEmpty) break;
      for (final row in rows) {
        final uuid = row['uuid'] as String;
        final account = row['account'] as String;
        final address = row['detected_address'] as String;
        final sealed = address.isEmpty
            ? null
            : await cipher.sealAddress(account, uuid, address);
        await db.update(
          'punches',
          {'detected_address': null, 'protected_address': sealed},
          where: 'account = ? AND uuid = ?',
          whereArgs: [account, uuid],
        );
      }
    }
    await db.update(
      'punches',
      {'latitude': 0, 'longitude': 0, 'selfie': null},
      where: 'sync_state != ?',
      whereArgs: [pending],
    );
  }

  @override
  Future<void> add(String account, QueuedPunch punch) async {
    final selfie = punch.selfie;
    if (selfie == null || selfie.isEmpty) {
      throw const FormatException('A selfie is required for attendance');
    }
    final evidence = await _cipher.seal(account, punch.uuid, (
      latitude: punch.latitude,
      longitude: punch.longitude,
      selfie: selfie,
    ));
    final db = await _database;
    await db.insert('punches', {
      'uuid': punch.uuid,
      'account': account,
      'clock_in': punch.isClockingIn ? 1 : 0,
      'punched_at': punch.at.microsecondsSinceEpoch,
      'device_id': punch.deviceId,
      'latitude': 0,
      'longitude': 0,
      'evidence': evidence,
      'sync_state': punch.state.name,
    });
  }

  @override
  Future<List<QueuedPunch>> pending(String account, {int limit = 5}) async {
    final db = await _database;
    final rows = await db.query(
      'punches',
      where: 'account = ? AND sync_state = ?',
      whereArgs: [account, PunchSyncState.pending.name],
      orderBy: 'punched_at, uuid',
      limit: limit,
    );
    return Future.wait(
      rows.map((row) async {
        final evidence = await _cipher.open(
          account,
          row['uuid'] as String,
          row['evidence'] as Uint8List,
        );
        return QueuedPunch.fromRow(row, evidence: evidence);
      }),
    );
  }

  @override
  Future<List<QueuedPunch>> recent(String account) async {
    final db = await _database;
    final rows = await db.query(
      'punches',
      columns: [
        'uuid',
        'clock_in',
        'punched_at',
        'device_id',
        'confirmed_punch_at',
        'synced_at',
        'sync_state',
        'error',
        'protected_address',
      ],
      where: 'account = ?',
      whereArgs: [account],
      orderBy: 'punched_at DESC, uuid DESC',
      limit: 20,
    );
    return Future.wait(
      rows.map((row) async {
        final sealed = row['protected_address'] as Uint8List?;
        final address = sealed == null
            ? null
            : await _cipher.openAddress(account, row['uuid'] as String, sealed);
        return QueuedPunch.fromRow(row, address: address);
      }),
    );
  }

  @override
  Future<int> pendingCount(String account) async {
    final db = await _database;
    final rows = await db.rawQuery(
      'SELECT COUNT(*) AS count FROM punches WHERE account = ? AND sync_state = ?',
      [account, PunchSyncState.pending.name],
    );
    return rows.single['count'] as int;
  }

  @override
  Future<DateTime?> lastSuccessfulSync(String account) async {
    final db = await _database;
    final rows = await db.rawQuery(
      'SELECT MAX(synced_at) AS last_sync FROM punches WHERE account = ?',
      [account],
    );
    return QueuedPunch._timestamp(rows.single['last_sync']);
  }

  @override
  Future<PunchQueueObservation> observePending(String account) async {
    final db = await _database;
    final rows = await db.rawQuery(
      '''
      SELECT
        COUNT(*) AS count,
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now') AS observed_at,
        CASE WHEN MIN(device_id) = MAX(device_id) THEN MIN(device_id) END AS device_id
      FROM punches
      WHERE account = ? AND sync_state = ?
      ''',
      [account, PunchSyncState.pending.name],
    );
    final row = rows.single;
    return (
      pendingCount: row['count'] as int,
      observedAt: DateTime.parse(row['observed_at'] as String),
      pendingDeviceId: row['device_id'] as String?,
    );
  }

  @override
  Future<void> defer(String account, String uuid, String reason) async {
    final db = await _database;
    await db.update(
      'punches',
      {'error': reason},
      where: 'account = ? AND uuid = ? AND sync_state = ?',
      whereArgs: [account, uuid, PunchSyncState.pending.name],
    );
  }

  @override
  Future<void> finish(
    String account,
    String uuid,
    PunchSyncState state, {
    String? error,
    String? detectedAddress,
    DateTime? punchedAt,
    DateTime? syncedAt,
  }) async {
    if (state == PunchSyncState.pending) {
      throw ArgumentError.value(
        state,
        'state',
        'Use defer to preserve the evidence',
      );
    }
    final address = detectedAddress == null
        ? null
        : await _cipher.sealAddress(account, uuid, detectedAddress);
    final db = await _database;
    await db.update(
      'punches',
      {
        'sync_state': state.name,
        'error': error,
        'protected_address': address,
        'evidence': null,
        'confirmed_punch_at': punchedAt?.microsecondsSinceEpoch,
        'synced_at': syncedAt?.microsecondsSinceEpoch,
      },
      where: 'account = ? AND uuid = ? AND sync_state = ?',
      whereArgs: [account, uuid, PunchSyncState.pending.name],
    );
  }
}

final punchQueueProvider = Provider<PunchQueue>((ref) => makePunchQueue());

final recentPunchesProvider = FutureProvider<List<QueuedPunch>>((ref) {
  final session = ref.watch(sessionProvider);
  if (session == null || session.user.id <= 0) return Future.value([]);
  return ref.watch(punchQueueProvider).recent(punchQueueAccount(session));
});

final pendingPunchCountProvider = FutureProvider<int>((ref) {
  final session = ref.watch(sessionProvider);
  if (session == null || session.user.id <= 0) return Future.value(0);
  return ref.watch(punchQueueProvider).pendingCount(punchQueueAccount(session));
});

final lastSuccessfulPunchSyncProvider = FutureProvider<DateTime?>((ref) {
  final session = ref.watch(sessionProvider);
  if (session == null || session.user.id <= 0) return Future.value(null);
  return ref
      .watch(punchQueueProvider)
      .lastSuccessfulSync(punchQueueAccount(session));
});
