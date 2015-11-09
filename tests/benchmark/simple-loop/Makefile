include $(TOPDIR)/Makefile.inc

EXAMPLE := simple-loop

TC_NAME    := $(EXAMPLE)
TC_MACHINE := $(TC_DIR)/$(TC_NAME).$(DB_PID).machine

simple-loop.o: $(TOPDIR)/defs.asm simple-loop.asm
simple-loop: simple-loop.o
	$(run-linker)

build: simple-loop

run: simple-loop
	$(Q) echo -n "$(CC_YELLOW)[RUN]$(CC_END) $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/simple-loop.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/simple-loop -g &> $(TC_MACHINE); \
			 if [[ $$? -ne 0 ]]; then \
			   touch $(TESTSET_FAILED); \
				 echo "$(CC_RED)FAIL$(CC_END)"; \
			 else \
			   echo "$(CC_GREEN)`grep 'Executed instructions' $(TC_MACHINE) | awk '{print $$5, $$6, $$7}'`$(CC_END)"; \
			 fi;

tests-pre:

tests: run

tests-post:

clean:
	$(Q) rm -f simple-loop.o simple-loop
