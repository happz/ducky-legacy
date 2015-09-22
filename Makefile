SHELL := /bin/bash

CC_RED=$(shell echo -e "\033[0;31m")
CC_GREEN=$(shell echo -e "\033[0;32m")
CC_YELLOW=$(shell echo -e "\033[0;33m")
CC_END=$(shell echo -e "\033[0m")

.PHONY: tests-pre tests-engine tests-post test-submit-results tests docs cloc flake

.PRECIOUS: %.o %.bin

PID := $(shell echo "$$$$")


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
  VMCOVERAGE_BIN := $(VIRTUAL_ENV)/bin/coverage run --branch --source=ducky
else
  VMCOVERAGE_BIN :=
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


#
# Helpers
#

define run-as
$(Q) echo -n "[COMPILE] $< => $@ ... "
$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.as-$(subst /,-,$<)-to-$(subst /,-,$@).$(PID)"; else echo ""; fi) \
	   DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) \
		   $(PYTHON) $(VMCOVERAGE_BIN) tools/as -i $< -o $@ \
		 -f \
		 $(shell if [ "$(MMAPABLE_SECTIONS)" = "yes" ]; then echo "--mmapable-sections"; else echo ""; fi) \
		 -I $(CURDIR) \
		 $1 \
		 $(VMDEBUG); \
		 if [ "$$?" -eq 0 ]; then \
		   echo "$(CC_GREEN)PASS$(CC_END)"; \
		 else \
		   echo "$(CC_RED)FAIL$(CC_END)"; \
		 fi;
endef


define run-linker
$(Q) echo -n "[LINK] $^ => $@ ... "
$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.ld-$(subst /,-,$<)-to-$(subst /,-,$@).$(PID)"; else echo ""; fi) \
	   DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) \
		 $(PYTHON) $(VMCOVERAGE_BIN) tools/ld -o $@ $(foreach objfile,$^,-i $(objfile)) \
		 $1 \
		 $(VMDEBUG); \
		 if [ "$$?" -eq 0 ]; then \
		   echo "$(CC_GREEN)PASS$(CC_END)"; \
		 else \
		   echo "$(CC_RED)FAIL$(CC_END)"; \
		 fi
endef


define run-simple-binary
$(Q) echo "[RUN] $1 ..."
$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$1.$(PID)"; else echo ""; fi) \
	   DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) \
		 $(PYTHON) $(VMCOVERAGE_BIN) tools/vm $(VMDEBUG) $(VMDEBUG_OPEN_FILES) --machine-config=$2 -g
endef


#
# FORTH
#

FORTH_KERNEL := forth/ducky-forth

forth/ducky-forth.o: forth/ducky-forth.asm forth/ducky-forth-words.asm forth/defs.asm defs.asm
	$(Q) echo "FORTH_DEBUG_FIND=$(FORTH_DEBUG_FIND)"
	$(call run-as,$(if $(filter yes,$(FORTH_DEBUG_FIND)),-D FORTH_DEBUG_FIND) $(if $(filter yes,$(FORTH_TEXT_WRITABLE)),-D FORTH_TEXT_WRITABLE --writable-sections,) $(if $(filter yes,$(FORTH_WELCOME)),-D FORTH_WELCOME))

forth/ducky-forth: forth/ducky-forth.o
	$(call run-linker,--section-base=.text=0x0000 --section-base=.userspace=0x5000)

forth: $(FORTH_KERNEL)


#
# Examples
#

# "Hello, world!"
examples/hello-world/hello-world.o: defs.asm examples/hello-world/hello-world.asm
examples/hello-world/hello-world: examples/hello-world/hello-world.o
	$(run-linker)

hello-world: interrupts examples/hello-world/hello-world

run-hello-world: hello-world
	$(call run-simple-binary,hello-world,examples/hello-world/hello-world.conf)


# "Hello, world!" using library
examples/hello-world-lib/lib.o: defs.asm examples/hello-world-lib/lib.asm
examples/hello-world-lib/main.o: defs.asm examples/hello-world-lib/main.asm
examples/hello-world-lib/hello-world: examples/hello-world-lib/lib.o examples/hello-world-lib/main.o
	$(run-linker)

hello-world-lib: interrupts examples/hello-world-lib/hello-world

run-hello-world-lib: hello-world-lib
	$(call run-simple-binary,hello-world-lib,examples/hello-world-lib/hello-world.conf)


# sVGA show-off
examples/vga/vga.o: defs.asm examples/vga/vga.asm
examples/vga/vga: examples/vga/vga.o
	$(run-linker)

vga: interrupts examples/vga/vga

