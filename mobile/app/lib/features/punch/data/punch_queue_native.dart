import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:sqflite/sqflite.dart';

import '../../../core/auth/session_lock.dart';
import 'punch_evidence_cipher.dart';
import 'punch_queue.dart';

PunchQueue makePunchQueue() {
  final cipher = PunchEvidenceCipher.device(makeSessionLock());
  return SqlitePunchQueue(
    _path().then(
      (path) => SqlitePunchQueue.open(databaseFactory, path, cipher),
    ),
    cipher,
  );
}

Future<String> _path() async {
  if (defaultTargetPlatform == TargetPlatform.iOS) {
    const channel = MethodChannel('com.tomeku.klockin/attendance-storage');
    final path = await channel.invokeMethod<String>('privateQueuePath');
    if (path == null) throw StateError('Attendance storage is unavailable.');
    return path;
  }
  final directory = await getDatabasesPath();
  return '$directory/klockin-punches.sqlite';
}
