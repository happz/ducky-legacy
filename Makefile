TOPDIR := $(CURDIR)
export TOPDIR

DB_PID := $(shell echo "$$$$")
export DB_PID

DCC := $(shell which ducky-cc)
DAS := $(shell which ducky-as)
DLD := $(shell which ducky-ld)
DVM := $(shell which ducky-vm)

export DAS
export DCC
export DLD
export DVM


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
TESTSET_FAILED := $(TESTSETDIR)/.failed

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
ifndef PYPY
  PYPY := no
endif

ifeq ($(PYPY),yes)
ifdef CIRCLECI
  PYTHON := PYTHONPATH="$(shell find $(VIRTUAL_ENV) -name 'ducky-*' -type d | tr ' ' ':'):$(shell find $(VIRTUAL_ENV) -name 'site-packages' | head -1):$(PYTHONPATH)" pypy
else
  PYTHON := pypy
endif
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
export TESTSET_FAILED
export VMDEBUG
export VMPROFILE
export VMCOVERAGE
export VMCOVERAGE_BIN
export VMCOVERAGE_RUN
export PYTHON

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

# Hello, world! with screen terminal
hello-world-screen: hello-world

run-hello-world-screen: hello-world-screen interrupts
	$(Q) $(MAKE) -C examples/hello-world run-screen


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

tests-interim-clean: clean-master clean-in-subdirs

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
	$(Q) echo "$(CC_YELLOW)Test set directory:$(CC_END) $(CC_GREEN)$(TESTSETDIR)$(CC_END)"

tests-pre: tests-pre-master
	$(Q) $(MAKE) -C tests/ tests-pre
	$(Q) $(MAKE) -C examples/ tests-pre

tests-in-subdirs: interrupts forth
	$(Q) $(MAKE) -C tests/ tests
	$(Q) $(MAKE) -C examples/ tests

tests-post-master:
	$(Q) $(MAKE) -C tests/ tests-post
	$(Q) $(MAKE) -C examples/ tests-post
ifeq ($(VMCOVERAGE),yes)
	$(Q) cd $(TESTSETDIR)/coverage && $(VMCOVERAGE_BIN) combine --rcfile=$(CURDIR)/coveragerc && cd ..
	$(Q) COVERAGE_FILE="$(TESTSETDIR)/coverage/.coverage" $(VMCOVERAGE_BIN) html --rcfile=$(CURDIR)/coveragerc -d $(TESTSETDIR)/coverage/
endif

tests-post: tests-post-master
	$(Q) echo "$(CC_GREEN)Avg # of instructions: `grep Executed $(shell find $(TESTSETDIR) -name '*.machine') | awk '{print $$5, " ", $$6}' | python tests/sum`/sec$(CC_END)"

tests-submit-results:
ifdef CIRCLE_TEST_REPORTS
	$(eval ts_results := $(wildard $(TESTSETDIR)/results/*.xml))
	$(Q) mkdir -p $(CIRCLE_TEST_REPORTS)/junit
	$(Q) for f in `ls -1 $(TESTSETDIR)/results/*.xml`; do g="`basename $$f`"; cp $$f $(CIRCLE_TEST_REPORTS)/junit/`echo "$$g" | sed 's/\(.*\).xml/$(TESTSET)-\1.xml/'`; done;
endif
ifdef CIRCLE_ARTIFACTS
	$(Q) cp -r $(TESTSETDIR) $(CIRCLE_ARTIFACTS)
endif

tests: tests-pre tests-in-subdirs tests-post tests-submit-results
	$(Q) if [ -e $(TESTSET_FAILED) ]; then /bin/false; fi

check: tests


#
# Utility targets
#

# Clean
clean-master:
	$(Q) rm -rf build dist
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
	cloc --skip-uniqueness --lang-no-ext=Python ducky/ forth/ examples/


flake:
	$(Q) ! flake8 --config=$(TOPDIR)/flake8.cfg $(shell find $(TOPDIR)/ducky $(TOPDIR)/tests -name '*.py') | sort | grep -v -e "'patch' imported but unused" -e duckyfs -e '\.swp' -e 'unable to detect undefined names'


pylint:
	$(Q) pylint --rcfile=pylintrc ducky


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
	$(Q) python setup.py install

install-edit:
	$(Q) pip install -e .

uninstall:
	$(Q) rm -rf $(shell find $(VIRTUAL_ENV) -name 'ducky-*' -type d)
	$(Q) rm -f  $(shell find $(VIRTUAL_ENV) -name 'ducky.egg-link')
