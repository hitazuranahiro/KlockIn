import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_primitives.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../shared/widgets/error_state_card.dart';
import '../../../shared/widgets/pressable.dart';
import '../data/employee_api.dart';
import '../data/employee_models.dart';
import 'profile_sheet.dart';

class DirectoryScreen extends ConsumerStatefulWidget {
  const DirectoryScreen({super.key});

  @override
  ConsumerState<DirectoryScreen> createState() => _DirectoryScreenState();
}

class _DirectoryScreenState extends ConsumerState<DirectoryScreen> {
  final _controller = TextEditingController();
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  /// Search hits the server, so it waits for a pause in typing rather than
  /// firing a request per keystroke.
  void _onChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      ref.read(directorySearchProvider.notifier).update(value.trim());
    });
  }

  @override
  Widget build(BuildContext context) {
    final directory = ref.watch(directoryProvider);
    final navigator = Navigator.of(context);
    final canPop = navigator.canPop();

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          AppTopBar(
            title: canPop ? 'Directory' : 'People',
            onBack: canPop ? navigator.pop : null,
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpace.screen,
              AppSpace.x6,
              AppSpace.screen,
              AppSpace.x4,
            ),
            child: TextField(
              controller: _controller,
              onChanged: _onChanged,
              textInputAction: TextInputAction.search,
              style: AppText.body.copyWith(fontSize: 15),
              decoration: InputDecoration(
                filled: true,
                fillColor: AppColors.surface,
                prefixIcon: const Icon(
                  Icons.search,
                  size: 20,
                  color: AppColors.ink3,
                ),
                hintText: 'Search by name',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(AppRadii.field),
                  borderSide: const BorderSide(color: AppColors.line),
                ),
              ),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              color: AppColors.brandStrong,
              onRefresh: () async => ref.refresh(directoryProvider.future),
              child: _body(directory),
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(AsyncValue<List<DirectoryEntry>> directory) {
    final people = directory.value;
    if (people != null) {
      return _DirectoryList(
        people: people,
        searching: _controller.text.trim().isNotEmpty,
      );
    }

    final error = directory.error;
    if (error != null) {
      return ErrorStateCard(
        failure: error is ApiFailure ? error : const ApiUnknown(),
        onRetry: () => ref.invalidate(directoryProvider),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(AppSpace.screen),
      children: const [
        AppCard.skeleton(height: 72),
        SizedBox(height: AppSpace.x10),
        AppCard.skeleton(height: 72),
        SizedBox(height: AppSpace.x10),
        AppCard.skeleton(height: 72),
      ],
    );
  }
}

class _DirectoryList extends StatelessWidget {
  const _DirectoryList({required this.people, required this.searching});

  final List<DirectoryEntry> people;
  final bool searching;

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(
        AppSpace.screen,
        AppSpace.x20,
        AppSpace.screen,
        AppSpace.scrollBottom,
      ),
      children: [
        if (searching) ...[
          const SectionHeader(title: 'Search results'),
          const SizedBox(height: AppSpace.x6),
        ],
        if (people.isEmpty)
          Text(
            searching
                ? 'No matches. Try a first name or last name.'
                : 'No people are visible in your directory yet.',
            style: AppText.body,
          )
        else ...[
          Text(
            '${people.length} ${people.length == 1 ? 'person' : 'people'}',
            style: AppText.meta,
          ),
          if (people.length == 1) ...[
            const SizedBox(height: AppSpace.x8),
            const Text(
              'Ask your administrator if you expect to see colleagues here.',
              style: AppText.meta,
            ),
          ],
          const SizedBox(height: AppSpace.x12),
          for (final person in people) ...[
            const Divider(height: 1, color: AppColors.line),
            _PersonRow(person: person),
          ],
          const Divider(height: 1, color: AppColors.line),
        ],
      ],
    );
  }
}

class _PersonRow extends StatelessWidget {
  const _PersonRow({required this.person});

  final DirectoryEntry person;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label:
          '${person.fullName}'
          '${person.jobPosition == null ? '' : ', ${person.jobPosition}'}',
      excludeSemantics: true,
      child: Pressable(
        scale: 0.99,
        onTap: () => showProfileSheet(context, person),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpace.x4,
            vertical: AppSpace.x12,
          ),
          child: Row(
            children: [
              AppAvatar.toned(name: person.fullName, size: 38),
              const SizedBox(width: AppSpace.x12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      person.fullName,
                      style: AppText.cardTitle.copyWith(fontSize: 14.5),
                    ),
                    if (person.jobPosition != null) ...[
                      const SizedBox(height: 2),
                      Text(person.jobPosition!, style: AppText.meta),
                    ],
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, size: 18, color: AppColors.ink4),
            ],
          ),
        ),
      ),
    );
  }
}
