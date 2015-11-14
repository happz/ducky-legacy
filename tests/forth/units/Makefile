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
	$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) FORTH $(TC_NAME) ... "
	$(Q) PYTHONUNBUFFERED=yes \
	     $(VMCOVERAGE_FILE) \
	     $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) \
			 $(VMPROFILE) \
			 $(BINPROFILE) -g \
			 --machine-config=$(TC_CONFIG) \
			 --set-option=machine:interrupt-routines=$(INTERRUPTS) \
			 --set-option=binary-0:file=$(FORTH_KERNEL) \
			 --set-option=device-3:streams_in=$(CURDIR)/../enable-test-mode.f \
			 --add-option=device-3:streams_in=$(TOPDIR)/forth/ducky-forth.f \
			 --add-option=device-3:streams_in=$(CURDIR)/../ans/tester.fr \
			 --add-option=device-3:streams_in=$< \
			 --add-option=device-3:streams_in=$(CURDIR)/../run-test-word.f \
			 --set-option=device-3:stream_out=$(TC_OUTPUT) \
			 $(foreach device,$(DUCKY_ENABLE_DEVICES),--enable-device=$(device)) \
			 $(foreach device,$(DUCKY_DISABLE_DEVICES),--disable-device=$(device)) \
			 $(VMDEBUG) $(VMDEBUG_OPEN_FILES) &> $(TC_MACHINE); \
			 if [[ $$? -ne 0 ]]; then \
			   $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$< --result=fail --message="Invalid exit code" --diff=$(TC_MACHINE); \
			   touch $(TESTSET_FAILED); \
				 echo "$(CC_RED)FAIL$(CC_END)"; \
			 else \
			   grep -v -e '\[INFO\] ' -e '#> ' $(TC_MACHINE) || /bin/true; \
				 grep -e 'INCORRECT RESULT' -e 'WRONG NUMBER OF RESULTS' $(TC_OUTPUT) > $(TC_FILTERED) || /bin/true; \
				 if [ -f $(TC_EXPECTED) ]; then diff -u $(TC_EXPECTED) $(TC_OUTPUT) &> $(TC_DIFF) || /bin/true; fi; \
				 if [ ! -s $(TC_FILTERED) ] && ([ ! -f $(TC_DIFF) ] || [ ! -s $(TC_DIFF) ]); then \
				   $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$<; \
					 echo "$(CC_GREEN)PASS$(CC_END)"; \
				 else \
				   [ -f $(TC_FILTERED) ] && cat $(TC_FILTERED) >> $(TC_TMPFILE); \
					 [ -f $(TC_DIFF) ] && cat $(TC_DIFF) >> $(TC_TMPFILE); \
					 $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$< --result=fail --message="Failed aserts" --diff=$(TC_TMPFILE); \
					 sed 's/^/  /' $(TC_TMPFILE); \
					 touch $(TESTSET_FAILED); \
					 echo "$(CC_RED)FAIL$(CC_END)"; \
				 fi; \
			 fi; \
			 exit 0;
	-$(Q) rm -f $(TC_TMPFILE)

tests-post:

clean:
