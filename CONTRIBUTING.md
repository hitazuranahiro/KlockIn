# Contributing to KlockIN by Tomeku

Report product bugs and suggest features in the issue tracker for this repository. For security issues, [contact the Tomeku project administrator privately](SECURITY.md).

## Make a change

1. Follow the local setup guide and use a disposable development database for tests. [KlockIN setup](README.md)
2. Make the change in a topic branch and keep the diff focused.
3. Run the checks appropriate to the change.

   ```bash
   python manage.py check
   python manage.py test klockin_attendance --noinput
   ```

   For mobile code, run `flutter analyze` and `flutter test` from `mobile/app`.

4. Open a pull request against the project's active development branch. Describe the problem, the change, and the checks you ran. If an existing installation needs a migration or change in settings, include that in the pull request.

Follow the repository's Python and Flutter formatting and reuse existing permission and company-scoping helpers. Keep original license and attribution information with inherited source. [Source notices](docs/klockin-source-notices.md)
