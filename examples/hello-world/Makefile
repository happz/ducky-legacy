include $(TOPDIR)/Makefile.inc

EXAMPLE := hello-world

TC_MACHINE := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).machine
TC_OUT     := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).out

TC_MACHINE_SCREEN := $(TESTSETDIR)/$(EXAMPLE)-screen.$(DB_PID).machine
TC_OUT_SCREEN     := $(TESTSETDIR)/$(EXAMPLE)-screen.$(DB_PID).out


hello-world.o: $(TOPDIR)/defs.asm hello-world.asm
hello-world: hello-world.o
	$(run-linker)

build: hello-world

run: build
	$(Q) echo "[RUN] $(EXAMPLE) ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/hello-world.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/hello-world \
			 -g

run-screen: build
	$(Q) echo "[RUN] $(EXAMPLE) ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE)-screen.$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/hello-world.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/hello-world \
			 --set-option=device-3:driver=ducky.devices.terminal.StandalonePTYTerminal \
			 -g

tests-pre: build

test-run: build
	$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/hello-world.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/hello-world \
			 -g &> $(TC_MACHINE); \
			 if [[ $$? -ne 0 ]]; then \
			   touch $(TESTSET_FAILED); \
				 echo "$(CC_RED)FAIL$(CC_END)"; \
			 else \
			   echo "$(CC_GREEN)PASS$(CC_END)"; \
			 fi; \
			 exit 0;

test-run-screen: build
	$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) $(EXAMPLE) (screen) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE)-screen.$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/hello-world.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/hello-world \
			 --set-option=device-3:driver=ducky.devices.terminal.StandalonePTYTerminal \
			 -g &> $(TC_MACHINE_SCREEN); \
			 if [[ $$? -ne 0 ]]; then \
			   touch $(TESTSET_FAILED); \
			   echo "$(CC_RED)FAIL$(CC_END)"; \
			 else \
			   echo "$(CC_GREEN)PASS$(CC_END)"; \
			 fi; \
			 exit 0;

tests: test-run test-run-screen

tests-post:

clean:
	$(Q) rm -f hello-world.o hello-world
