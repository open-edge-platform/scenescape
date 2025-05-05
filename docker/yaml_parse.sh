#!/bin/bash

# Copyright (C) 2021 Intel Corporation
#
# This software and the related documents are Intel copyrighted materials,
# and your use of them is governed by the express license under which they
# were provided to you ("License"). Unless the License provides otherwise,
# you may not use, modify, copy, publish, distribute, disclose or transmit
# this software or the related documents without Intel's prior written permission.
#
# This software and the related documents are provided as is, with no express
# or implied warranties, other than those that are expressly stated in the License.

parse_yaml() {
    local yaml_file=$1
    local prefix=$2
    local s
    local w
    local fs

    s='[[:space:]]*'
    w='[a-zA-Z0-9_.-]*'
    fs="$(echo @ | tr @ '\034')"

    (
        sed -e '/- [^\“]'"[^\']"'.*: /s|\([ ]*\)- \('"$s"'\)|\1-\'$'\n''  \1\2|g' |
            sed -ne '/^--/s|--||g; s|\"|\\\"|g; s/'"$s"'$//g;' \
                -e 's/\$/\\\$/g' \
                -e "/#.*[\"\']/!s| #.*||g; /^#/s|#.*||g;" \
                -e "s|^\($s\)\($w\)$s:$s\"\(.*\)\"$s\$|\1$fs\2$fs\3|p" \
                -e "s|^\($s\)\($w\)${s}[:-]$s\(.*\)$s\$|\1$fs\2$fs\3|p" |
            awk -F"$fs" \
                '{
                   prev_indent = indent;
                   indent = length($1)/2;
                   if (prev_indent > indent && length(vname[prev_indent])) {
                     vn=""; for (i=0; i<prev_indent; i++) {vn=(vn)(vname[i])("_")}
                     printf("%s%s=(\"%s\")\n", "'"$prefix"'", vn, vname[prev_indent]);
                   }
                   if (length($2) == 0) { conj[indent]="+";} else {conj[indent]="";}
                   vname[indent] = $2;
                   for (i in vname) {if (i > indent) {delete vname[i]}}
                   if (length($3) > 0) {
                     vn=""; for (i=0; i<indent; i++) {vn=(vn)(vname[i])("_")}
                     printf("%s%s%s%s=(\"%s\")\n", "'"$prefix"'",vn, vname[indent], conj[indent-1], $3);
                   }
                 }' |
                        sed -e 's/_=/+=/g' |
                                    awk 'BEGIN {
                FS="=";
                OFS="="
            }
            /(-|\.).*=/ {
                gsub("-|\\.", "_", $1)
            }
            { print }'
    ) <"$yaml_file"
}
