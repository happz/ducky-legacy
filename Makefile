SHELL := /bin/bash

CC_RED=$(shell echo -e "\033[0;31m")
CC_GREEN=$(shell echo -e "\033[0;32m")
CC_YELLOW=$(shell echo -e "\033[0;33m")
CC_END=$(shell echo -e "\033[0m")

INSTALLED_EGG := $(VIRTUAL_ENV)/lib/python2.7/site-packages/ducky-1.0-py2.7.egg

.PHONY: tests-pre tests-engine tests-post test-submit-results tests docs cloc flake

.PRECIOUS: %.o %.bin


#
# Tests
#
FORTH_TESTS_IN  := $(shell find $(CURDIR) -name 'test-*.f' | sort)
FORTH_TESTS_OUT := $(FORTH_TESTS_IN:%.f=%.f.out)

# See tests/forth/ans/runtest.fth for full list
FORTH_ANS_TESTS := core.fr memorytest.fth # coreplustest.fth coreexttest.fth memorytest.fth toolstest.fth stringtest.fth
ENGINE_TESTS := $(shell find $(CURDIR)/tests/instructions/tests $(CURDIR)/tests/storage -name '*.asm')


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
  PYPY_BINARY=$(shell pyenv which pypy-2.4.0)
else
  PYPY_BINARY=$(shell which pypy)
endif
  # pypy does not see our local installed packages
	PYTHON := PYTHONPATH="$(INSTALLED_EGG):$(VIRTUAL_ENV)/lib/python2.7/site-packages:$(PYTHONPATH)" $(PYPY_BINARY)
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
# FORTH
#
FORTH_KERNEL := forth/ducky-forth
FORTH_LD_OPTIONS := --section-base=.text=0x0000 --section-base=.userspace=0x5000

forth/ducky-forth.o: forth/ducky-forth.asm forth/ducky-forth-words.asm
$(FORTH_KERNEL): forth/ducky-forth.o
	$(Q) echo -n "[LINK] $^ => $@ ... "
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/ld -o $@ $(foreach objfile,$^,-i $(objfile)) $(FORTH_LD_OPTIONS) $(VMDEBUG); if [ "$$?" -eq 0 ]; then echo "$(CC_GREEN)PASS$(CC_END)"; else echo "$(CC_RED)FAIL$(CC_END)"; fi

forth: $(FORTH_KERNEL)

#
# Examples
#

examples/hello-world/hello-world: examples/hello-world/hello-world.o
	$(Q) echo -n "[LINK] $^ => $@ ... "
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/ld -o $@ $(foreach objfile,$^,-i $(objfile)) $(VMDEBUG); if [ "$$?" -eq 0 ]; then echo "$(CC_GREEN)PASS$(CC_END)"; else echo "$(CC_RED)FAIL$(CC_END)"; fi

hello-world: interrupts examples/hello-world/hello-world

run-hello-world: hello-world
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/vm $(VMDEBUG) $(VMDEBUG_OPEN_FILES) --machine-config=examples/hello-world/hello-world.conf -g

examples/hello-world-lib/hello-world: examples/hello-world-lib/lib.o examples/hello-world-lib/main.o
	$(Q) echo -n "[LINK] $^ => $@ ... "
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/ld -o $@ $(foreach objfile,$^,-i $(objfile)) $(VMDEBUG); if [ "$$?" -eq 0 ]; then echo "$(CC_GREEN)PASS$(CC_END)"; else echo "$(CC_RED)FAIL$(CC_END)"; fi

hello-world-lib: interrupts examples/hello-world-lib/hello-world

run-hello-world-lib: hello-world-lib
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/vm $(VMDEBUG_OPEN_FILES) --machine-config=examples/hello-world-lib/hello-world.conf -g

examples/vga/vga: examples/vga/vga.o
	$(Q) echo -n "[LINK] $^ => $@ ... "
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/ld -o $@ $(foreach objfile,$^,-i $(objfile)) $(VMDEBUG); if [ "$$?" -eq 0 ]; then echo "$(CC_GREEN)PASS$(CC_END)"; else echo "$(CC_RED)FAIL$(CC_END)"; fi

vga: interrupts examples/vga/vga


interrupts: interrupts.o
	$(Q) echo -n "[LINK] $^ => $@ ... "
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/ld -o $@ $(foreach objfile,$^,-i $(objfile)) $(VMDEBUG); if [ "$$?" -eq 0 ]; then echo "$(CC_GREEN)PASS$(CC_END)"; else echo "$(CC_RED)FAIL$(CC_END)"; fi

tests/instructions/interrupts-basic: tests/instructions/interrupts-basic.o
	$(Q) echo -n "[LINK] $^ => $@ ... "
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/ld -o $@ $(foreach objfile,$^,-i $(objfile)) $(VMDEBUG); if [ "$$?" -eq 0 ]; then echo "$(CC_GREEN)PASS$(CC_END)"; else echo "$(CC_RED)FAIL$(CC_END)"; fi

run: interrupts $(FORTH_KERNEL)
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(CURDIR)/.coverage.run")
	$(eval VMCOVERAGE_BIN  := $(VIRTUAL_ENV)/bin/coverage run)
else
	$(eval VMCOVERAGE_FILE := )
	$(eval VMCOVERAGE_BIN  := )
endif
	$(Q) $(VMCOVERAGE_FILE) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) PYTHONUNBUFFERED=yes $(PYTHON) $(VMCOVERAGE_BIN) tools/vm $(VMPROFILE) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) $(BINPROFILE) --machine-config=tests/forth/test-machine.conf --machine-in=forth/ducky-forth.f

run-binary: interrupts
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(CURDIR)/.coverage.run")
	$(eval VMCOVERAGE_BIN  := $(VIRTUAL_ENV)/bin/coverage run)
else
	$(eval VMCOVERAGE_FILE := )
	$(eval VMCOVERAGE_BIN  := )
endif
	$(Q) $(VMCOVERAGE_FILE) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) PYTHONUNBUFFERED=yes $(PYTHON) $(VMCOVERAGE_BIN) tools/vm $(VMPROFILE) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) $(BINPROFILE) --machine-config=$(MACHINE_CONFIG) -g

run-forth-script: interrupts $(FORTH_KERNEL)
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(CURDIR)/.coverage.run")
	$(eval VMCOVERAGE_BIN  := $(VIRTUAL_ENV)/bin/coverage run)
else
	$(eval VMCOVERAGE_FILE := )
	$(eval VMCOVERAGE_BIN  := )
endif
	$(Q) $(VMCOVERAGE_FILE) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) PYTHONUNBUFFERED=yes $(PYTHON) $(VMCOVERAGE_BIN) tools/vm $(VMPROFILE) $(VMDEBUG) $(BINPROFILE) --machine-config=tests/forth/test-machine.conf --machine-in=forth/ducky-forth.f --machine-in=$(FORTH_SCRIPT) -g

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
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(TESTSETDIR)/coverage/.coverage.engine")
	$(eval COVERAGE_NOSE_FLAG := --with-coverage --cover-branches)
else
	$(eval VMCOVERAGE_FILE := )
	$(eval COVERAGE_NOSE_FLAG := )
endif
ifeq ($(VMDEBUG_OPEN_FILES),--debug-open-files)
	$(eval DEBUG_OPEN_FILES := yes)
else
	$(eval DEBUG_OPEN_FILES := no)
endif
	-$(Q) $(VMCOVERAGE_FILE) CURDIR=$(CURDIR) DEBUG_OPEN_FILES=$(DEBUG_OPEN_FILES) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) MMAPABLE_SECTIONS=$(MMAPABLE_SECTIONS) $(PYTHON) $(VIRTUAL_ENV)/bin/nosetests -v --with-timer --timer-top-n 10 --all-modules $(COVERAGE_NOSE_FLAG) --with-xunit --xunit-file=$(TESTSETDIR)/results/nosetests.xml --no-path-adjustment -w $(CURDIR)/tests 2>&1 | stdbuf -oL -eL tee $(TESTSETDIR)/engine.out | grep -v -e '\[INFO\] ' -e '#> '
	-$(Q) sed -i 's/<testsuite name="nosetests"/<testsuite name="nosetests-$(TESTSET)"/' $(TESTSETDIR)/results/nosetests.xml

tests-forth-units: interrupts $(FORTH_KERNEL) $(FORTH_TESTS_OUT)