run-vga: vga
	$(call run-simple-binary,vga,examples/vga/vga.conf)


# RTC "clocks"
examples/clock/clock.o: defs.asm examples/clock/clock.asm
examples/clock/clock: examples/clock/clock.o
	$(run-linker)

clock: interrupts examples/clock/clock

run-clock: clock
	$(call run-simple-binary,clock,examples/clock/clock.conf)


#
# Common binaries
#

# Basic interrupt routines

interrupts.o: interrupts.asm defs.asm
interrupts: interrupts.o
	$(run-linker)

# Test interrupt routines

tests/instructions/interrupts-basic.o: tests/instructions/interrupts-basic.asm defs.asm
tests/instructions/interrupts-basic: tests/instructions/interrupts-basic.o
	$(run-linker)


#
# Tests
#

FORTH_TESTS_IN  := $(shell find $(CURDIR) -name 'test-*.f' | sort)
FORTH_TESTS_OUT := $(FORTH_TESTS_IN:%.f=%.f.out)

# See tests/forth/ans/runtest.fth for full list
FORTH_ANS_TESTS := core.fr memorytest.fth # coreplustest.fth coreexttest.fth memorytest.fth toolstest.fth stringtest.fth
ENGINE_TESTS := $(shell find $(CURDIR)/tests/instructions/tests $(CURDIR)/tests/storage -name '*.asm')

tests-pre:
	$(Q) echo -n "[TEST] Create test set $(TESTSET) ... "
	$(Q) rm -rf $(TESTSETDIR)
	$(Q) mkdir -p $(TESTSETDIR)
	$(Q) mkdir -p $(TESTSETDIR)/coverage
	$(Q) mkdir -p $(TESTSETDIR)/profile
	$(Q) mkdir -p $(TESTSETDIR)/results
	$(Q) mkdir -p $(TESTSETDIR)/tmp
	$(Q) $(CURDIR)/tests/xunit-record --init --file=$(TESTSETDIR)/results/forth.xml --testsuite=forth-$(TESTSET)
	$(Q) echo "$(CC_GREEN)PASS$(CC_END)"
	$(Q) echo "Using python: $(CC_GREEN)$(PYTHON)$(CC_END)"


tests-engine: tests/instructions/interrupts-basic $(ENGINE_TESTS:%.asm=%.bin)
	$(Q)  echo "[TEST] Engine unit tests"
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(TESTSETDIR)/coverage/.coverage.engine.$(PID)")
	$(eval COVERAGE_NOSE_FLAG := --with-coverage --cover-branches --cover-package=ducky)
else
	$(eval VMCOVERAGE_FILE := )
	$(eval COVERAGE_NOSE_FLAG := )
endif
ifeq ($(VMDEBUG_OPEN_FILES),--debug-open-files)
	$(eval DEBUG_OPEN_FILES := yes)
else
	$(eval DEBUG_OPEN_FILES := no)
endif
	-$(Q) $(VMCOVERAGE_FILE) CURDIR=$(CURDIR) DEBUG_OPEN_FILES=$(DEBUG_OPEN_FILES) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) MMAPABLE_SECTIONS=$(MMAPABLE_SECTIONS) $(PYTHON) $(VIRTUAL_ENV)/bin/nosetests -v --all-modules $(COVERAGE_NOSE_FLAG) --with-xunit --xunit-file=$(TESTSETDIR)/results/nosetests.xml --no-path-adjustment --with-timer -w $(CURDIR)/tests 2>&1 | stdbuf -oL -eL tee $(TESTSETDIR)/engine.out | grep -v -e '\[INFO\] ' -e '#> '
	-$(Q) sed -i 's/<testsuite name="nosetests"/<testsuite name="nosetests-$(TESTSET)"/' $(TESTSETDIR)/results/nosetests.xml


tests-forth-units: interrupts $(FORTH_KERNEL) $(FORTH_TESTS_OUT)

tests-forth-ans: interrupts $(FORTH_KERNEL)
	$(Q) echo -n "[TEST] FORTH ANS testsuite ... "
	$(eval tc_out      := $(TESTSETDIR)/forth-ans.$(PID).out)
	$(eval tc_machine  := $(TESTSETDIR)/forth-ans.$(PID).machine)
	$(eval tc_filtered := $(TESTSETDIR)/forth-ans.$(PID).filtered)
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(TESTSETDIR)/coverage/.coverage.forth-ans.$(PID)")
else
	$(eval VMCOVERAGE_FILE := )
