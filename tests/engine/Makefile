include $(TOPDIR)/Makefile.inc

.PHONY: tests-pre tests clean
.PRECIOUS: %.o %.testbin

ENGINE_TESTS := $(shell find tests/instructions/tests tests/storage -name '*.asm')

ifeq ($(VMCOVERAGE),yes)
  COVERAGE_FILE := $(TESTSETDIR)/coverage/.coverage.engine.$(DB_PID)
  COVERAGE_NOSE_FLAG := --with-coverage --cover-branches --cover-package=ducky
else
  COVERAGE_FILE :=
  COVERAGE_NOSE_FLAG :=
endif

ifeq ($(VMDEBUG_OPEN_FILES),--debug-open-files)
  DEBUG_OPEN_FILES := yes
else
  DEBUG_OPEN_FILES := no
endif

TC_DIR     := $(TESTSETDIR)/engine
TC_OUTPUT  := $(TC_DIR)/engine.out
TC_RESULTS := $(TESTSETDIR)/results/engine.xml

export CURDIR
export COVERAGE_FILE
export DEBUG_OPEN_FILES


tests/instructions/interrupts-basic.o: tests/instructions/interrupts-basic.asm $(TOPDIR)/defs.asm
tests/instructions/interrupts-basic:   tests/instructions/interrupts-basic.o
	$(run-linker)

tests-pre:
	$(Q) mkdir -p $(TC_DIR)

tests: tests/instructions/interrupts-basic $(ENGINE_TESTS:%.asm=%.testbin)
	-$(Q) echo "$(CC_YELLOW)[TEST]$(CC_END) Engine unit tests"
	-$(Q) $(PYTHON) $(VIRTUAL_ENV)/bin/nosetests -v --all-modules $(COVERAGE_NOSE_FLAG) \
	      --with-xunit --xunit-file=$(TC_RESULTS) \
			  --no-path-adjustment \
			  -w tests 2>&1 | stdbuf -o L -eL tee $(TC_OUTPUT) | grep -v -e '\[INFO\] ' -e '#> '; \
				if [[ $$? -ne 0 ]]; then touch $(TESTSET_FAILED); fi
	-$(Q) sed -i 's/<testsuite name="nosetests"/<testsuite name="nosetests-$(TESTSET)"/' $(TC_RESULTS)

tests-post:

clean:
	$(Q) rm -f tests/instructions/interrupts-basic.o tests/instructions/interrupts-basic $(ENGINE_TESTS:%.asm=%.testbin)

%.testbin: %.o
	$(call run-linker,--section-base=.text=0x0000)
