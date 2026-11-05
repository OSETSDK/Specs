#!/usr/bin/env ruby
# Resolve each migrated Pod independently with the installed CocoaPods resolver.
# This script downloads public specification metadata only. It does not install
# Pods, download SDK artifacts, build an app, edit the Specs tree, or publish.

require 'json'
require 'pathname'
require 'optparse'
require 'digest'
require 'time'

ENV['COCOAPODS_CDN_MAX_CONCURRENCY'] ||= '8'
ENV['COCOAPODS_CDN_MAX_NUMBER_OF_RETRIES'] ||= '2'
ENV['COCOAPODS_DISABLE_STATS'] ||= 'true'
ENV['GIT_OPTIONAL_LOCKS'] ||= '0'

options = { pods: [], minimum_ios: '12.0' }
parser = OptionParser.new do |o|
  o.banner = 'Usage: validate_resolution.rb SPECS_REPO REPORT.json [--pod NAME ...] [--minimum-ios VERSION]'
  o.on('--pod NAME', 'Resolve only this root Pod; may be repeated') { |name| options[:pods] << name }
  o.on('--minimum-ios VERSION', 'Target baseline; raised to each root specification minimum') { |v| options[:minimum_ios] = v }
end
parser.parse!
abort parser.to_s unless ARGV.length == 2

repo_path = Pathname.new(ARGV[0]).expand_path.realpath
report_path = Pathname.new(ARGV[1]).expand_path
abort 'Report must be outside the read-only Specs repository' if report_path.to_s.start_with?(repo_path.to_s + '/')

isolation = %w[CP_HOME_DIR CP_CACHE_DIR CP_REPOS_DIR].to_h do |key|
  value = ENV[key]
  abort "#{key} must point to an explicitly isolated directory" if value.nil? || value.empty?
  path = Pathname.new(value).expand_path
  protected_paths = [Pathname.new('~/.cocoapods').expand_path, Pathname.new('~/Library/Caches/CocoaPods').expand_path, repo_path]
  abort "Unsafe #{key}: #{path}" if protected_paths.any? { |p| path == p || path.to_s.start_with?(p.to_s + '/') }
  [key, path.to_s]
end

require 'cocoapods'
abort "Expected CocoaPods 1.16.2, got #{Pod::VERSION}" unless Pod::VERSION == '1.16.2'
Pod::Config.instance.silent = true

cdn_url = 'https://cdn.cocoapods.org/'
spec_paths = repo_path.glob('*/*/*.podspec.json').sort
abort 'No POD/VERSION/POD.podspec.json files found' if spec_paths.empty?
specs = spec_paths.map do |path|
  spec = Pod::Specification.from_file(path)
  relative = path.relative_path_from(repo_path).each_filename.to_a
  unless relative == [spec.name, spec.version.to_s, "#{spec.name}.podspec.json"]
    abort "Specification name/version does not match directory: #{path}"
  end
  [spec.name, spec, path]
end
manifest_path = repo_path.join('specs-manifest.json')
if manifest_path.file?
  entries = JSON.parse(manifest_path.read).fetch('pods')
  chosen = entries.to_h { |entry| [entry.fetch('name'), entry.fetch('selected_version')] }
  order = entries.to_h { |entry| [entry.fetch('name'), entry.fetch('order')] }
  specs.select! { |name, spec, _path| chosen[name] == spec.version.to_s }
  missing = chosen.keys - specs.map(&:first)
  abort "Manifest selected versions missing: #{missing.join(', ')}" unless missing.empty?
  specs.sort_by! { |name, _spec, _path| order.fetch(name) }
else
  specs = specs.group_by(&:first).map { |_name, versions| versions.max_by { |_n, spec, _p| spec.version } }
end
unknown = options[:pods] - specs.map(&:first)
abort "Requested Pod is not present: #{unknown.join(', ')}" unless unknown.empty?
specs.select! { |name, _spec, _path| options[:pods].include?(name) } unless options[:pods].empty?
input_hashes = spec_paths.to_h { |path| [path.to_s, Digest::SHA256.file(path).hexdigest] }

report_path.dirname.mkpath
scratch_path = report_path.dirname.join(report_path.basename('.json').to_s + '-scratch')
scratch_path.mkpath
report = {
  schema_version: 1,
  started_at: Time.now.utc.iso8601,
  cocoapods_version: Pod::VERSION,
  scope: 'Independent fresh dependency resolution for each root Pod; no lockfile',
  does_not_validate: ['SDK artifact availability', 'resource file existence', 'pod installation', 'simulator/device build', 'advertising behavior', 'old customer lockfile migration'],
  specs_repository: repo_path.to_s,
  input_specification_sha256: input_hashes,
  isolation: isolation,
  minimum_ios: options[:minimum_ios],
  public_cdn: cdn_url,
  results: []
}

def save_report(path, report)
  temporary = Pathname.new(path.to_s + '.tmp')
  temporary.write(JSON.pretty_generate(report) + "\n")
  temporary.rename(path)
end

