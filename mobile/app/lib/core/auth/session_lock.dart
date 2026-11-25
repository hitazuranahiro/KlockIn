import 'package:flutter/foundation.dart';
import 'package:sqflite/sqflite.dart';

/// Serializes changes to the single secure-storage session slot.
abstract interface class SessionLock {
  Future<T> run<T>(Future<T> Function() action);
}

class MemorySessionLock implements SessionLock {
  Future<void> _tail = Future<void>.value();

  @override
  Future<T> run<T>(Future<T> Function() action) {
    final result = _tail.then((_) => action());
    _tail = result.then<void>((_) {}, onError: (Object _, StackTrace _) {});
    return result;
  }
}

/// The same database path coordinates independent foreground and background
/// Flutter engines. The database contains only SQLite's lock, never tokens.
class SqliteSessionLock implements SessionLock {
  SqliteSessionLock({
    required this.factory,
    required this.databasePath,
    this.waitLimit = const Duration(seconds: 55),
  });

  final DatabaseFactory factory;
  final Future<String> Function() databasePath;
  final Duration waitLimit;

  @override
  Future<T> run<T>(Future<T> Function() action) async {
    final path = await databasePath();
    final stopwatch = Stopwatch()..start();
    while (true) {
      Database? database;
      var entered = false;
      try {
        database = await factory.openDatabase(
          path,
          options: OpenDatabaseOptions(
            singleInstance: false,
            // Wait in Dart so we never pin a native SQLite worker needed by
            // the engine that is finishing the current transaction.
            onConfigure: (db) async {
              await db.rawQuery('PRAGMA busy_timeout = 0');
            },
          ),
        );
        return await database.transaction((_) {
          entered = true;
          return action();
        }, exclusive: false);
      } on DatabaseException catch (error) {
        final details = error.toString().toLowerCase();
        final busy =
            details.contains('database is locked') ||
            details.contains('database table is locked') ||
            details.contains('sqlite_busy') ||
            details.contains('sqlite_locked');
        if (entered || !busy || stopwatch.elapsed >= waitLimit) rethrow;
      } finally {
        await database?.close();
      }
      await Future<void>.delayed(const Duration(milliseconds: 80));
    }
  }
}

SessionLock makeSessionLock() {
  if (kIsWeb ||
      (defaultTargetPlatform != TargetPlatform.android &&
          defaultTargetPlatform != TargetPlatform.iOS)) {
    return MemorySessionLock();
  }
  return SqliteSessionLock(
    factory: databaseFactory,
    databasePath: () async =>
        '${await getDatabasesPath()}/klockin-session-lock.sqlite',
  );
}
