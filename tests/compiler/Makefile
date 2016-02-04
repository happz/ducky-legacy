include $(TOPDIR)/Makefile.inc


SUBDIRS := units examples
SUBDIRS := examples

TC_DIR       := $(TESTSETDIR)/compiler
TC_RESULTS   := $(TESTSETDIR)/results/compiler.xml
TC_TESTSUITE := compiler-$(TESTSET)

export TC_DIR
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
