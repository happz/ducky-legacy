include $(TOPDIR)/Makefile.inc


# See tests/forth/ans/runtest.fth for full list
FORTH_ANS_TESTS := core.fr memorytest.fth # coreplustest.fth coreexttest.fth memorytest.fth toolstest.fth stringtest.fth

TC_DIR      := $(TC_DIR)/ans
TC_OUTPUT   := $(TC_DIR)/forth-ans.$(DB_PID).out
TC_MACHINE  := $(TC_DIR)/forth-ans.$(DB_PID).machine
TC_FILTERED := $(TC_DIR)/forth-ans.$(DB_PID).filtered

ifeq ($(VMCOVERAGE),yes)
  COVERAGE_FILE := $(TESTSETDIR)/coverage/.coverage.forth-ans.$(DB_PID)
else
  COVERAGE_FILE :=
endif

export COVERAGE_FILE


tests-pre:
	$(Q) mkdir -p $(TC_DIR)

tests: $(TOPDIR)/interrupts $(FORTH_KERNEL)
	-$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) FORTH ANS testsuite ... "
	-$(Q) $(PYTHON) $(VMCOVERAGE_RUN) $(DVM) \
				$(VMPROFILE) \
				$(BINPROFILE) -g \
				--machine-config=$(TC_CONFIG) \
				--set-option=machine:interrupt-routines=$(INTERRUPTS) \
				--set-option=binary-0:file=$(FORTH_KERNEL) \
				--set-device-option=device-3:streams_in=$(CURDIR)/../enable-test-mode.f \
				--add-device-option=device-3:streams_in=$(TOPDIR)/forth/ducky-forth.f \
				--add-device-option=device-3:streams_in=$(CURDIR)/tester.fr \
				$(foreach testfile,$(FORTH_ANS_TESTS),--add-device-option=device-3:streams_in=$(CURDIR)/$(testfile)) \
				--set-device-option=device-3:stream_out=$(TC_OUTPUT) \
				$(foreach device,$(DUCKY_ENABLE_DEVICES),--enable-device=$(device)) \
				$(foreach device,$(DUCKY_DISABLE_DEVICES),--disable-device=$(device)) \
				$(VMDEBUG) $(VMDEBUG_OPEN_FILES) 2>&1 | stdbuf -oL -eL tee $(TC_MACHINE) | grep -v -e '\[INFO\] ' -e '#> '
	-$(Q) grep -e 'INCORRECT RESULT' -e 'WRONG NUMBER OF RESULTS' $(TC_OUTPUT) | cat > $(TC_FILTERED);
	-$(Q) if [ ! -s $(TC_FILTERED) ]; then \
	        $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name="ANS test suite"; \
					echo "$(CC_GREEN)PASS$(CC_END)"; \
				else \
				  $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name="ANS test suite" --result=fail --message="Failed aserts" --diff=$(TC_FILTERED); \
				  echo "$(CC_RED)FAIL$(CC_END)"; \
				  sed -e 's/^/  /' $(TC_FILTERED); \
				fi

tests-post:

clean:
