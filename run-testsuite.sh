#!/bin/bash

set -x

PASSED=yes
VERSIONS="${1:-2.7.10 3.4.3 3.5.0 pypy-2.5.0}"

eval "$(pyenv init -)"


function run_tests () {
  local interpret="$1"
  local mmap="$2"

  local mmap_postfix=""
  [ "$mmap" = "yes" ] && mmap_postfix="-mmap"

  local pypy="no"
  [[ "$interpret" == pypy-* ]] && pypy="yes"

  pyenv global "$1"
  pyenv versions

  export Q=@
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
