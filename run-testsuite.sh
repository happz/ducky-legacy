#!/bin/bash

set -x

PASSED=yes
VERSIONS="${1:-py27 pypy}"

function run_tests () {
  local interpret="$1"
  local mmap="$2"

  local mmap_postfix=""
  [[ "$mmap" == "yes" ]] && mmap_postfix="-mmap"

  local pypy="no"
  [[ "$interpret" == pypy* ]] && pypy="yes"

  #export Q=@
  export TESTSET="${interpret}${mmap_postfix}"
  export PYPY="$pypy"
  export MMAPABLE_SECTIONS="$mmap"

  make --keep-going tests-interim-clean tests
  [ $? -ne 0 ] && PASSED=no
}

for version in $VERSIONS; do
  run_tests "$version" no
  run_tests "$version" yes
done

[ $PASSED = no ] && exit 1

set +x

exit 0
