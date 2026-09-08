#!/usr/bin/env fish

function fail
    echo "build-deps: $argv" >&2
    exit 1
end

argparse h/help push 'platform=' 'tag=' -- $argv
or fail "usage: build-deps.fish [--push] [--platform=LIST] [--tag=IMAGE]"

if set -q _flag_help
    echo "usage: build-deps.fish [--push] [--platform=LIST] [--tag=IMAGE]"
    echo "  default: build for the host platform and load into the local daemon"
    echo "  --push:  build linux/amd64,linux/arm64 and push to the registry"
    exit 0
end

set -l script_file (status --current-filename)
test -n "$script_file"
or fail "could not resolve the script path"

set -l script_dir (path dirname (path resolve "$script_file"))
set -l repo_root (path dirname "$script_dir")

for file in deps/Dockerfile pyproject.toml pdm.lock
    test -f "$repo_root/$file"
    or fail "$file was not found at $repo_root"
end

set -l tag ghcr.io/gcca/blackkeys-ws:deps
set -q _flag_tag; and set tag $_flag_tag

set -l output --load
set -l platform
if set -q _flag_push
    set output --push
    set platform linux/amd64,linux/arm64
else
    switch (uname -m)
        case arm64 aarch64
            set platform linux/arm64
        case x86_64 amd64
            set platform linux/amd64
        case '*'
            fail "unsupported host architecture: "(uname -m)
    end
end
set -q _flag_platform; and set platform $_flag_platform

set -l lock_digest (shasum -a 256 "$repo_root/pdm.lock" | string split -f1 ' ')
or fail "could not hash pdm.lock"

docker buildx build \
    --file "$repo_root/deps/Dockerfile" \
    --target deps \
    --platform $platform \
    --tag $tag \
    --label org.opencontainers.image.source=https://github.com/plaza-san-miguel/blackkeys \
    --label org.opencontainers.image.revision=pdm.lock-sha256:$lock_digest \
    $output \
    "$repo_root"
or fail "docker buildx build failed"