def plain_error(error)
  error.message.gsub(/\e\[[\d;]*m/, '')
end

save_report(report_path, report)

begin
  manager = Pod::Config.instance.sources_manager
  # Use the actual CocoaPods command to register the CDN in CP_REPOS_DIR.
  # No source registration or cache writes reach the user's normal installation.
  cdn_name = 'oset-migration-trunk'
  expected_cdn_dir = Pathname.new(isolation.fetch('CP_REPOS_DIR')).join(cdn_name)
  unless expected_cdn_dir.join('.url').file?
    Pod::Command::Repo::AddCDN.parse([cdn_name, cdn_url]).run
  end
  cdn_source = manager.sources([cdn_name]).first
  abort "Unexpected CDN URL: #{cdn_source.url}" unless cdn_source.url == cdn_url
  local_source = Pod::Source.new(repo_path)
  report[:sources] = [
    { kind: 'oset_specs', path: repo_path.to_s, url: local_source.url },
    { kind: 'public_cdn', path: cdn_source.repo.to_s, url: cdn_source.url }
  ]
  managed_names = input_hashes.keys.map { |path| Pathname.new(path).relative_path_from(repo_path).each_filename.first }.uniq

  specs.each_with_index do |(name, spec, path), index|
    started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    result = { pod: name, requested_version: spec.version.to_s, spec_path: path.to_s, status: 'running' }
    begin
      ios_platform = spec.available_platforms.find { |platform| platform.name == :ios }
      raise "Root specification does not support iOS: #{name}" unless ios_platform
      declared_minimum = ios_platform.deployment_target&.to_s || '0'
      target_ios = [Pod::Version.new(options[:minimum_ios]), Pod::Version.new(declared_minimum)].max.to_s
      result[:declared_minimum_ios] = declared_minimum
      result[:target_ios] = target_ios
      podfile = Pod::Podfile.new do
        platform :ios, target_ios
        install! 'cocoapods', :warn_for_multiple_pod_sources => false
        target 'ResolutionProbe' do
          pod name, "= #{spec.version}"
        end
      end
      sandbox = Pod::Sandbox.new(scratch_path.join(name, 'Pods'))
      resolver = Pod::Resolver.new(sandbox, podfile, Molinillo::DependencyGraph.new,
                                   [local_source, cdn_source], true, sources_manager: manager)
      resolved = resolver.resolve.values.flatten.uniq { |item| [item.name, item.spec.version.to_s] }
      result[:resolved_specifications] = resolved.map do |item|
        source = item.source
        kind = if source && source.repo.expand_path == repo_path
                 'oset_specs'
               elsif source && source.repo.expand_path == cdn_source.repo.expand_path
                 'public_cdn'
               else
                 'other'
               end
        {
          name: item.name,
          root_name: item.spec.root.name,
          version: item.spec.version.to_s,
          source_kind: kind,
          source_url: source&.url,
          source_path: source&.repo&.to_s,
          specification_sha1: item.spec.checksum,
          dependencies: item.spec.all_dependencies.map { |dependency| { name: dependency.name, requirement: dependency.requirement.to_s } }
        }
      end.sort_by { |item| [item[:root_name], item[:name]] }
      root_entries = result[:resolved_specifications].select { |item| item[:root_name] == name }
      raise 'Root was not resolved from the candidate OSET Specs source' if root_entries.empty? || root_entries.any? { |item| item[:source_kind] != 'oset_specs' }
      result[:managed_dependencies_from_public_cdn] = result[:resolved_specifications].select do |item|
        managed_names.include?(item[:root_name]) && item[:source_kind] == 'public_cdn'
      end.map { |item| { name: item[:name], version: item[:version] } }
      result[:resolved_root_pod_count] = result[:resolved_specifications].map { |item| item[:root_name] }.uniq.length
      result[:status] = 'passed'
    rescue StandardError => error
      result[:status] = 'failed'
      result[:error_class] = error.class.name
      result[:error] = plain_error(error)
    ensure
      result[:elapsed_seconds] = (Process.clock_gettime(Process::CLOCK_MONOTONIC) - started).round(3)
      report[:results] << result
      save_report(report_path, report)
      puts JSON.generate({ index: index + 1, total: specs.length, pod: name, status: result[:status], target_ios: result[:target_ios], resolved_root_pod_count: result[:resolved_root_pod_count], error: result[:error] })
      STDOUT.flush
    end
  end
rescue StandardError => error
  report[:setup_error] = { error_class: error.class.name, error: plain_error(error) }
ensure
  changed_inputs = input_hashes.select { |path, hash| !File.file?(path) || Digest::SHA256.file(path).hexdigest != hash }.keys
  report[:input_specifications_unchanged] = changed_inputs.empty?
  report[:changed_input_specifications] = changed_inputs
  report[:finished_at] = Time.now.utc.iso8601
  report[:summary] = {
    requested_roots: specs.length,
    completed_roots: report[:results].length,
    passed_roots: report[:results].count { |result| result[:status] == 'passed' },
    failed_roots: report[:results].count { |result| result[:status] == 'failed' }
  }
  save_report(report_path, report)
end

success = report[:setup_error].nil? && report[:input_specifications_unchanged] &&
          report[:summary][:completed_roots] == report[:summary][:requested_roots] &&
          report[:summary][:failed_roots].zero?
puts JSON.generate({ report: report_path.to_s, summary: report[:summary], setup_error: report[:setup_error] })
exit(success ? 0 : 1)
