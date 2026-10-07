#!/usr/bin/env fish

function fail
    echo "build-deps: $argv" >&2
    exit 1
end

function step
    echo "build-deps: $argv" >&2
end

set -l usage "usage: build-deps.fish [--push] [--local-tag=IMAGE] [--remote-tag=IMAGE] [--platforms=LIST]"

argparse h/help push 'local-tag=' 'remote-tag=' 'platforms=' -- $argv
or fail $usage

if set -q _flag_help
    echo $usage
    echo "  1. build deps for the host platform and load it as the local tag"
    echo "  2. build the app on top of the local deps image and smoke-test it"
    echo "  3. --push: build the remote platforms and push the remote tag"
    echo "  defaults: --local-tag=blackkeys-assets-bo:deps"
    echo "            --remote-tag=ghcr.io/gcca/blackkeys:assets-bo-deps"
    echo "            --platforms=linux/amd64,linux/arm64"
    exit 0
end

test (count $argv) -eq 0
or fail "unexpected arguments: $argv"

for option in local_tag remote_tag platforms
    set -l flag _flag_$option
    if set -q $flag; and test -z "$$flag"
        fail "--"(string replace -a _ - -- $option)" must not be empty"
    end
end

set -l script_file (status --current-filename)
test -n "$script_file"
or fail "could not resolve the script path"

set -l script_dir (path dirname (path resolve "$script_file"))
set -l repo_root (path dirname "$script_dir")

for file in Dockerfile deps/Dockerfile CMakeLists.txt src/assetsbo.cc
    test -f "$repo_root/$file"
    or fail "$file was not found at $repo_root"
end

set -l local_tag blackkeys-assets-bo:deps
set -q _flag_local_tag; and set local_tag $_flag_local_tag
set -l remote_tag ghcr.io/gcca/blackkeys:assets-bo-deps
set -q _flag_remote_tag; and set remote_tag $_flag_remote_tag
set -l platforms linux/amd64,linux/arm64
set -q _flag_platforms; and set platforms $_flag_platforms
set -l check_tag blackkeys-assets-bo:deps-check

set -l host_platform
switch (uname -m)
    case arm64 aarch64
        set host_platform linux/arm64
    case x86_64 amd64
        set host_platform linux/amd64
    case '*'
        fail "unsupported host architecture: "(uname -m)
end

set -l deps_digest (shasum -a 256 "$repo_root/deps/Dockerfile" | string split -f1 ' ')
or fail "could not hash deps/Dockerfile"
string match -rq '^[0-9a-f]{64}$' -- $deps_digest
or fail "could not hash deps/Dockerfile"

set -l labels \
    --label org.opencontainers.image.source=https://github.com/gcca/blackkeys \
    --label org.opencontainers.image.revision=deps.Dockerfile-sha256:$deps_digest

step "building $local_tag for $host_platform"
docker buildx build \
    --file "$repo_root/deps/Dockerfile" \
    --target deps \
    --platform $host_platform \
    --tag $local_tag \
    $labels \
    --load \
    "$repo_root"
or fail "local deps build failed"

step "building $check_tag on $local_tag"
docker build \
    --build-arg DEPS_IMAGE=$local_tag \
    --tag $check_tag \
    "$repo_root"
or fail "app build on $local_tag failed"

step "smoke-testing $check_tag"
docker run --rm $check_tag --help >/dev/null 2>&1
set -l help_code $status
# No env: settings must reject credentials before AWS initialization or any S3 call.
set -l output
set -l code
if test $help_code -eq 0
    set output (docker run --rm $check_tag 2>&1)
    set code $status
end
docker image rm $check_tag >/dev/null
test $help_code -eq 0
or fail "--help smoke test on $check_tag failed (exit $help_code)"
test "$code" -eq 1
and string match -q '*AWS_ACCESS_KEY_ID must not be empty*' -- $output
or fail "smoke test on $check_tag failed (exit $code): $output"

if not set -q _flag_push
    step "done: $local_tag"
    exit 0
end

step "building and pushing $remote_tag for $platforms"
docker buildx build \
    --file "$repo_root/deps/Dockerfile" \
    --target deps \
    --platform $platforms \
    --tag $remote_tag \
    $labels \
    --push \
    "$repo_root"
or fail "remote deps build or push failed"

step "done: $local_tag, $remote_tag"
