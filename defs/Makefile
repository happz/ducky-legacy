include $(TOPDIR)/Makefile.inc

DEFSDIR := $(TOPDIR)/defs

SOURCES := $(shell find $(DEFSDIR) -name '*.asm.in')
DEFINES := $(SOURCES:%.asm.in=%.asm)


all: $(DEFINES)

clean:
	$(Q) rm -f *.asm

%.asm: %.asm.in
	$(Q) echo -n "$(CC_YELLOW)[DEFS]$(CC_END) $^ => $@ ... "
	$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.template-$(subst /,-,$(abspath $<))-to-$(subst /,-,$(abspath $@)).$(DB_PID)"; else echo ""; fi) \
	     $(TOPDIR)/template.py $< > $@; \
			 if [ "$$?" -eq 0 ]; then \
			   echo "$(CC_GREEN)PASS$(CC_END)"; \
			 else \
			   echo "$(CC_RED)FAIL$(CC_END)"; \
			 fi
