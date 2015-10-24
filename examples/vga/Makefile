include $(TOPDIR)/Makefile.inc

EXAMPLE := vga


vga.o: vga.asm $(TOPDIR)/defs.asm
vga: vga.o
	$(run-linker)

build: vga

run:
	$(Q) echo "[RUN] $(EXAMPLE) ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(TOPDIR)/tools/vm $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/vga.conf \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(CURDIR)/vga \
			 -g

clean:
	$(Q) rm -f vga.o vga
