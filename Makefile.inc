SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c


CC_RED    := $(shell echo -e "\033[0;31m")
CC_GREEN  := $(shell echo -e "\033[0;32m")
CC_YELLOW := $(shell echo -e "\033[0;33m")
CC_END    := $(shell echo -e "\033[0m")


define run-cc
$(Q) echo -n "$(CC_YELLOW)[COMPILE]$(CC_END) $< => $@ ... "
$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.cc-$(subst /,-,$(abspath $<))-to-$(subst /,-,$(abspath $@)).$(DB_PID)"; else echo ""; fi) \
     $(PYTHON) $(VMCOVERAGE_RUN) $(DCC) -i $< -o $@ \
		 -O0 -q; \
		 if [ "$$?" -eq 0 ]; then \
		   echo "$(CC_GREEN)PASS$(CC_END)"; \
		 else \
		   echo "$(CC_RED)FAIL$(CC_END)"; \
		 fi;
endef


define run-as
$(Q) echo -n "$(CC_YELLOW)[COMPILE]$(CC_END) $< => $@ ... "
$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.as-$(subst /,-,$(abspath $<))-to-$(subst /,-,$(abspath $@)).$(DB_PID)"; else echo ""; fi) \
		 $(PYTHON) $(VMCOVERAGE_RUN) $(DAS) -i $< -o $@ \
		   -f \
		   $(shell if [ "$(MMAPABLE_SECTIONS)" = "yes" ]; then echo "--mmapable-sections"; else echo ""; fi) \
		   -I $(CURDIR) -I $(TOPDIR) \
		   $1 \
		   $(VMDEBUG); \
		 if [ "$$?" -eq 0 ]; then \
		   echo "$(CC_GREEN)PASS$(CC_END)"; \
		 else \
		   echo "$(CC_RED)FAIL$(CC_END)"; \
		 fi;
endef


define run-linker
$(Q) echo -n "$(CC_YELLOW)[LINK]$(CC_END) $^ => $@ ... "
$(Q) COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.ld-$(subst /,-,$(abspath $<))-to-$(subst /,-,$(abspath $@)).$(DB_PID)"; else echo ""; fi) \
		 $(PYTHON) $(VMCOVERAGE_RUN) $(DLD) -o $@ $(foreach objfile,$^,-i $(objfile)) \
		 $1 \
		 $(VMDEBUG); \
		 if [ "$$?" -eq 0 ]; then \
		   echo "$(CC_GREEN)PASS$(CC_END)"; \
		 else \
		   echo "$(CC_RED)FAIL$(CC_END)"; \
		 fi
endef


%.asm: %.c
	$(call run-cc)

%.o: %.asm
	$(call run-as)
