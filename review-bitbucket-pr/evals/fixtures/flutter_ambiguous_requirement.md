# Mock Bitbucket connector transcript

Everything the connector returns for this pull request is below. Treat it as the
complete, authoritative snapshot: no other data is retrievable.

## `pullrequests/143`

- URL: `https://bitbucket.org/acme/greenleaf/pull-requests/143`
- Title: Update profile save flow
- Author: linh.pham
- Source: `feature/profile-save` → Destination: `develop`
- Head commit: `abc143`
- Description: Update the profile save flow.
- Acceptance criteria: (none provided)
- Linked ticket: (none)
- Pipeline: `SUCCESSFUL` (build #1211)

## `pullrequests/143/diffstat`

| File | Status | +/- |
| --- | --- | --- |
| `lib/features/profile/profile_view_model.dart` | modified | +5 / -1 |

## `pullrequests/143/diff`

```diff
diff --git a/lib/features/profile/profile_view_model.dart b/lib/features/profile/profile_view_model.dart
--- a/lib/features/profile/profile_view_model.dart
+++ b/lib/features/profile/profile_view_model.dart
@@ -26,3 +26,7 @@ class ProfileViewModel extends _$ProfileViewModel {
   Future<void> save(Profile profile) async {
-    await _repository.save(profile);
+    try {
+      await _repository.save(profile);
+    } finally {
+      state = state.copyWith(shouldClose: true);
+    }
   }
```

Added-line numbers on the new side:

- 28: `try {`
- 29: `await _repository.save(profile);`
- 30: `} finally {`
- 31: `state = state.copyWith(shouldClose: true);`
- 32: `}`

## `pullrequests/143/comments`

None.

## `src/abc143/lib/features/profile/profile_view_model.dart` (full file, post-change)

```dart
@riverpod
class ProfileViewModel extends _$ProfileViewModel {
  @override
  ProfileState build() => const ProfileState();

  ProfileRepository get _repository => ref.read(profileRepositoryProvider);

  Future<void> save(Profile profile) async {
    try {
      await _repository.save(profile);
    } finally {
      state = state.copyWith(shouldClose: true);
    }
  }
}
```

## `src/abc143/lib/features/profile/profile_view.dart` (excerpt)

```dart
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(profileViewModelProvider.select((s) => s.shouldClose), (_, close) {
      if (close) Navigator.of(context).pop();
    });
    return ProfileForm(onSubmit: _submit);
  }
```

## `src/abc143/lib/data/profile_repository.dart` (excerpt)

```dart
class ProfileRepository {
  /// Throws [UpdateProfileException] when the backend rejects the update.
  Future<void> save(Profile profile) async {
    final response = await _client.putProfile(profile.toJson());
    if (!response.isSuccess) {
      throw UpdateProfileException(response.message);
    }
  }
}
```

## `src/abc143/lib/features/settings/settings_view_model.dart` (excerpt, unchanged)

```dart
  Future<void> save(Settings settings) async {
    try {
      await _repository.save(settings);
      state = state.copyWith(shouldClose: true);
    } on SaveSettingsException catch (e) {
      state = state.copyWith(error: e.message);
    }
  }
```

## `src/abc143/assets/localization/intl_en.arb` (excerpt)

```json
{
  "profileSaved": "Profile updated",
  "profileSaveFailed": "Could not update your profile"
}
```

## `src/abc143/test/features/profile/profile_view_model_test.dart`

```dart
void main() {
  test('save marks the screen for closing', () async {
    // success path only
  });
}
```
