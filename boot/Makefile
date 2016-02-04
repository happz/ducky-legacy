include $(TOPDIR)/Makefile.inc

loader.o: $(DEFSDIR)/ducky.asm $(DEFSDIR)/boot.asm $(DEFSDIR)/control.asm $(DEFSDIR)/hdt.asm loader.asm
	$(call run-as,$(if $(filter yes,$(DUCKY_BOOT_IMG)),-D DUCKY_BOOT_IMG))

lib.o: $(DEFSDIR)/ducky.asm $(DEFSDIR)/hdt.asm $(DEFSDIR)/boot.asm lib.asm

loader: loader.o lib.o
	$(call run-linker,--section-base=.text=0x00000000)

loader.img: loader
	$(call run-binary-image,--bio)

build: loader loader.img

tests-pre:

tests:

tests-post:

clean:
	$(Q) rm -f lib.o loader.o loader loader.img
