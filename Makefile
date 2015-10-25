TOPDIR := $(CURDIR)
export TOPDIR

DB_PID := $(shell echo "$$$$")
export DB_PID

include Makefile.inc

.PHONY: tests tests-pre tests-post test-submit-results docs cloc flake forth hello-world hello-world-lib clock vga


#
#
#

SUBDIRS := docs examples forth tests


#
# Control variables
#

# Testset name
ifndef TESTSET
  TESTSET := default
endif

TESTSETDIR := $(CURDIR)/tests-$(TESTSET)

# Using development sources instead of installed package
ifndef DUCKY_IMPORT_DEVEL
  DUCKY_IMPORT_DEVEL := no
endif

# VM debugging
ifndef VMDEBUG
  VMDEBUG := no
endif
ifeq ($(VMDEBUG),yes)
  VMDEBUG := -d
else
  VMDEBUG :=
endif

ifndef VMDEBUG_OPEN_FILES
  VMDEBUG_OPEN_FILES := no
endif
ifeq ($(VMDEBUG_OPEN_FILES),yes)
  VMDEBUG_OPEN_FILES := --debug-open-files
else
  VMDEBUG_OPEN_FILES :=
endif

# VM profiling
ifndef VMPROFILE
  VMPROFILE := no
endif
ifeq ($(VMPROFILE),yes)
  VMPROFILE := -p --profile-dir=$(TESTSETDIR)/profile
else
  VMPROFILE :=
endif

# VM coverage
ifndef VMCOVERAGE
  VMCOVERAGE=no
endif
ifeq ($(VMCOVERAGE),yes)
	VMCOVERAGE_BIN := $(VIRTUAL_ENV)/bin/coverage
	VMCOVERAGE_RUN := $(VMCOVERAGE_BIN) run --rcfile=$(CURDIR)/coveragerc
else
  VMCOVERAGE_BIN :=
	VMCOVERAGE_RUN :=
endif

# Binary profiling
ifndef BINPROFILE
  BINPROFILE := no
endif
ifeq ($(BINPROFILE),yes)
  BINPROFILE := --machine-profile --profile-dir=$(TESTSETDIR)/profile
else
  BINPROFILE :=
endif

# Devices
ifndef DUCKY_ENABLE_DEVICES
	DUCKY_ENABLE_DEVICES :=
endif

ifndef DUCKY_DISABLE_DEVICES
	DUCKY_DISABLE_DEVICES :=
endif

# pypy selection
ifdef PYPY
ifdef CIRCLECI
  PYPY_BINARY=$(shell pyenv which pypy)
else
  PYPY_BINARY=$(shell which pypy)
endif
  # pypy does not see our local installed packages
	PYTHON := PYTHONPATH="$(VIRTUAL_ENV)/lib/python2.7/site-packages/:$(PYTHONPATH)" $(PYPY_BINARY)
else
	PYTHON :=
endif

# Use mmapable sections
ifndef MMAPABLE_SECTIONS
  MMAPABLE_SECTIONS := no
endif

ifndef FORTH_DEBUG_FIND
  FORTH_DEBUG_FIND := no
endif

ifndef FORTH_TEXT_WRITABLE
  FORTH_TEXT_WRITABLE := no
endif

ifndef FORTH_WELCOME
  FORTH_WELCOME := no
endif

export TESTSET
export TESTSETDIR
export VMDEBUG
export VMPROFILE
export VMCOVERAGE
export VMCOVERAGE_BIN
export VMCOVERAGE_RUN
export PYTHON

export DUCKY_IMPORT_DEVEL
export DUCKY_ENABLE_DEVICES
export DUCKY_DISABLE_DEVICES

export MMAPABLE_SECTIONS
export FORTH_DEBUG_FIND
export FORTH_TEXT_WRITABLE
export FORTH_WELCOME


#
# FORTH
#

FORTH_KERNEL := $(TOPDIR)/forth/ducky-forth
export FORTH_KERNEL

forth:
	$(Q) make -C forth/ kernel


#
# Examples
#


# Hello, world!
hello-world:
	$(Q) $(MAKE) -C examples/hello-world build

run-hello-world: hello-world interrupts
	$(Q) $(MAKE) -C examples/hello-world run


# Clock
clock:
	$(Q) $(MAKE) -C examples/clock build

run-clock: clock interrupts
	$(Q) $(MAKE) -C examples/clock run


# "Hello, world!" using library
hello-world-lib:
	$(Q) $(MAKE) -C examples/hello-world-lib build

run-hello-world-lib: hello-world-lib interrupts
	$(Q) $(MAKE) -C examples/hello-world-lib run


# sVGA show-off
vga:
	$(Q) $(MAKE) -C examples/vga build

run-vga: vga interrupts
	$(Q) $(MAKE) -C examples/vga run


#
# Common binaries
#

