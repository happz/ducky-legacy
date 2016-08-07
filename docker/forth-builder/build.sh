#!/usr/bin/env bash

TMPDIR=$(mktemp -d)

DUCKY_UPSTREAM=/tmp/ducky-upstream
DUCKY_REPO=/tmp/ducky-repo
DUCKY_UPLOAD=/tmp/ducky-upload
LLVM_TARBALL=https://ducky.happz.cz/llvm/ducky-llvm-latest.tar.gz

wget --no-check-certificate -O ducky-llvm-latest.tar.gz $LLVM_TARBALL
tar xzf ducky-llvm-latest.tar.gz -C /
export LLVMDIR=/opt/llvm


git clone $DUCKY_UPSTREAM $DUCKY_REPO

pushd $DUCKY_REPO

BUILD_ID="`git log --pretty='%H-%ad' --date='format:%Y%m%d-%H%M%S' | head -1`"

export VIRTUAL_ENV=/usr/local

python setup.py install
/usr/bin/scons -sQ forth

if [ ! -f $DUCKY_REPO/forth/ducky-forth ]; then
  popd
  exit 1
fi

tar czf $DUCKY_UPLOAD/ducky-forth.tar.gz forth/ducky-forth forth/ducky-forth.f forth/forth.conf

popd # $DUCKY_REPO