endif
	-$(Q) $(VMCOVERAGE_FILE) \
		    DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) \
				$(PYTHON) $(VMCOVERAGE_BIN) tools/vm \
				$(VMPROFILE) \
				$(BINPROFILE) -g \
				--machine-config=tests/forth/test-machine.conf \
				$(foreach testfile,$(FORTH_ANS_TESTS),--add-device-option=device-3:streams_in=tests/forth/ans/$(testfile)) \
				--set-device-option=device-3:stream_out=$(tc_out) \
				$(foreach device,$(DUCKY_ENABLE_DEVICES),--enable-device=$(device)) \
				$(foreach device,$(DUCKY_DISABLE_DEVICES),--disable-device=$(device)) \
				$(VMDEBUG) $(VMDEBUG_OPEN_FILES) 2>&1 | stdbuf -oL -eL tee $(tc_machine) | grep -v -e '\[INFO\] ' -e '#> '
	-$(Q) grep -e 'INCORRECT RESULT' -e 'WRONG NUMBER OF RESULTS' $(tc_out) | cat > $(tc_filtered);
	-$(Q) if [ ! -s $(tc_filtered) ]; then \
				  $(CURDIR)/tests/xunit-record --add --file=$(TESTSETDIR)/results/forth.xml --ts=forth-$(TESTSET) --name="ANS test suite"; \
					echo "$(CC_GREEN)PASS$(CC_END)"; \
				else \
				  $(CURDIR)/tests/xunit-record --add --file=$(TESTSETDIR)/results/forth.xml --ts=forth-$(TESTSET) --name="ANS test suite" --result=fail --message="Failed aserts" --diff=$(tc_filtered); \
					echo "$(CC_RED)FAIL$(CC_END)"; \
					sed -e 's/^/  /' $(tc_filtered); \
				fi


tests-post:
	$(Q) echo "$(CC_GREEN)Avg # of instructions: `grep Executed $(TESTSETDIR)/*.machine | awk '{print $$5, " ", $$6}' | python tests/sum`/sec$(CC_END)"
	$(Q) cd $(TESTSETDIR)/coverage && coverage combine && cd ..
ifeq ($(VMCOVERAGE),yes)
	$(Q) COVERAGE_FILE="$(TESTSETDIR)/coverage/.coverage" coverage html --omit="*/python2.7/*" -d $(TESTSETDIR)/coverage/
endif


