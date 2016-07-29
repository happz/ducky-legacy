#!/bin/bash

#
# Build LLVM and Clang for CI testing
#

pushd ~

sudo apt-get update
sudo apt-get install ninja-build

# Build recent CMake
wget --no-check-certificate http://www.cmake.org/files/v3.5/cmake-3.5.2.tar.gz
tar xf cmake-3.5.2.tar.gz
pushd cmake-3.5.2
./configure
make
sudo make install
popd # cmake-3.5.2


# Clone first instance of LLVM to get the build script
git clone https://github.com/happz/llvm.git llvm-first
pushd llvm-first
JOBS=1 ./build-release.sh
popd # llvm-first

popd # ~
