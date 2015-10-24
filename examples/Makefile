include $(TOPDIR)/Makefile.inc

SUBDIRS := clock hello-world

XUNIT := $(CURDIR)/xunit-record
export XUNIT


tests-pre:
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
