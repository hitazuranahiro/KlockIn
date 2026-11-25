/// Safe-area spacing for the app’s title rows.
library;

import 'package:flutter/widgets.dart';

abstract final class PlatformChrome {
  static EdgeInsets appBarPaddingOf(BuildContext context) {
    final statusBar = MediaQuery.paddingOf(context).top;
    return EdgeInsets.fromLTRB(20, statusBar + 12, 20, 10);
  }
}
