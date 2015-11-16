include $(TOPDIR)/Makefile.inc

EXAMPLE := smp

TC_MACHINE := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).machine
TC_OUT     := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).out

TC_OBJDUMP_OUT := $(TESTSETDIR)/$(EXAMPLE).objdump.$(DB_PID).out
TC_COREDUMP_OUT := $(TESTSETDIR)/$(EXAMPLE).coredump.$(DB_PID).out
					 

smp.o: $(TOPDIR)/defs.asm smp.asm
smp: smp.o
	$(call run-linker,--section-base=.cwt=0x8000)

build: smp

run: build
	$(Q) echo "[RUN] $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/smp.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/smp \
			 -g

test-run: build
	$(Q) echo -n "[TEST] $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/smp.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/smp \
			 -g &> $(TC_MACHINE); \
			 if [[ $$? -ne 1 ]]; then touch $(TESTSET_FAILED); echo "$(CC_RED)FAIL$(CC_END)"; else echo "$(CC_GREEN)PASS$(CC_END)"; fi; \
			 exit 0;
	$(Q) echo -n "[TEST] $(EXAMPLE) coredump ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).coredump.$(DB_PID)"; else echo ""; fi) \
			 $(PYTHON) $(VMCOVERAGE_RUN) $(DCD) $(VMDEBUG) \
			 -i ducky-snapshot.bin -q \
			 -Q "STATE.get_child('machine').get_cpu_state_by_id(0).get_core_state_by_id(0).registers[0]" \
			 -Q "STATE.get_child('machine').get_cpu_state_by_id(0).get_core_state_by_id(1).registers[0]" \
			 -Q "STATE.get_child('machine').get_cpu_state_by_id(1).get_core_state_by_id(0).registers[0]" \
			 -Q "STATE.get_child('machine').get_cpu_state_by_id(1).get_core_state_by_id(1).registers[0]" &> $(TC_OUT); \
			 if [[ "$$(cat $(TC_OUT))" != $$'0409743524353' ]]; then echo "$(CC_RED)FAIL$(CC_END)"; else echo "$(CC_GREEN)PASS$(CC_END)"; fi; \
			 exit 0;

tests-pre: build

tests: build test-run

tests-post:

clean:
	$(Q) rm -f smp.o smp
