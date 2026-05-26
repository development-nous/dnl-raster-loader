#!/bin/bash

## Get the directory of this script
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
parent_dir="$(dirname "${script_dir}")"
plugin_name="$(basename "${script_dir}")"

echo "$script_dir"

rm  -f "${script_dir}/dnl-raster-loader.zip"

cd "${parent_dir}" || exit

zip -r "dnl-raster-loader.zip" "${plugin_name}" \
  -x "${plugin_name}"/\*.zip \
  -x "${plugin_name}"/make-zip.sh \
  -x "${plugin_name}"/.git \
  -x "${plugin_name}"/.git/\* \
  -x "${plugin_name}"/\*.sw\* \
  -x "${plugin_name}"/res/images \
  -x "${plugin_name}"/res/images/\* \
  -x "${plugin_name}"/.gitignore

mv ./dnl-raster-loader.zip "${script_dir}/"
