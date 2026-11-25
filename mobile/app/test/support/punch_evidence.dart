import 'package:cryptography/cryptography.dart';
import 'package:klockin/features/punch/data/punch_evidence_cipher.dart';

final testPunchCipher = PunchEvidenceCipher(
  () async => SecretKey(List<int>.generate(32, (index) => index)),
);
