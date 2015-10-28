include $(TOPDIR)/Makefile.inc


FORTH_TESTS_IN  := $(shell find $(CURDIR) -name 'test-*.f' | sort)
FORTH_TESTS_OUT := $(FORTH_TESTS_IN:%.f=%.f.out)

TC_DIR := $(TC_DIR)/unit

tests-pre:
	$(Q) mkdir -p $(TC_DIR)

tests: $(TOPDIR)/interrupts $(FORTH_KERNEL) $(FORTH_TESTS_OUT)

%.f.out: %.f $(TOPDIR)/interrupts $(FORTH_KERNEL)
	$(eval TC_NAME     := $(notdir $(<:%.f=%)))
	$(eval TC_OUTPUT   := $(TC_DIR)/$(TC_NAME).$(DB_PID).out)
	$(eval TC_COVERAGE := $(TESTSETDIR)/coverage/.coverage.forth-unit.$(TC_NAME).$(DB_PID))
	$(eval TC_MACHINE  := $(TC_DIR)/$(TC_NAME).$(DB_PID).machine)
	$(eval TC_FILTERED := $(TC_DIR)/$(TC_NAME).$(DB_PID).filtered)
	$(eval TC_EXPECTED := $(<:%.f=%.f.expected))
	$(eval TC_DIFF     := $(TC_DIR)/$(TC_NAME).$(DB_PID).diff)
	$(eval TC_TMPFILE  := $(shell mktemp))
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(TC_COVERAGE)")
else
	$(eval VMCOVERAGE_FILE := )
endif
	-$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) FORTH $(TC_NAME) ... "
	-$(Q) PYTHONUNBUFFERED=yes \
	      $(VMCOVERAGE_FILE) \
	      $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) \
				$(VMPROFILE) \
				$(BINPROFILE) -g \
				--machine-config=$(TC_CONFIG) \
				--set-option=machine:interrupt-routines=$(INTERRUPTS) \
				--set-option=binary-0:file=$(FORTH_KERNEL) \
				--set-device-option=device-3:streams_in=$(CURDIR)/../enable-test-mode.f \
				--add-device-option=device-3:streams_in=$(TOPDIR)/forth/ducky-forth.f \
				--add-device-option=device-3:streams_in=$(CURDIR)/../ans/tester.fr \
				--add-device-option=device-3:streams_in=$< \
				--add-device-option=device-3:streams_in=$(CURDIR)/../run-test-word.f \
				--set-device-option=device-3:stream_out=$(TC_OUTPUT) \
				$(foreach device,$(DUCKY_ENABLE_DEVICES),--enable-device=$(device)) \
				$(foreach device,$(DUCKY_DISABLE_DEVICES),--disable-device=$(device)) \
				$(VMDEBUG) $(VMDEBUG_OPEN_FILES) 2>&1 | stdbuf -oL -eL tee $(TC_MACHINE) | grep -v -e '\[INFO\] ' -e '#> ' | cat
	-$(Q) grep -e 'INCORRECT RESULT' -e 'WRONG NUMBER OF RESULTS' $(TC_OUTPUT) | cat > $(TC_FILTERED)
	-$(Q) if [ -f $(TC_EXPECTED) ]; then diff -u $(TC_EXPECTED) $(TC_OUTPUT) | cat &> $(TC_DIFF); fi
	-$(Q) if [ ! -s $(TC_FILTERED) ] && ([ ! -f $(TC_DIFF) ] || [ ! -s $(TC_DIFF) ]); then \
	        $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$<; \
					echo "$(CC_GREEN)PASS$(CC_END)"; \
				else \
				  [ -f $(TC_FILTERED) ] && cat $(TC_FILTERED) >> $(TC_TMPFILE); \
					[ -f $(TC_DIFF) ] && cat $(TC_DIFF) >> $(TC_DIFF); \
					$(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$< --result=fail --message="Failed aserts" --diff=$(TC_TMPFILE); \
					echo "$(CC_RED)FAIL$(CC_END)"; \
					sed 's/^/  /' $(TC_TMPFILE); \
				fi;
	-$(Q) rm -f $(TC_TMPFILE)

tests-post:

clean:
