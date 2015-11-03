include $(TOPDIR)/Makefile.inc

EXAMPLE := hello-world


hello-world.o: $(TOPDIR)/defs.asm hello-world.asm
hello-world: hello-world.o
	$(run-linker)

build: hello-world

run:
	$(Q) echo "[RUN] $(EXAMPLE) ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/hello-world.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/hello-world \
			 -g

run-screen:
	$(Q) echo "[RUN] $(EXAMPLE) ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE)-screen.$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/hello-world.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/hello-world \
			 --set-option=device-3:driver=ducky.devices.terminal.StandalonePTYTerminal \
			 -g


clean:
	$(Q) rm -f hello-world.o hello-world
