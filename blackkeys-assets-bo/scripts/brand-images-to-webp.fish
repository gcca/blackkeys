#!/usr/bin/env fish

function fail
    echo "brand-images-to-webp: $argv" >&2
    exit 1
end

function step
    echo "brand-images-to-webp: $argv" >&2
end

set -l usage "usage: brand-images-to-webp.fish [--apply] [--bucket=NAME]"

argparse h/help apply 'bucket=' -- $argv
or fail $usage

if set -q _flag_help
    echo $usage
    echo "  converts brands/name=*/{logo,picture}.png into a .webp sibling"
    echo "  logo: lossless; picture: lossy q=82"
    echo "  default is a dry run: objects are downloaded and converted locally,"
    echo "  sizes are reported, and nothing is written to the bucket"
    echo "  --apply: upload each .webp with Content-Type image/webp"
    echo "  existing .webp objects are skipped; .png objects are never deleted"
    echo "  defaults: --bucket=\$BUCKET_NAME, else blackkeys-assets"
    exit 0
end

for tool in aws cwebp od
    command -q $tool
    or fail "$tool was not found on PATH"
end

set -l bucket blackkeys-assets
if set -q BUCKET_NAME; and test -n "$BUCKET_NAME"
    set bucket $BUCKET_NAME
end
if set -q _flag_bucket
    set bucket $_flag_bucket
end

set -l mode "dry run"
set -q _flag_apply; and set mode apply
step "bucket=$bucket mode=$mode"

set -l listing (aws s3api list-objects-v2 --bucket $bucket --prefix brands/ \
    --query 'Contents[].Key' --output text)
or fail "could not list s3://$bucket/brands/"

set -l keys
for line in $listing
    for key in (string split \t -- $line)
        test "$key" = None; or set -a keys $key
    end
end

set -l work (mktemp -d)
or fail "could not create a temporary directory"

set -l converted 0
set -l skipped 0
set -l failed 0
set -l before_total 0
set -l after_total 0

for key in $keys
    set -l match (string match -r '^brands/name=[^/]+/(logo|picture)\.png$' -- $key)
    or continue
    set -l kind $match[2]
    set -l target (string replace -r '\.png$' .webp -- $key)

    if contains -- $target $keys
        step "skip $key ($target exists)"
        set skipped (math $skipped + 1)
        continue
    end

    set -l source_file $work/source.png
    set -l output_file $work/output.webp
    rm -f $source_file $output_file

    if not aws s3 cp --only-show-errors "s3://$bucket/$key" $source_file
        step "FAIL $key: download failed"
        set failed (math $failed + 1)
        continue
    end

    set -l options -quiet -metadata none -mt
    if test $kind = logo
        set -a options -lossless -z 9
    else
        set -a options -q 82 -m 6
    end
    if not cwebp $options $source_file -o $output_file
        step "FAIL $key: cwebp failed"
        set failed (math $failed + 1)
        continue
    end

    set -l header (od -An -tx1 -N12 $output_file | string replace -ar '\s' '')
    if test (string sub -l 8 -- "$header") != 52494646
        or test (string sub -s 17 -l 8 -- "$header") != 57454250
        step "FAIL $key: output is not a RIFF/WEBP file"
        set failed (math $failed + 1)
        continue
    end

    set -l before (wc -c < $source_file | string trim)
    set -l after (wc -c < $output_file | string trim)
    set before_total (math $before_total + $before)
    set after_total (math $after_total + $after)

    if set -q _flag_apply
        if not aws s3 cp --only-show-errors --content-type image/webp \
                $output_file "s3://$bucket/$target"
            step "FAIL $key: upload of $target failed"
            set failed (math $failed + 1)
            continue
        end
        step "wrote $target ($before -> $after bytes)"
    else
        step "would write $target ($before -> $after bytes)"
    end
    set converted (math $converted + 1)
end

rm -rf $work

step "converted=$converted skipped=$skipped failed=$failed bytes=$before_total -> $after_total"
test $failed -eq 0
