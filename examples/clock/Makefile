include $(TOPDIR)/Makefile.inc


clock.o: $(TOPDIR)/defs.asm clock.asm
clock: clock.o
	$(run-linker)

build: clock

run:
	$(Q) echo "[RUN] clock ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$1.$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/clock.conf \
			 --set-option=machine:interrupt-routines=$(CURDIR)/clock \
			 --set-option=binary-0:file=$(CURDIR)/clock \
			 -g

clean:
	$(Q) rm -f clock.o clock
