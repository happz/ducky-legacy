include $(TOPDIR)/Makefile.inc

SUBDIRS := units ans

TC_DIR       := $(TESTSETDIR)/forth
TC_CONFIG    := $(CURDIR)/test-machine.conf
TC_RESULTS   := $(TESTSETDIR)/results/forth.xml
TC_TESTSUITE := forth-$(TESTSET)

export TC_DIR
export TC_CONFIG
export TC_RESULTS
export TC_TESTSUITE

tests-pre:
	$(Q) $(XUNIT) --init --file=$(TC_RESULTS) --testsuite=$(TC_TESTSUITE)
	$(Q) mkdir -p $(TC_DIR)
	$(Q) for dir in $(SUBDIRS); do \
	       $(MAKE) -C $$dir tests-pre; \
			 done

tests:
	$(Q) for dir in $(SUBDIRS); do \
	       $(MAKE) -C $$dir tests; \
			 done

tests-post:
	$(Q) for dir in $(SUBDIRS); do \
	       $(MAKE) -C $$dir tests-post; \
			 done

clean:
	$(Q) for dir in $(SUBDIRS); do \
	       $(MAKE) -C $$dir clean; \
	     done
