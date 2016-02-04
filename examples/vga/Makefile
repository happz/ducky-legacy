include $(TOPDIR)/Makefile.inc

EXAMPLE := vga


vga.o: vga.asm $(DEFSDIR)/ducky.asm $(DEFSDIR)/svga.asm
vga: vga.o
	$(call run-linker,--section-base=.text=0x00000000)

build: vga

run: build
	$(Q) echo "[RUN] $(EXAMPLE) ..."
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			 --machine-config=$(CURDIR)/vga.conf \
			 --set-option=bootloader:file=$(CURDIR)/vga \
			 -g $(VMDEBUG)

tests-pre: build

tests: run

tests-post:

clean:
	$(Q) rm -f vga.o vga
