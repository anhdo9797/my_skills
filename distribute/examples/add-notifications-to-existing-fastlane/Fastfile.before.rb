# A project's existing Fastfile, before the skill touches it.
#
# It already builds, signs, and uploads. That part works and stays exactly as it
# is — the integration adds a step after the upload, and nothing else.

default_platform(:android)

platform :android do
  desc "Build and upload to Firebase App Distribution"
  lane :beta do
    gradle(task: "clean assembleRelease")

    firebase_app_distribution(
      app: ENV["FIREBASE_APP_ID"],
      groups: "qa-team",
      release_notes_file: "release_notes.txt"
    )
  end
end
