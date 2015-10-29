include $(TOPDIR)/Makefile.inc

SUBDIRS := simple-loop

TC_DIR := $(TESTSETDIR)/benchmark
export TC_DIR

tests-pre:
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
