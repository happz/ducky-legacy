SHELL := /bin/bash

SOURCES  := $(shell find $(CURDIR) -name '*.asm')
BINARIES := $(SOURCES:%.asm=%.bin)

FORTH_KERNEL := forth/ducky-forth.bin

forth/ducky-forth.bin: forth/ducky-forth.asm forth/ducky-forth-words.asm

.PHONY: tests-pre tests-engine tests-post test-submit-results tests docs cloc


#
# Tests
#
FORTH_TESTS_IN  := $(shell find $(CURDIR) -name 'test-*.f' | sort)
FORTH_TESTS_OUT := $(FORTH_TESTS_IN:%.f=%.f.out)

ifdef VMDEBUG
  VMDEBUG := -d
else
  VMDEBUG :=
endif

ifndef CONIO_ECHO
  CONIO_ECHO := no
endif

ifndef CONIO_HIGHLIGHT
  CONIO_HIGHLIGHT := no
endif

ifdef PROFILE
  PROFILE := -p
else
  PROFILE :=
endif

ifndef COVERAGE
  COVERAGE=yes
endif

ifdef PYPY
  PYTHON := PYTHONPATH=$(VIRTUAL_ENV)/lib/python2.7/site-packages:$(CURDIR)/src /usr/bin/pypy
else
  PYTHON := PYTHONPATH=$(CURDIR)/src
endif


tests-pre:
	$(Q) mkdir -p $(CURDIR)/coverage
	$(Q) mkdir -p $(CURDIR)/profile
	$(Q) rm -f $(shell find $(CURDIR)/coverage -name '.coverage.*') $(shell find $(CURDIR)/tests -name '*.xml') $(shell find $(CURDIR)/tests -name '*.out') $(shell find $(CURDIR)/tests -name '*.machine') $(shell find $(CURDIR)/tests -name '*.diff')
	$(Q) rm -rf coverage/* profile/*
	$(Q) $(CURDIR)/tests/xunit-record --init --file=$(CURDIR)/tests/forth.xml --testsuite=units --testsuite=ans

tests-engine: tests/instructions/interrupts-basic.bin
	$(Q)  echo "[TEST] Engine unit tests"
	-$(Q) COVERAGE_FILE="$(CURDIR)/coverage/.coverage.tests-engine" PYTHONPATH=$(CURDIR)/src nosetests -v --all-modules --with-coverage --with-xunit --xunit-file=$(CURDIR)/tests/nosetests.xml &> tests/engine.out

tests-forth-units: interrupts.bin $(FORTH_KERNEL) $(FORTH_TESTS_OUT)

tests-forth-ans: interrupts.bin $(FORTH_KERNEL)
	$(Q)  echo "[TEST] FORTH ANS testsuite"
ifeq ($(COVERAGE),yes)
	$(eval COVERAGE_FILE := COVERAGE_FILE="$(CURDIR)/coverage/.coverage.forth-ans")
	$(eval COVERAGE_BIN  := $(VIRTUAL_ENV)/bin/coverage run)
else
	$(eval COVERAGE_FILE := )
	$(eval COVERAGE_BIN  := )
endif
	-$(Q) $(COVERAGE_FILE) $(PYTHON) $(COVERAGE_BIN) tools/vm $(PROFILE) --machine-config=$(CURDIR)/tests/forth/test-machine.conf --machine-in=tests/forth/enable-test-mode.f --machine-in=forth/ducky-forth.f --machine-in=tests/forth/ans/tester.fr --machine-in=tests/forth/ans/core.fr --machine-out=tests/forth/ans.out -g --conio-echo=$(CONIO_ECHO) --conio-console=no --conio-highlight=$(CONIO_HIGHLIGHT) --conio-stdout-echo=yes $(VMDEBUG) 2>&1 | stdbuf -oL -eL tee tests/forth/ans.machine | grep -v -e '\[INFO\] ' -e '#> '

tests-post:
	$(Q) cd coverage && coverage combine && cd ..
	$(Q) COVERAGE_FILE="coverage/.coverage" coverage html -d coverage/

tests-submit-results:
ifdef CIRCLE_TEST_REPORTS
	$(Q) cp $(shell find $(CURDIR)/tests -name '*.xml') $(CIRCLE_TEST_REPORTS)/
endif
ifdef CIRCLE_ARTIFACTS
	$(Q) cp -r $(CURDIR)/coverage $(CIRCLE_ARTIFACTS)/
	$(Q) cp $(shell find $(CURDIR)/tests -name '*.out') $(CIRCLE_ARTIFACTS)/
	$(Q) cp $(shell find $(CURDIR)/tests -name '*.machine') $(CIRCLE_ARTIFACTS)/
endif

tests: tests-pre tests-engine tests-forth-units tests-forth-ans tests-post tests-submit-results

tests-engine-only: tests-pre tests-engine tests-post tests-submit-results

tests-forth-only: tests-pre tests-forth-units tests-post tests-submit-results


#
# Some utility targets
#
cloc:
	cloc --skip-uniqueness src/ forth/ examples/

docs:
	sphinx-apidoc -o docs/ src/
	make -C docs clean
	make -C docs html

clean: tests-pre
	$(Q)rm -f $(BINARIES) $(FORTH_TESTS_OUT) $(shell find $(CURDIR) -name '*.f.machine')


#
# Wildcard targets
#
%.bin: %.asm
	$(Q) echo "[COMPILE] $< => $@"
	$(Q) $(PYTHON) tools/as -i $< -o $@ -f


%.f.out: %.f $(FORTH_KERNEL)
	$(eval tc_name     := $(notdir $(<:%.f=%)))
	$(eval tc_coverage := $(CURDIR)/coverage/.coverage.forth-unit.$(tc_name))
	$(eval tc_machine  := $(<:%.f=%.f.machine))
	$(eval tc_expected := $(<:%.f=%.f.expected))
	$(eval tc_diff     := $(<:%.f=%.f.diff))
ifeq ($(COVERAGE),yes)
	$(eval COVERAGE_FILE := COVERAGE_FILE="$(tc_coverage)")
	$(eval COVERAGE_BIN  := $(VIRTUAL_ENV)/bin/coverage run)
else
	$(eval COVERAGE_FILE := )
	$(eval COVERAGE_BIN  := )
endif
	$(Q)  echo "[TEST] FORTH $(tc_name)"
	-$(Q) $(COVERAGE_FILE) PYTHONUNBUFFERED=yes $(PYTHON) $(COVERAGE_BIN) tools/vm $(PROFILE) -g --conio-stdout-echo=yes --conio-echo=$(CONIO_ECHO) --conio-highlight=$(CONIO_HIGHLIGHT) --conio-console=no --machine-config=tests/forth/test-machine.conf --machine-in=tests/forth/enable-test-mode.f --machine-in=forth/ducky-forth.f --machine-in=$< --machine-in=tests/forth/run-test-word.f --machine-out=$@ $(VMDEBUG) 2>&1 | stdbuf -oL -eL tee $(tc_machine) | grep -v -e '\[INFO\] ' -e '#> '
	-$(Q) diff -u $(tc_expected) $@ &> $(tc_diff); \
	      if [ "$$?" = "0" ]; then \
				  $(CURDIR)/tests/xunit-record --add --file=$(CURDIR)/tests/forth.xml --ts=units --name=$(tc_name) --classname=$<; \
				else \
				  $(CURDIR)/tests/xunit-record --add --file=$(CURDIR)/tests/forth.xml --ts=units --name=$(tc_name) --classname=$< --result=fail; \
				fi
