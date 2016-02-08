include $(TOPDIR)/Makefile.inc

.PRECIOUS: %.o

ifndef BUILD_STAMP
  BUILD_STAMP := $(shell git log --date=iso --pretty=format:"%H %cd" -n 1 | cut -d' ' -f1,2,3 | tr -d '-' | tr -d ':' | tr ' ' '-')
endif


ducky-forth.asm: ducky-forth-words.asm double-cell-ints.asm ducky-forth-defs.asm $(DEFSDIR)/ducky.asm

ducky-forth.o: ducky-forth.asm
	$(call run-as,-D FORTH_BUILD_STAMP="$(BUILD_STAMP)" $(if $(filter yes,$(FORTH_DEBUG)),-D FORTH_DEBUG) $(if $(filter yes,$(FORTH_DEBUG_FIND)),-D FORTH_DEBUG_FIND) $(if $(filter yes,$(FORTH_WELCOME)),-D FORTH_WELCOME))

$(FORTH_KERNEL): ducky-forth.o
	$(call run-linker,--section-base=.text=0x0000 --section-base=.userspace=0x5000)

kernel: $(FORTH_KERNEL)

run-kernel: $(FORTH_KERNEL)
	$(Q) echo -n "$(CC_YELLOW)[RUN]$(CC_END) FORTH ... "
	$(Q) $(PYTHON) $(DVM) \
	     $(VMPROFILE) $(BINPROFILE) $(VMDEBUG) \
			 --machine-config=$(CURDIR)/forth.conf \
			 --set-option=bootloader:file=$(FORTH_KERNEL) \
			 --set-option=device-3:streams_in=$(CURDIR)/ducky-forth.f \
			 --set-option=device-3:driver=ducky.devices.terminal.StandalonePTYTerminal \
			 $(foreach device,$(DUCKY_ENABLE_DEVICES),--enable-device=$(device)) \
			 $(foreach device,$(DUCKY_DISABLE_DEVICES),--disable-device=$(device))

clean:
	$(Q) rm -f ducky-forth.o $(FORTH_KERNEL)
