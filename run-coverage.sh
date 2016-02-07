#!/bin/bash

set -x

VERSIONS="${1:-py27}"

function run_tests () {
  local interpret="$1"

  local pypy="no"
  [[ "$interpret" == pypy* ]] && pypy="yes"

  export Q=@
  export TESTSET=coverage-${interpret}
  export VMCOVERAGE=yes
  export PYPY=$pypy
  export DUCKY_BOOT_IMG=yes

  make tests-interim-clean tests-pre

  export MMAPABLE_SECTIONS=
  make tests-in-subdirs

  make tests-interim-clean

  export MMAPABLE_SECTIONS=yes
  make tests-in-subdirs

  make tests-post tests-submit-results
}

if [ "$1" = "--submit" ]; then
  rm -rf tests-coverage
  mkdir tests-coverage

  for f in `find tests-coverage-* -name '.coverage'`; do
    echo "Coverage from ${f}..."
    cp $f tests-coverage/.coverage.`echo $(dirname $f) | sed 's/\//-/g'`
  done

  pushd tests-coverage
    coverage combine --rcfile=../coveragerc
  popd

  if [ -f ./.coveralls-token ]; then
    source ./.coveralls-token
  fi

  COVERAGE_FILE=tests-coverage/.coverage coveralls --rcfile=coveragerc
else
  for version in $VERSIONS; do
    run_tests "$version"
  done
fi

set +x

exit 0
