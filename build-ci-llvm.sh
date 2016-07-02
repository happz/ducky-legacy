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

git clone https://github.com/happz/llvm.git
pushd llvm/tools
git clone https://github.com/happz/clang.git
popd # llvm/tools

mkdir llvm-build
pushd llvm-build
/usr/local/bin/cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_ASSERTIONS=Off -DCMAKE_INSTALL_PREFIX=$PREFIX -DLLVM_BUILD_TESTS=OFF -DLLVM_BUILD_DOCS=OFF -DLLVM_OPTIMIZED_TABLEGEN=ON -DLLVM_TARGETS_TO_BUILD=Ducky -DLLVM_DEFAULT_TARGET_TRIPLE=ducky-none-none -DCLANG_VENDOR=happz/ducky ~/llvm
ninja -j1
popd # llvm-build

popd # ~