tests-submit-results:
ifdef CIRCLE_TEST_REPORTS
	$(eval ts_results := $(wildard $(TESTSETDIR)/results/*.xml))
	$(Q) mkdir -p $(CIRCLE_TEST_REPORTS)/$(TESTSET)
	$(Q) for f in `ls -1 $(TESTSETDIR)/results/*.xml`; do g="`basename $$f`"; cp $$f $(CIRCLE_TEST_REPORTS)/`echo "$$g" | sed 's/\(.*\).xml/$(TESTSET)-\1.xml/'`; done;
endif
ifdef CIRCLE_ARTIFACTS
	$(Q) cp -r $(TESTSETDIR) $(CIRCLE_ARTIFACTS)
endif


tests: tests-pre tests-engine tests-forth-units tests-forth-ans run-hello-world run-hello-world-lib run-vga run-clock tests-post tests-submit-results


tests-engine-only: tests-pre tests-engine tests-post tests-submit-results


tests-forth-only: tests-pre tests-forth-units tests-forth-ans tests-post tests-submit-results


tests-interim-clean:
	$(Q) rm -f $(FORTH_KERNEL) interrupts `find $(CURDIR) -name '*.pyc'` `find $(CURDIR) -name '*.o'` `find $(CURDIR) -name '*.bin'` tests/instructions/interrupts-basic ducky-snapshot.bin


#
# Some utility targets
#

profile-eval:
	$(Q) python -i -c "import os; import pstats; ps = pstats.Stats(*['$(TESTSETDIR)/profile/%s' % f for f in os.listdir('$(TESTSETDIR)/profile/') if f.find('-Profile-') != -1])"


cloc:
	cloc --skip-uniqueness ducky/ forth/ examples/


flake:
	$(Q) ! flake8 --config=$(CURDIR)/flake8.cfg $(shell find $(CURDIR)/ducky $(CURDIR)/tests -name '*.py') $(shell find $(CURDIR)/tools) | sort | grep -v -e "'patch' imported but unused" -e tools/cc -e duckyfs -e '\.swp'


docs:
	cp README.rst docs/introduction.rst
	sphinx-apidoc -T -e -o docs/ ducky/
	make -C docs clean
	make -C docs html


build: ducky/native/data_cache.c
	python setup.py build --debug


install:
	python setup.py install


clean:
	$(Q) rm -f examples/hello-world/hello-world examples/hello-world-lib/hello-world examples/clock/clock examples/vga/vga $(FORTH_KERNEL) interrupts
	$(Q) rm -f `find $(CURDIR) -name '*.pyc'` `find $(CURDIR) -name '*.o'` `find $(CURDIR) -name '*.bin'` tests/instructions/interrupts-basic
	$(Q) rm -rf ducky-snapshot.bin build dist ducky.egg-info tests-python-egg-mmap tests-python-egg-read tests-python-devel-mmap tests-python-devel-read tests-pypy-devel-mmap tests-pypy-devel-mmap tests-pypy-devel-read tests-pypy-egg-mmap tests-pypy-egg-read


#
# Wildcard targets
#

%.o: %.asm
	$(call run-as)


%.bin: %.o
	$(call run-linker,$(if $(findstring tests,$^),--section-base=.text=0x0000))


%.f.out: %.f interrupts $(FORTH_KERNEL)
	$(eval tc_name     := $(notdir $(<:%.f=%)))
	$(eval tc_coverage := $(TESTSETDIR)/coverage/.coverage.forth-unit.$(tc_name).$(PID))
	$(eval tc_machine  := $(<:%.f=%.f.$(PID).machine))
	$(eval tc_filtered := $(<:%.f=%.f.$(PID).filtered))
	$(eval tc_expected := $(<:%.f=%.f.$(PID).expected))
	$(eval tc_diff     := $(<:%.f=%.f.$(PID).diff))
	$(eval tc_tmpfile  := $(shell mktemp))
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(tc_coverage)")
else
	$(eval VMCOVERAGE_FILE := )
endif
	$(Q)  echo -n "[TEST] FORTH $(tc_name) ... "
	-$(Q) $(VMCOVERAGE_FILE) \
		    DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) \
				PYTHONUNBUFFERED=yes \
				$(PYTHON) $(VMCOVERAGE_BIN) tools/vm \
				$(VMPROFILE) \
				$(BINPROFILE) -g \
				--machine-config=tests/forth/test-machine.conf \
				--add-device-option=device-3:streams_in=$< \
				--add-device-option=device-3:streams_in=tests/forth/run-test-word.f \
				--set-device-option=device-3:stream_out=$@ \
				$(foreach device,$(DUCKY_ENABLE_DEVICES),--enable-device=$(device)) \
				$(foreach device,$(DUCKY_DISABLE_DEVICES),--disable-device=$(device)) \
				$(VMDEBUG) $(VMDEBUG_OPEN_FILES) 2>&1 | stdbuf -oL -eL tee $(tc_machine) | grep -v -e '\[INFO\] ' -e '#> ' | cat
	-$(Q) grep -e 'INCORRECT RESULT' -e 'WRONG NUMBER OF RESULTS' $@ | cat > $(tc_filtered)
	-$(Q) if [ -f $(tc_expected) ]; then diff -u $(tc_expected) $@ | cat &> $(tc_diff); fi
	-$(Q) if [ ! -s $(tc_filtered) ] && ([ ! -f $(tc_diff) ] || [ ! -s $(tc_diff) ]); then \
				  $(CURDIR)/tests/xunit-record --add --file=$(TESTSETDIR)/results/forth.xml --ts=forth-$(TESTSET) --name=$(tc_name) --classname=$<; \
					echo "$(CC_GREEN)PASS$(CC_END)"; \
				else \
				  [ -f $(tc_filtered) ] && cat $(tc_filtered) >> $(tc_tmpfile); \
					[ -f $(tc_diff) ] && cat $(tc_diff) >> $(tc_tmpfile); \
				  $(CURDIR)/tests/xunit-record --add --file=$(TESTSETDIR)/results/forth.xml --ts=forth-$(TESTSET) --name=$(tc_name) --classname=$< --result=fail --message="Failed aserts" --diff=$(tc_tmpfile); \
					echo "$(CC_RED)FAIL$(CC_END)"; \
					sed 's/^/  /' $(tc_tmpfile); \
				fi; \
				rm -f $(tc_tmpfile)
	-$(Q) mv $@ $(TESTSETDIR)/
	-$(Q) if [ -f $(tc_machine) ]; then mv $(tc_machine) $(TESTSETDIR)/; fi
	-$(Q) if [ -f $(tc_diff) ]; then mv $(tc_diff) $(TESTSETDIR)/; fi
	-$(Q) if [ -f $(tc_filtered) ]; then mv $(tc_filtered) $(TESTSETDIR)/; fi
