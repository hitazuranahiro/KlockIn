import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_failure.dart';
import '../../../core/theme/tokens.dart';
import '../../../shared/widgets/app_button.dart';
import '../../../shared/widgets/app_card.dart';
import '../../../shared/widgets/app_primitives.dart';
import '../../../shared/widgets/app_top_bar.dart';
import '../../../shared/widgets/error_state_card.dart';
import '../../../shared/widgets/toast.dart';
import '../data/export_api.dart';
import '../data/export_models.dart';
import 'export_preview_screen.dart';

Future<void> openDocumentExport(BuildContext context, ExportTarget target) =>
    Navigator.of(context).push<void>(
      MaterialPageRoute(builder: (_) => ExportScreen(target: target)),
    );

enum _ExportAction { save, preview }

class ExportScreen extends ConsumerStatefulWidget {
  const ExportScreen({super.key, required this.target});

  final ExportTarget target;

  @override
  ConsumerState<ExportScreen> createState() => _ExportScreenState();
}

class _ExportScreenState extends ConsumerState<ExportScreen> {
  final _note = TextEditingController();

  ExportSettings? _draft;
  String _savedNote = '';
  ApiFailure? _loadError;
  String? _actionError;
  _ExportAction? _action;

  bool get _busy => _action != null;

  bool get _noteNeedsSaving =>
      _draft?.showNotes == true && _note.text.trim() != _savedNote;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (_loadError != null) setState(() => _loadError = null);
    try {
      final saved = await ref
          .read(exportApiProvider)
          .fetchSettings(widget.target.type);
      if (!mounted) return;
      setState(() {
        _draft = saved;
        _savedNote = saved.note.trim();
        _note.text = saved.note;
      });
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _loadError = failure);
    }
  }

  void _change(ExportSettings settings) {
    setState(() {
      _draft = settings;
      _actionError = null;
    });
  }

  Future<void> _run(_ExportAction action) async {
    final draft = _draft;
    if (_busy ||
        draft == null ||
        (action == _ExportAction.preview && _noteNeedsSaving)) {
      return;
    }

    setState(() {
      _action = action;
      _actionError = null;
    });

    final api = ref.read(exportApiProvider);
    try {
      if (action == _ExportAction.save) {
        final saved = await api.saveSettings(
          widget.target.type,
          draft.copyWith(note: _note.text.trim()),
        );
        if (!mounted) return;
        setState(() {
          _draft = saved;
          _savedNote = saved.note.trim();
          if (_note.text != saved.note) _note.text = saved.note;
        });
        ref.read(toastProvider.notifier).show('Export preferences saved');
      } else {
        final document = await api.fetchPdf(widget.target, draft);
        if (!mounted) return;
        await Navigator.of(context).push<void>(
          MaterialPageRoute(
            builder: (_) =>
                ExportPreviewScreen(target: widget.target, document: document),
          ),
        );
      }
    } on ApiFailure catch (failure) {
      if (mounted) setState(() => _actionError = failure.message);
    } finally {
      if (mounted) setState(() => _action = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final type = widget.target.type;
    final draft = _draft;
    final loadError = _loadError;

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Column(
        children: [
          AppTopBar(
            title: '${type.label} PDF',
            onBack: ModalRoute.canPopOf(context) == true
                ? () => Navigator.maybePop(context)
                : null,
          ),
          Expanded(
            child: switch ((draft, loadError)) {
              (final settings?, _) => _form(type, settings),
              (_, final failure?) => ErrorStateCard(
                failure: failure,
                onRetry: _load,
              ),
              _ => const Center(child: CircularProgressIndicator()),
            },
          ),
          if (draft != null)
            SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.all(AppSpace.screen),
                child: Column(
                  children: [
                    AppButton(
                      label: _action == _ExportAction.preview
                          ? 'Opening PDF…'
                          : 'Preview PDF',
                      onPressed: _busy || _noteNeedsSaving
                          ? null
                          : () => _run(_ExportAction.preview),
                    ),
                    const SizedBox(height: AppSpace.x6),
                    TextButton(
                      onPressed: _busy ? null : () => _run(_ExportAction.save),
                      child: Text(
                        _action == _ExportAction.save
                            ? 'Saving…'
                            : 'Save as default',
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _form(ExportDocumentType type, ExportSettings draft) => ListView(
    padding: const EdgeInsets.fromLTRB(
      AppSpace.screen,
      AppSpace.x18,
      AppSpace.screen,
      AppSpace.x18,
    ),
    children: [
      if (_actionError != null) ...[
        Semantics(
          liveRegion: true,
          child: AppCard(
            background: AppColors.dangerBg,
            borderColor: AppColors.dangerBorder,
            child: Text(
              _actionError!,
              style: AppText.body.copyWith(color: AppColors.danger),
            ),
          ),
        ),
        const SizedBox(height: AppSpace.x14),
      ],
      Text(widget.target.formattedPeriod, style: AppText.cardTitle),
      const SizedBox(height: AppSpace.x18),
      _choices('Layout', type.layouts, draft.layout, (value) {
        _change(draft.copyWith(layout: value));
      }),
      if (type == ExportDocumentType.dtr) ...[
        const SizedBox(height: AppSpace.x14),
        _choices(
          'Orientation',
          ExportSettings.orientations,
          draft.orientation,
          (value) {
            _change(draft.copyWith(orientation: value));
          },
        ),
      ],
      const SizedBox(height: AppSpace.x14),
      AppCard(
        padding: const EdgeInsets.symmetric(horizontal: AppSpace.x14),
        child: Material(
          type: MaterialType.transparency,
          child: Column(
            children: [
              _toggle('Show company details', draft.showCompany, (value) {
                _change(draft.copyWith(showCompany: value));
              }),
              _toggle('Show notes', draft.showNotes, (value) {
                _change(draft.copyWith(showNotes: value));
              }),
              if (type == ExportDocumentType.dtr)
                _toggle('Show undertime', draft.showUndertime, (value) {
                  _change(draft.copyWith(showUndertime: value));
                }),
            ],
          ),
        ),
      ),
      if (draft.showNotes) ...[
        const SizedBox(height: AppSpace.x14),
        TextField(
          controller: _note,
          enabled: !_busy,
          maxLength: ExportSettings.maxNoteLength,
          maxLines: 2,
          style: AppText.body,
          decoration: const InputDecoration(
            labelText: 'PDF note',
            hintText: 'Optional note to include in this export',
            border: OutlineInputBorder(),
          ),
          onChanged: (_) => setState(() => _actionError = null),
        ),
        if (_noteNeedsSaving)
          const Text(
            'Save as default to include the edited note in your PDF.',
            style: AppText.meta,
          ),
      ],
    ],
  );

  Widget _toggle(String label, bool selected, ValueChanged<bool> change) =>
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(label, style: AppText.body),
        value: selected,
        onChanged: _busy ? null : change,
      );

  Widget _choices(
    String label,
    Map<String, String> choices,
    String value,
    ValueChanged<String> change,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      EyebrowLabel(label),
      const SizedBox(height: AppSpace.x6),
      Wrap(
        spacing: AppSpace.x8,
        runSpacing: AppSpace.x6,
        children: [
          for (final choice in choices.entries)
            ChoiceChip(
              label: Text(choice.value),
              selected: choice.key == value,
              onSelected: _busy ? null : (_) => change(choice.key),
            ),
        ],
      ),
    ],
  );
}