tests-forth-ans: interrupts $(FORTH_KERNEL)
	$(Q) echo -n "[TEST] FORTH ANS testsuite ... "
	$(eval tc_out      := $(TESTSETDIR)/forth-ans.out)
	$(eval tc_machine  := $(TESTSETDIR)/forth-ans.machine)
	$(eval tc_filtered := $(TESTSETDIR)/forth-ans.filtered)
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(TESTSETDIR)/coverage/.coverage.forth-ans")
	$(eval VMCOVERAGE_BIN  := $(VIRTUAL_ENV)/bin/coverage run)
else
	$(eval VMCOVERAGE_FILE := )
	$(eval VMCOVERAGE_BIN  := )
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

tests: tests-pre tests-engine tests-forth-units tests-forth-ans tests-post tests-submit-results

tests-engine-only: tests-pre tests-engine tests-post tests-submit-results

tests-forth-only: tests-pre tests-forth-units tests-forth-ans tests-post tests-submit-results


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

install:
	python setup.py install

clean:
	$(Q) rm -f examples/hello-world/hello-world examples/hello-world-lib/hello-world $(FORTH_KERNEL) interrupts
	$(Q) rm -f `find $(CURDIR) -name '*.pyc'` `find $(CURDIR) -name '*.o'` `find $(CURDIR) -name '*.bin'` tests/instructions/interrupts-basic
	$(Q) rm -rf ducky-snapshot.bin build dist ducky.egg-info tests-python-egg-mmap tests-python-egg-read tests-python-devel-mmap tests-python-devel-read tests-pypy-devel-mmap tests-pypy-devel-mmap tests-pypy-devel-read tests-pypy-egg-mmap tests-pypy-egg-read


#
# Wildcard targets
#

%.o: %.asm
ifeq ($(MMAPABLE_SECTIONS),yes)
	$(eval mmapable_sections := --mmapable-sections)
else
	$(eval mmapable_sections := )
endif
ifeq ($(FORTH_DEBUG_FIND),yes)
	$(eval forth_debug_find := -D FORTH_DEBUG_FIND)
else
	$(eval forth_debug_find := )
endif
ifeq ($(FORTH_TEXT_WRITABLE),yes)
	$(eval forth_text_writable := -D FORTH_TEXT_WRITABLE --writable-sections)
else
	$(eval forth_text_writable := )
endif
ifeq ($(FORTH_WELCOME),yes)
	$(eval forth_welcome := -D FORTH_WELCOME)
else
	$(eval forth_welcome := )
endif
	$(Q) echo -n "[COMPILE] $< => $@ ... "
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/as -i $< -o $@ -f $(mmapable_sections) $(forth_debug_find) $(forth_text_writable) $(forth_welcome) $(VMDEBUG); if [ "$$?" -eq 0 ]; then echo "$(CC_GREEN)PASS$(CC_END)"; else echo "$(CC_RED)FAIL$(CC_END)"; fi


%.bin: %.o
	$(eval ld_flags := )
	$(if $(findstring tests,$^), $(eval ld_flags := --section-base=.text=0x0000))
	$(Q) echo -n "[LINK] $^ => $@ ... "
	$(Q) DUCKY_IMPORT_DEVEL=$(DUCKY_IMPORT_DEVEL) $(PYTHON) tools/ld -o $@ $(foreach objfile,$^,-i $(objfile)) $(ld_flags) $(VMDEBUG); if [ "$$?" -eq 0 ]; then echo "$(CC_GREEN)PASS$(CC_END)"; else echo "$(CC_RED)FAIL$(CC_END)"; fi


%.f.out: %.f interrupts $(FORTH_KERNEL)
	$(eval tc_name     := $(notdir $(<:%.f=%)))
	$(eval tc_coverage := $(TESTSETDIR)/coverage/.coverage.forth-unit.$(tc_name))
	$(eval tc_machine  := $(<:%.f=%.f.machine))
	$(eval tc_filtered := $(<:%.f=%.f.filtered))
	$(eval tc_expected := $(<:%.f=%.f.expected))
	$(eval tc_diff     := $(<:%.f=%.f.diff))
	$(eval tc_tmpfile  := $(shell mktemp))
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(tc_coverage)")
	$(eval VMCOVERAGE_BIN  := $(VIRTUAL_ENV)/bin/coverage run)
else
	$(eval VMCOVERAGE_FILE := )
	$(eval VMCOVERAGE_BIN  := )
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
