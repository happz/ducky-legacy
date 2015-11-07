include $(TOPDIR)/Makefile.inc

EXAMPLE := hello-world-lib


main.o: main.asm
lib.o: lib.asm $(TOPDIR)/defs.asm
hello-world: main.o lib.o
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

tests-pre: build

tests: run

tests-post:

clean:
	$(Q) rm -f main.o lib.o hello-world
