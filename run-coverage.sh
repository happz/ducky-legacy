#!/bin/sh

export Q=@
export TESTSET=coverage-python
export VMCOVERAGE=yes
export VMDEBUG_OPEN_FILES=yes

make clean tests-pre

export MMAPABLE_SECTIONS=yes
make tests-in-subdirs run-hello-world run-clock run-hello-world-lib run-vga run-hello-world-screen

make clean-master clean-in-subdirs

export MMAPABLE_SECTIONS=
make tests-in-subdirs run-hello-world run-clock run-hello-world-lib run-vga run-hello-world-screen

make tests-post tests-submit-results

if [ -f ./.coveralls-token ]; then
  source ./.coveralls-token
  coveralls --config_file coveragerc --data_file tests-coverage-python/coverage/.coverage
fi
