TOPDIR := $(CURDIR)
export TOPDIR

DB_PID := $(shell echo "$$$$")
export DB_PID

DCC := $(shell which ducky-cc)
DAS := $(shell which ducky-as)
DLD := $(shell which ducky-ld)
DVM := $(shell which ducky-vm)
DOD := $(shell which ducky-objdump)
DCD := $(shell which ducky-coredump)
DIM := $(shell which ducky-img)

export DAS
export DCC
export DLD
export DVM
export DOD
export DCD
export DIM


include Makefile.inc


.PHONY: tests tests-pre tests-post test-submit-results docs cloc flake forth hello-world hello-world-lib clock vga


all: loader hello-world hello-world-lib clock vga smp


#
#
#

SUBDIRS := docs boot examples forth tests


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
  PYTHON_INTERPRET := pypy
	PYTHON := pypy
else
  PYTHON_INTERPRET := python
  PYTHON :=
endif

# Use mmapable sections
ifndef MMAPABLE_SECTIONS
  MMAPABLE_SECTIONS := no
endif

ifndef FORTH_DEBUG_FIND
  FORTH_DEBUG_FIND := no
endif

ifndef FORTH_DEBUG
  FORTH_DEBUG := no
endif

ifndef FORTH_WELCOME
  FORTH_WELCOME := no
endif

ifndef VERIFY_DISASSEMBLE
  VERIFY_DISASSEMBLE := no
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
# Assembler defines
#

DEFSDIR := $(TOPDIR)/defs
export DEFSDIR


defines:
	$(Q) $(MAKE) -C defs/ all


#
# Loader
#

LOADER := $(TOPDIR)/boot/loader
export LOADER

ifndef DUCKY_BOOT_IMG
  DUCKY_BOOT_IMG :=
endif

loader: defines
	$(Q) $(MAKE) -C boot/ build


#
# FORTH
#

FORTH_KERNEL := $(TOPDIR)/forth/ducky-forth
export FORTH_KERNEL

forth: defines
	$(Q) make -C forth/ kernel


#
# Examples
#


# Hello, world!
hello-world: defines
	$(Q) $(MAKE) -C examples/hello-world build

run-hello-world: hello-world
	$(Q) $(MAKE) -C examples/hello-world run

# Hello, world! with screen terminal
hello-world-screen: hello-world

run-hello-world-screen: hello-world-screen
	$(Q) $(MAKE) -C examples/hello-world run-screen


# Clock
clock: defines
	$(Q) $(MAKE) -C examples/clock build

run-clock: clock
	$(Q) $(MAKE) -C examples/clock run


# "Hello, world!" using library
hello-world-lib: defines
	$(Q) $(MAKE) -C examples/hello-world-lib build

run-hello-world-lib: hello-world-lib
	$(Q) $(MAKE) -C examples/hello-world-lib run


# sVGA show-off
vga: defines
	$(Q) $(MAKE) -C examples/vga build

run-vga: vga
	$(Q) $(MAKE) -C examples/vga run


# SMP show-off
smp: defines
	$(Q) $(MAKE) -C examples/smp build

run-smp: loader smp
	$(Q) $(MAKE) -C examples/smp run


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
	$(Q) echo "$(CC_YELLOW)Python version:$(CC_END) $(CC_GREEN)$(shell $(PYTHON_INTERPRET) --version 2>&1 | tr '\n' ' ')$(CC_END)"
	$(Q) echo "$(CC_YELLOW)Test set directory:$(CC_END) $(CC_GREEN)$(TESTSETDIR)$(CC_END)"

tests-pre: tests-pre-master defines forth loader
	$(Q) $(MAKE) -C tests/ tests-pre
	$(Q) $(MAKE) -C examples/ tests-pre

tests-in-subdirs:
	$(Q) $(MAKE) -C tests/ tests
	$(Q) $(MAKE) -C examples/ tests

tests-post-master:
	$(Q) $(MAKE) -C tests/ tests-post
	$(Q) $(MAKE) -C examples/ tests-post
ifeq ($(VMCOVERAGE),yes)
	$(Q) cd $(TESTSETDIR)/coverage && $(VMCOVERAGE_BIN) combine --rcfile=$(CURDIR)/coveragerc && cd ..
	$(Q) COVERAGE_FILE="$(TESTSETDIR)/coverage/.coverage" $(VMCOVERAGE_BIN) html --rcfile=$(CURDIR)/coveragerc -d $(TESTSETDIR)/coverage/
endif

tests-stats:
	$(Q) echo "$(CC_GREEN)Avg # of instructions: `grep Executed $(shell find $(TESTSETDIR) -name '*.machine') | awk '{print $$5, " ", $$6}' | python tests/sum`/sec$(CC_END)"

tests-post: tests-post-master tests-stats

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

benchmark: tests-pre-master defines
	$(Q) $(MAKE) -C tests/benchmark tests-pre
	$(Q) $(MAKE) -C tests/benchmark tests
	$(Q) $(MAKE) -C tests/benchmark tests-post
	$(Q) $(MAKE) -C $(TOPDIR) tests-stats

check: tests


#
# Utility targets
#

# Clean
clean-master:
	$(Q) rm -rf build dist
	$(Q) find $(TOPDIR) -name 'ducky-snapshot.bin' -print0 | xargs -0 rm -f
	$(Q) find $(TOPDIR) -name '*.pyc' -print0 | xargs -0 rm -f
	$(Q) find $(TOPDIR) -name '*.pyo' -print0 | xargs -0 rm -f
	$(Q) find $(TOPDIR) -name '*.o' -print0 | xargs -0 rm -f

clean-testsets:
	$(Q) rm -rf tests-*

clean-in-subdirs:
	$(Q) $(MAKE) -C defs/ clean
	$(Q) for dir in $(SUBDIRS); do \
	       $(MAKE) -C $$dir clean; \
	     done

clean: clean-master clean-testsets clean-in-subdirs


profile-eval:
	$(Q) python -i -c "import os; import pstats; ps = pstats.Stats(*['$(TESTSETDIR)/profile/%s' % f for f in os.listdir('$(TESTSETDIR)/profile/') if f.find('-Profile-') != -1])"


cloc:
	cloc --skip-uniqueness --lang-no-ext=Python boot/ defs/ ducky/ forth/ examples/


flake:
	$(Q) ! flake8 --config=$(TOPDIR)/flake8.cfg $(shell find $(TOPDIR)/ducky $(TOPDIR)/tests -name '*.py' | grep -v vhdl) | sort | grep -v -e "'patch' imported but unused" -e duckyfs -e '\.swp' -e 'unable to detect undefined names'


pylint:
	$(Q) pylint --rcfile=pylintrc ducky


# Documentation
docs: loader
	cp README.rst docs/introduction.rst
	sphinx-apidoc -T -e -o docs/ ducky/
	#$(MAKE) -C docs/ clean
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
	$(Q) rm -rf $(shell find $(VIRTUAL_ENV) -name 'ducky-*' -type d | grep -v "^$(VIRTUAL_ENV)$$")
	$(Q) rm -f  $(shell find $(VIRTUAL_ENV) -name 'ducky.egg-link')

publish:
	$(Q) python setup.py sdist upload