# Basic interrupt routines

INTERRUPTS := $(TOPDIR)/interrupts
export INTERRUPTS

interrupts.o: interrupts.asm defs.asm
interrupts: interrupts.o
	$(run-linker)


#
# Tests
#

tests-interim-clean: clean-master
	$(Q) for dir in $(SUBDIRS); do \
	       $(MAKE) -C $$dir clean; \
			 done

tests-pre-master:
	$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) Create test set $(TESTSET) ... "
	$(Q) rm -rf $(TESTSETDIR)
	$(Q) mkdir -p $(TESTSETDIR)
	$(Q) mkdir -p $(TESTSETDIR)/coverage
	$(Q) mkdir -p $(TESTSETDIR)/profile
	$(Q) mkdir -p $(TESTSETDIR)/results
	$(Q) mkdir -p $(TESTSETDIR)/tmp
	$(Q) echo "$(CC_GREEN)PASS$(CC_END)"
	$(Q) echo "$(CC_YELLOW)Using python:$(CC_END) $(CC_GREEN)$(PYTHON)$(CC_END)"

tests-pre: tests-pre-master
	$(Q) $(MAKE) -C tests/ tests-pre

tests-in-subdirs: interrupts forth
	$(Q) $(MAKE) -C tests/ tests

tests-post-master:
	$(Q) $(MAKE) -C tests/ tests-post
ifeq ($(VMCOVERAGE),yes)
	$(Q) cd $(TESTSETDIR)/coverage && $(VMCOVERAGE_BIN) combine --rcfile=$(CURDIR)/coveragerc && cd ..
	$(Q) COVERAGE_FILE="$(TESTSETDIR)/coverage/.coverage" $(VMCOVERAGE_BIN) html --rcfile=$(CURDIR)/coveragerc --omit="*/python2.7/*" -d $(TESTSETDIR)/coverage/
endif

tests-post: tests-post-master
	$(Q) $(MAKE) -C tests/ tests-post
	$(Q) ls $(TESTSETDIR)/*.machine &> /dev/null; \
	     if [ "$?" = "0" ]; then echo "$(CC_GREEN)Avg # of instructions: `grep Executed $(TESTSETDIR)/*.machine | awk '{print $$5, " ", $$6}' | python tests/sum`/sec$(CC_END)"; fi

tests-submit-results:
ifdef CIRCLE_TEST_REPORTS
	$(eval ts_results := $(wildard $(TESTSETDIR)/results/*.xml))
	$(Q) mkdir -p $(CIRCLE_TEST_REPORTS)/$(TESTSET)
	$(Q) for f in `ls -1 $(TESTSETDIR)/results/*.xml`; do g="`basename $$f`"; cp $$f $(CIRCLE_TEST_REPORTS)/`echo "$$g" | sed 's/\(.*\).xml/$(TESTSET)-\1.xml/'`; done;
endif
ifdef CIRCLE_ARTIFACTS
	$(Q) cp -r $(TESTSETDIR) $(CIRCLE_ARTIFACTS)
endif

tests: tests-pre tests-in-subdirs tests-post tests-submit-results
check: tests


#
# Utility targets
#

# Clean
clean-master:
	$(Q) rm -rf build dist ducky.egg-info
	$(Q) rm -f $(shell find $(TOPDIR) -name 'ducky-snapshot.bin')
	$(Q) rm -f $(shell find $(TOPDIR) -name '*.pyc' -o -name '*.o')
	$(Q) rm -f interrupts

clean-testsets:
	$(Q) rm -rf tests-*

clean-in-subdirs:
	$(Q) for dir in $(SUBDIRS); do \
	       $(MAKE) -C $$dir clean; \
	     done

clean: clean-master clean-testsets clean-in-subdirs


profile-eval:
	$(Q) python -i -c "import os; import pstats; ps = pstats.Stats(*['$(TESTSETDIR)/profile/%s' % f for f in os.listdir('$(TESTSETDIR)/profile/') if f.find('-Profile-') != -1])"


cloc:
	cloc --skip-uniqueness --lang-no-ext=Python ducky/ forth/ examples/ tools/


flake:
	$(Q) ! flake8 --config=$(TOPDIR)/flake8.cfg $(shell find $(TOPDIR)/ducky $(TOPDIR)/tests -name '*.py') $(shell find $(TOPDIR)/tools) | sort | grep -v -e "'patch' imported but unused" -e 'tools/cc:' -e duckyfs -e '\.swp' -e 'unable to detect undefined names'


# Documentation
docs:
	cp README.rst docs/introduction.rst
	sphinx-apidoc -T -e -o docs/ ducky/
	$(MAKE) -C docs/ clean
	$(MAKE) -C docs/ html


#
# Packaging
#

build: ducky/native/data_cache.c
	python setup.py build --debug


install:
	python setup.py install
