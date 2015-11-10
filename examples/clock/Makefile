include $(TOPDIR)/Makefile.inc

EXAMPLE := clock

TC_OUT := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).out
TC_MACHINE := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).machine


clock.o: $(TOPDIR)/defs.asm clock.asm
clock: clock.o
	$(run-linker)

build: clock

run: build
	$(Q) echo "[RUN] clock ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.clock.$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/clock.conf \
			 --set-option=machine:interrupt-routines=$(CURDIR)/clock \
			 --set-option=binary-0:file=$(CURDIR)/clock \
			 -g

tests-pre: build

tests: build
	$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.clock.$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/clock.conf \
			 --set-option=machine:interrupt-routines=$(CURDIR)/clock \
			 --set-option=binary-0:file=$(CURDIR)/clock \
			 --set-option=device-6:stream_out=$(TC_OUT) \
			 -g &> $(TC_MACHINE); \
			 if [[ $$? -ne 0 ]]; then \
			   touch $(TESTSET_FAILED); \
				 echo "$(CC_RED)FAIL$(CC_END)"; \
			 else \
			   echo "$(CC_GREEN)PASS$(CC_END)"; \
			 fi; \
			 exit 0;

tests-post:

clean:
	$(Q) rm -f clock.o clock
