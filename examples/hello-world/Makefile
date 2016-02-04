include $(TOPDIR)/Makefile.inc

EXAMPLE := hello-world

TC_MACHINE := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).machine
TC_OUT     := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).out

TC_MACHINE_SCREEN := $(TESTSETDIR)/$(EXAMPLE)-screen.$(DB_PID).machine
TC_OUT_SCREEN     := $(TESTSETDIR)/$(EXAMPLE)-screen.$(DB_PID).out

TC_OBJDUMP_OUT := $(TESTSETDIR)/$(EXAMPLE).objdump.$(DB_PID).out
TC_COREDUMP_OUT := $(TESTSETDIR)/$(EXAMPLE).coredump.$(DB_PID).out


hello-world.o: $(DEFSDIR)/tty.asm hello-world.asm
hello-world: hello-world.o
	$(call run-linker,--section-base=.text=0x00000000)

build: hello-world

run: build
	$(Q) echo "[RUN] $(EXAMPLE) ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/hello-world.conf \
			 --set-option=bootloader:file=$(CURDIR)/hello-world \
			 -g $(VMPROFILE)

run-screen: build
	$(Q) echo "[RUN] $(EXAMPLE) ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE)-screen.$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/hello-world.conf \
			 --set-option=bootloader:file=$(CURDIR)/hello-world \
			 --set-option=device-2:driver=ducky.devices.terminal.StandalonePTYTerminal \
			 -g $(VMPROFILE)

tests-pre: build

tests-objdump:
	$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) objdump $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.objdump.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DOD) $(VMDEBUG) \
			 -i hello-world.o -a &> $(TC_OBJDUMP_OUT); \
			 if [[ $$? -ne 0 ]]; then \
			   touch $(TESTSET_FAILED); \
				 echo "$(CC_RED)FAIL$(CC_END)"; \
			 else \
			   echo "$(CC_GREEN)PASS$(CC_END)"; \
			 fi; \
			 cat $(TC_OBJDUMP_OUT); \
			 exit 0;

tests-coredump:
	$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) coredump $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.coredump.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DCD) $(VMDEBUG) \
			 -i ducky-snapshot.bin -a &> $(TC_COREDUMP_OUT); \
			 if [[ $$? -ne 0 ]]; then \
			   touch $(TESTSET_FAILED); \
				 echo "$(CC_RED)FAIL$(CC_END)"; \
			 else \
			   echo "$(CC_GREEN)PASS$(CC_END)"; \
			 fi; \
			 cat $(TC_COREDUMP_OUT); \
			 exit 0;

test-run: build
	$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/hello-world.conf \
			 --set-option=bootloader:file=$(CURDIR)/hello-world \
			 -g $(VMPROFILE) &> $(TC_MACHINE); \
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
			 --set-option=bootloader:file=$(CURDIR)/hello-world \
			 --set-option=device-2:driver=ducky.devices.terminal.StandalonePTYTerminal \
			 -g $(VMPROFILE) &> $(TC_MACHINE_SCREEN); \
			 if [[ $$? -ne 0 ]]; then \
			   touch $(TESTSET_FAILED); \
			   echo "$(CC_RED)FAIL$(CC_END)"; \
			 else \
			   echo "$(CC_GREEN)PASS$(CC_END)"; \
			 fi; \
			 exit 0;

tests: test-run test-run-screen tests-objdump tests-coredump

tests-post:

clean:
	$(Q) rm -f hello-world.o hello-world
