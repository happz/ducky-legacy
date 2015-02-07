SHELL := /bin/bash

SOURCES  := $(shell find $(CURDIR) -name '*.asm')
BINARIES := $(SOURCES:%.asm=%.bin)

FORTH_KERNEL := forth/ducky-forth.bin

forth/ducky-forth.bin: forth/ducky-forth.asm forth/ducky-forth-words.asm

.PHONY: tests-pre tests-engine tests-post test-submit-results tests docs cloc


#
# Tests
#
FORTH_TESTS_IN  := $(shell find $(CURDIR) -name 'test-*.f')
FORTH_TESTS_OUT := $(FORTH_TESTS_IN:%.f=%.f.out)

tests-pre:
	@mkdir -p $(CURDIR)/coverage
	@mkdir -p $(CURDIR)/profile
	@rm -f $(shell find $(CURDIR)/coverage -name '.coverage.*')
	@rm -f $(shell find $(CURDIR)/tests -name '*.xml')
	@rm -f $(shell find $(CURDIR)/tests/forth -name '*.out' -o -name '*.machine')
	@rm -rf coverage/*
	@rm -rf profile/*

tests-engine: tests/instructions/interrupts-basic.bin
	@echo "[TEST] Engine unit tests"
	-@COVERAGE_FILE="$(CURDIR)/coverage/.coverage.tests-engine" PYTHONPATH=$(CURDIR)/src nosetests -v --all-modules --with-coverage --with-xunit --xunit-file=$(CURDIR)/tests/nosetests.xml &> tests-engine.log

tests-forth-units: interrupts.bin $(FORTH_KERNEL) $(FORTH_TESTS_OUT)

tests-forth-asn: interrupts.bin $(FORTH_KERNEL)
	@echo "[TEST] FORTH ANS testsuite"
	-@PYTHONUNBUFFERED=yes PYTHONPATH=$(CURDIR)/src tools/vm --machine-config=$(CURDIR)/tests/test-machine.conf --machine-in=forth/ducky-forth.f --machine-in=tests/forth/ans/tester.fr --machine-in=tests/forth/ans/core.fr --machine-out=m.out -g

tests-post:
	# merge all coverage reports
	@cd coverage && coverage combine && cd ..
	# create html coverage report
	@COVERAGE_FILE="coverage/.coverage" coverage html -d coverage/

tests-submit-results:
ifdef CIRCLE_TEST_REPORTS
	@cp $(shell find $(CURDIR)/tests -name '*.xml') $(CIRCLE_TEST_REPORTS)/
endif
ifdef CIRCLE_ARTIFACTS
	@cp -r $(CURDIR)/coverage $(CIRCLE_ARTIFACTS)/
	@cp -r $(CURDIR)/tests-engine.log
endif

tests: tests-pre tests-engine tests-forth-units tests-post tests-submit-results


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
	@rm -f $(BINARIES) $(FORTH_TESTS_OUT) $(shell find $(CURDIR) -name '*.f.machine')


#
# Wildcard targets
#
%.bin: %.asm
	@echo "[COMPILE] $< => $@"
	@PYTHONPATH=$(CURDIR)/src tools/as -i $< -o $@ -f

%.f.out: %.f
	@echo "[TEST] FORTH $(notdir $(<:%.f=%))"
	-@COVERAGE_FILE="$(CURDIR)/coverage/.coverage.forth-unit.$(notdir $(<:%.f=%))" PYTHONUNBUFFERED=yes PYTHONPATH=$(CURDIR)/src coverage run tools/vm --machine-config=tests/forth/test-machine.conf --machine-in=forth/ducky-forth.f --machine-in=$< --machine-out=$@ -g --no-conio-echo &> $(@:%.f.out=%.f.machine)
	@$(CURDIR)/tests/xunit-record $(<:%.f=%.f.xml) $(notdir $(<:%.f=%)) $(subst /,.,$<)

