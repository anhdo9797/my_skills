# The same Fastfile after the integration.
#
# Three additions, marked below. The build and upload steps are byte-identical
# to Fastfile.before.rb: a release pipeline that already works is the last thing
# to rewrite while adding notifications to it.

# (1) Requires for running the scripts and parsing their JSON.
require "json"
require "open3"
require "shellwords"

default_platform(:android)

# (2) Two helpers. Keep them near the top of the Fastfile or in a separate file
#     the Fastfile imports.

# Runs a Fastlane-owned release script and keeps JSON stdout separate from logs.
#
# `sh` is avoided deliberately: Fastlane decorates its output, and the Notion
# publisher's stdout has to stay parseable JSON.
def run_release_notification_script(script_name, arguments)
  script_path = File.join(__dir__, script_name)
  UI.user_error!("Release script not found: #{script_path}") unless File.file?(script_path)

  command = ["bash", script_path] + arguments.map(&:to_s)
  UI.command(command.shelljoin)
  stdout, stderr, status = Open3.capture3(*command)
  stderr.each_line do |line|
    UI.command_output(line.strip) unless line.strip.empty?
  end

  return stdout if status.success?

  output = [stdout, stderr].reject(&:empty?).join
  UI.user_error!(
    "Release notification failed with exit status #{status.exitstatus}.\n#{output}"
  )
end

# Publishes the Notion release page, then announces it on Discord.
#
# Notion runs first because Discord needs the page URL, the assignee list, and
# the backlog it produces. A failure here means the build already shipped, so
# the error must not read as a build failure.
def publish_release_notifications(platform:, version:, build_number:)
  release_notes_path = File.expand_path("../release_notes.txt", __dir__)
  UI.user_error!("Release notes not found: #{release_notes_path}") unless File.file?(release_notes_path)

  environment = Fastlane::Actions.lane_context[
    Fastlane::Actions::SharedValues::ENVIRONMENT
  ].to_s
  UI.user_error!("Pass --env to select an environment.") if environment.empty?
  environment = {"dev" => "Development", "prod" => "Production"}.fetch(environment, environment)

  notion_output = run_release_notification_script(
    "publish_notion_release.sh",
    [
      "--input", release_notes_path,
      "--platform", platform,
      "--version", version,
      "--build-number", build_number,
      "--environment", environment
    ]
  )

  begin
    notion_result = JSON.parse(notion_output)
  rescue JSON::ParserError => error
    UI.user_error!("Notion publisher returned invalid JSON: #{error.message}")
  end

  UI.user_error!("Notion publication failed.") unless notion_result["success"] == true

  release_page_url = notion_result["release_page_url"].to_s
  UI.user_error!("Notion publication did not return a release page URL.") if release_page_url.empty?

  run_release_notification_script(
    "send_discord_release_notification.sh",
    [
      "--release-url", release_page_url,
      "--assignees-json", JSON.generate(notion_result.fetch("assignees", []).uniq),
      # Already separated from shipped work by the publisher; forward it as-is
      # rather than re-parsing the release notes here.
      "--backlog-json", JSON.generate(notion_result.fetch("backlog", [])),
      "--platform", platform,
      "--version", version,
      "--build-number", build_number,
      "--environment", environment
    ]
  )

  UI.success("Notion release page: #{release_page_url}")
end

platform :android do
  desc "Build and upload to Firebase App Distribution"
  lane :beta do
    gradle(task: "clean assembleRelease")

    firebase_app_distribution(
      app: ENV["FIREBASE_APP_ID"],
      groups: "qa-team",
      release_notes_file: "release_notes.txt"
    )

    # (3) The only change inside the existing lane: notify after the upload
    #     succeeded. Reuse the metadata the build already produced instead of
    #     re-deriving it.
    publish_release_notifications(
      platform: "Android",
      version: android_get_version_name,
      build_number: android_get_version_code
    )
  end

  desc "Re-announce the current build without rebuilding it"
  lane :publish_current_release_notifications do
    publish_release_notifications(
      platform: "Android",
      version: android_get_version_name,
      build_number: android_get_version_code
    )
  end
end
