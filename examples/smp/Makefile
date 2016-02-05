include $(TOPDIR)/Makefile.inc

EXAMPLE := smp

TC_MACHINE := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).machine
TC_OUT     := $(TESTSETDIR)/$(EXAMPLE).$(DB_PID).out


smp.o: $(DEFSDIR)/boot.asm $(DEFSDIR)/ducky.asm $(DEFSDIR)/control.asm $(DEFSDIR)/hdt.asm smp.asm

smp: smp.o $(TOPDIR)/boot/lib.o
	$(call run-linker,--section-base=.text=0x00000000)

smp.img: smp
	$(call run-binary-image,--bio)

build: smp smp.img

run: build
	$(Q) echo "[RUN] $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/smp.conf \
			 --set-option=bootloader:file=$(LOADER) \
			 --set-option=device-6:filepath=$(CURDIR)/smp.img \
			 -g $(VMPROFILE)

test-run: build
	$(Q) echo -n "[TEST] $(EXAMPLE) ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/smp.conf \
			 --set-option=bootloader:file=$(CURDIR)/smp \
			 --set-option=device-6:filepath=$(CURDIR)/smp.img \
			 -g $(VMPROFILE) &> $(TC_MACHINE); \
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
			 if [[ "$$(cat $(TC_OUT))" != $$'27816553665537' ]]; then touch $(TESTSET_FAILED); echo "$(CC_RED)FAIL$(CC_END)"; else echo "$(CC_GREEN)PASS$(CC_END)"; fi; \
			 exit 0;

tests-pre: build

tests: build test-run

tests-post:

clean:
	$(Q) rm -f smp.o smp smp.img
