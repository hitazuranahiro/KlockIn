import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:klockin/features/punch/data/punch_queue.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../../support/punch_evidence.dart';

void main() {
  test(
    'unsynced rows persist, are ordered, and stay scoped to the account',
    () async {
      sqfliteFfiInit();
      final dir = await Directory.systemTemp.createTemp('klockin-punch-test-');
      addTearDown(() => dir.delete(recursive: true));
      final path = '${dir.path}/punches.sqlite';
      var db = await SqlitePunchQueue.open(
        databaseFactoryFfi,
        path,
        testPunchCipher,
      );
      var queue = SqlitePunchQueue(Future.value(db), testPunchCipher);

      final selfie = Uint8List.fromList([1, 2, 3]);
      QueuedPunch punch(String uuid, int hour) => QueuedPunch(
        uuid: uuid,
        isClockingIn: hour == 8,
        at: DateTime.utc(2026, 11, 25, hour),
        deviceId: 'device-id',
        latitude: 14.5,
        longitude: 121.0,
        selfie: selfie,
      );

      await queue.add('a', punch('late', 9));
      await queue.add('a', punch('early', 8));
      await queue.add('b', punch('other', 8));
      await db.close();

      db = await SqlitePunchQueue.open(
        databaseFactoryFfi,
        path,
        testPunchCipher,
      );
      addTearDown(db.close);
      queue = SqlitePunchQueue(Future.value(db), testPunchCipher);
      final pending = await queue.pending('a');
      expect(await db.getVersion(), 3);
      expect(pending.map((punch) => punch.uuid), ['early', 'late']);
      expect(pending.first.selfie, selfie);
      final stored = (await db.query(
        'punches',
        where: 'uuid = ?',
        whereArgs: ['early'],
      )).single;
      expect(stored['selfie'], isNull);
      expect(stored['latitude'], 0);
      expect(stored['longitude'], 0);
      expect(stored['evidence'], isA<Uint8List>());
      expect(stored['evidence'], isNot(selfie));
      expect(
        pending.first.fields,
        containsPair('punched_at', '2026-11-25T08:00:00.000Z'),
      );
      expect(pending.first.fields, containsPair('gps_long', '121.000000'));
      await queue.finish('b', 'early', PunchSyncState.synced);
      expect(await queue.pendingCount('a'), 2);
      final syncedAt = DateTime.utc(2026, 11, 26, 8);
      final serverPunchAt = DateTime.utc(2026, 11, 25, 8, 1);
      await queue.finish(
        'a',
        'early',
        PunchSyncState.synced,
        detectedAddress: 'Makati, Metro Manila',
        punchedAt: serverPunchAt,
        syncedAt: syncedAt,
      );
      expect(await queue.lastSuccessfulSync('a'), syncedAt);
      expect(await queue.lastSuccessfulSync('b'), isNull);
      await queue.finish(
        'a',
        'early',
        PunchSyncState.rejected,
        error: 'late conflicting response',
      );
      final receipt = (await db.query(
        'punches',
        where: 'uuid = ?',
        whereArgs: ['early'],
      )).single;
      expect(receipt['sync_state'], 'synced');
      expect(receipt['selfie'], isNull);
      expect(receipt['evidence'], isNull);
      expect(receipt['detected_address'], isNull);
      expect(receipt['protected_address'], isA<Uint8List>());
      final recent = await queue.recent('a');
      expect(
        recent.where((punch) => punch.uuid == 'early').single.detectedAddress,
        'Makati, Metro Manila',
      );
      expect(
        recent.where((punch) => punch.uuid == 'early').single.displayedAt,
        serverPunchAt,
      );
      expect(await queue.pendingCount('a'), 1);
    },
  );
  test(
    'upgrading the legacy queue encrypts existing unsynced evidence',
    () async {
      sqfliteFfiInit();
      final dir = await Directory.systemTemp.createTemp(
        'klockin-legacy-punch-test-',
      );
      addTearDown(() => dir.delete(recursive: true));
      final path = '${dir.path}/punches.sqlite';
      final legacy = await databaseFactoryFfi.openDatabase(
        path,
        options: OpenDatabaseOptions(
          version: 1,
          onCreate: (db, _) => db.execute('''
        CREATE TABLE punches (uuid TEXT PRIMARY KEY, account TEXT NOT NULL,
          clock_in INTEGER NOT NULL, punched_at INTEGER NOT NULL, device_id TEXT NOT NULL,
          latitude REAL NOT NULL, longitude REAL NOT NULL, selfie BLOB,
          sync_state TEXT NOT NULL, error TEXT)
      '''),
        ),
      );
      final image = Uint8List.fromList([18, 23, 38, 54]);
      await legacy.insert('punches', {
        'uuid': 'existing',
        'account': 'a',
        'clock_in': 1,
        'punched_at': 1,
        'device_id': 'phone',
        'latitude': 14.54321,
        'longitude': 121.098765,
        'selfie': image,
        'sync_state': 'pending',
      });
      await legacy.close();
      final db = await SqlitePunchQueue.open(
        databaseFactoryFfi,
        path,
        testPunchCipher,
      );
      addTearDown(db.close);
      final actual = (await db.query('punches')).single;
      expect(actual['selfie'], isNull);
      expect(actual['latitude'], 0);
      expect(actual['longitude'], 0);
      final queue = SqlitePunchQueue(Future.value(db), testPunchCipher);
      final restored = (await queue.pending('a')).single;
      expect(restored.selfie, image);
      expect(restored.latitude, 14.54321);
      expect(restored.longitude, 121.098765);
      final tampered = Uint8List.fromList(actual['evidence'] as Uint8List);
      tampered[17] ^= 1;
      await db.update('punches', {'evidence': tampered});
      await expectLater(queue.pending('a'), throwsException);
      expect(await queue.pendingCount('a'), 1);
    },
  );
}
