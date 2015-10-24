include $(TOPDIR)/Makefile.inc


TESTS_IN  := $(shell find $(CURDIR) -name 'assign-*.c' | sort)
TESTS_OUT := $(TESTS_IN:%.c=%.asm)

TC_DIR := $(TC_DIR)/unit


tests-pre:
	$(Q) mkdir -p $(TC_DIR)

tests: $(TESTS_OUT)

tests-post:

clean:

%.asm: %.c
	$(eval TC_NAME     := $(notdir $(<:%.c=%)))
	$(eval TC_OUT      := $(TC_DIR)/$(TC_NAME).$(DB_PID).asm)
	$(eval TC_OUTPUT   := $(TC_DIR)/$(TC_NAME).$(DB_PID).out)
	$(eval TC_COVERAGE := $(TESTSETDIR)/coverage/.coverage.forth-unit.$(TC_NAME).$(DB_PID))
	$(eval TC_EXPECTED := $(<:%.c=%.asm.expected))
	$(eval TC_DIFF     := $(TC_DIR)/$(TC_NAME).$(DB_PID).diff)
	$(eval TC_FAIL     := $(<:%.c=%.c.fail))
	$(eval TC_TMPFILE  := $(shell mktemp))
ifeq ($(VMCOVERAGE),yes)
	$(eval VMCOVERAGE_FILE := COVERAGE_FILE="$(TC_COVERAGE)")
else
	$(eval VMCOVERAGE_FILE := )
endif
	-$(Q) echo -n "$(CC_YELLOW)[TEST]$(CC_END) Compiler $(TC_NAME) ... "
	-$(Q) $(VMCOVERAGE_FILE) \
	      $(PYTHON) $(VMCOVERAGE_RUN) $(TOPDIR)/tools/cc-ast \
				-i $< -o $(TC_OUT) -O0 -q \
				$(VMDEBUG) &> $(TC_OUTPUT); \
				if [ "$$?" = "0" ]; then \
				  if [ -f $(TC_EXPECTED) ]; then \
					  sed '/^  ;.*$$/d' $(TC_OUT) > $(TC_TMPFILE); \
						diff -u $(TC_EXPECTED) $(TC_TMPFILE) | cat &> $(TC_DIFF); \
					fi; \
					if [ ! -f $(TC_DIFF) ] || [ ! -s $(TC_DIFF) ]; then \
					  $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$<; \
						echo "$(CC_GREEN)PASS$(CC_END)"; \
					else \
					  $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$< --result=fail --message="Unexpected output" --diff=$(TC_DIFF); \
						echo "$(CC_RED)FAIL$(CC_END)"; \
					fi; \
				else \
				  if [ -f $(TC_FAIL) ]; then \
					  $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$<; \
						echo "$(CC_GREEN)PASS$(CC_END)"; \
					else \
					  $(XUNIT) --add --file=$(TC_RESULTS) --ts=$(TC_TESTSUITE) --name=$(TC_NAME) --classname=$< --result=fail --message="Unexpected exit code"; \
						echo "$(CC_RED)FAIL$(CC_END)"; \
					fi; \
				fi;
	-$(Q) rm -f $(TC_TMPFILE)

