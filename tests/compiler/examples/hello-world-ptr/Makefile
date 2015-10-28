include $(TOPDIR)/Makefile.inc

EXAMPLE := hello-world


TC_DIR      := $(TESTSETDIR)/compiler
TC_NAME     := hello-world
TC_OUT      := $(TC_DIR)/$(TC_NAME).$(DB_PID).out
TC_MACHINE  := $(TC_DIR)/$(TC_NAME).$(DB_PID).machine
TC_FILTERED := $(TC_DIR)/$(TC_NAME).$(DB_PID).filtered
TC_EXPECTED := $(CURDIR)/expected
TC_DIFF     := $(TC_DIR)/$(TC_NAME).$(DB_PID).diff
TC_TMPFILE  := $(shell mktemp)


hello-world.asm: hello-world.c
hello-world.o: hello-world.asm
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

tests-pre:

tests: build
	$(Q)  echo -n "$(CC_YELLOW)[TEST]$(CC_END) $(EXAMPLE) ... "
	$(Q)  COVERAGE_FILE=$(shell if [ "$(VMCOVERAGE)" = "yes" ]; then echo "$(TESTSETDIR)/coverage/.coverage.$(EXAMPLE).$(DB_PID)"; else echo ""; fi) \
	      $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) $(VMDEBUG) $(VMDEBUG_OPEN_FILES) \
			  --machine-config=$(CURDIR)/hello-world.conf \
			  --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			  --set-option=binary-0:file=$(CURDIR)/hello-world \
			  -g \
			  --set-device-option=device-3:stream_out=$(TC_OUT) \
			  $(foreach device,$(DUCKY_ENABLE_DEVICES),--enable-device=$(device)) \
			  $(foreach device,$(DUCKY_DISABLE_DEVICES),--disable-device=$(device)) \
	 	 	  $(VMDEBUG) $(VMDEBUG_OPEN_FILES) 2>&1 | stdbuf -oL -eL tee $(TC_MACHINE) | grep -v -e '\[INFO\] ' -e '#> ' | cat &> /dev/null
	-$(Q) if [ -f $(TC_EXPECTED) ]; then diff -u $(TC_EXPECTED) $(TC_OUT) | cat &> $(TC_DIFF); fi
	-$(Q) if [ ! -s $(TC_FILTERED) ] && ([ ! -f $(TC_DIFF) ] || [ ! -s $(TC_DIFF) ]); then \
	        $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$<; \
					echo "$(CC_GREEN)PASS$(CC_END)"; \
				else \
				  [ -f $(TC_FILTERED) ] && cat $(TC_FILTERED) >> $(TC_TMPFILE); \
					[ -f $(TC_DIFF) ] && cat $(TC_DIFF) >> $(TC_TMPFILE); \
					$(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$< --result=fail --message="Failed aserts" --diff=$(TC_TMPFILE); \
					echo "$(CC_RED)FAIL$(CC_END)"; \
					sed 's/^/  /' $(TC_TMPFILE); \
				fi;
	-$(Q) rm -f $(TC_TMPFILE)

tests-post:

clean:
	$(Q) rm -f hello-world.asm hello-world.o hello-world
