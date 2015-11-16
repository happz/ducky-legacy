#!/bin/bash

set -x

VERSIONS="${1:-2.7.10 3.4.3}"

function run_tests () {
  local interpret="$1"

  local pypy="no"
  [ $interpret == pypy-* ] && pypy="yes"

  pyenv global "$1"

  export Q=@
  export TESTSET=coverage-${interpret}
  export VMCOVERAGE=yes

  make tests-interim-clean tests-pre

  export MMAPABLE_SECTIONS=
  make tests-in-subdirs

  make tests-interim-clean

  export MMAPABLE_SECTIONS=yes
  make tests-in-subdirs

  make tests-post tests-submit
}

if [ "$1" = "--submit" ]; then
  rm -rf tests-coverage
  mkdir tests-coverage

  for f in `find tests-coverage-* -name '.coverage'`; do
    cp $f tests-coverage/.coverage.`echo $(dirname $f) | sed 's/\//-/g'`
  done

  pushd tests-coverage
    coverage combine --rcfile=../coveragerc
  popd

  if [ -f ./.coveralls-token ]; then
    source ./.coveralls-token
  fi

  coveralls --config_file coveragerc --data_file tests-coverage/.coverage
else
  for version in $VERSIONS; do
    run_tests "$version"
  done
fi

set +x

exit 0
