#!/bin/bash

set -x

PASSED=yes

# If run without any params, scripts runs as a part of CI job
# Guess versions according to a CIRCLE_NODE_INDEX
if [[ "$1" = "" ]]; then
  Q=@ make clean

  if [[ $CIRCLE_NODE_INDEX == "0" ]]; then
    VERSIONS="2.7.10"

  elif [[ $CIRCLE_NODE_INDEX == "1" ]]; then
    VERSIONS="3.2.5"

  elif [[ $CIRCLE_NODE_INDEX == "2" ]]; then
    VERSIONS="3.3.3"

  elif [[ $CIRCLE_NODE_INDEX == "3" ]]; then
    VERSIONS="3.4.3"

  elif [[ $CIRCLE_NODE_INDEX == "4" ]]; then
    VERSIONS="3.5.0"

  elif [[ $CIRCLE_NODE_INDEX == "5" ]]; then
    VERSIONS="pypy-2.5.0"
  fi
else
  VERSIONS="${1:-2.7.10 pypy-2.5.0}"
fi

function run_tests () {
  local interpret="$1"
  local mmap="$2"

  local mmap_postfix=""
  [[ "$mmap" == "yes" ]] && mmap_postfix="-mmap"

  local pypy="no"
  [[ "$interpret" == pypy-* ]] && pypy="yes"

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
