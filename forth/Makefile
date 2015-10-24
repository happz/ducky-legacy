include $(TOPDIR)/Makefile.inc

.PRECIOUS: %.o

ducky-forth.o: ducky-forth.asm ducky-forth-words.asm ducky-forth-defs.asm $(TOPDIR)/defs.asm
	$(call run-as,$(if $(filter yes,$(FORTH_DEBUG_FIND)),-D FORTH_DEBUG_FIND) $(if $(filter yes,$(FORTH_TEXT_WRITABLE)),-D FORTH_TEXT_WRITABLE --writable-sections,) $(if $(filter yes,$(FORTH_WELCOME)),-D FORTH_WELCOME))

$(FORTH_KERNEL): ducky-forth.o
	$(call run-linker,--section-base=.text=0x0000 --section-base=.userspace=0x5000)

kernel: $(FORTH_KERNEL)

clean:
	$(Q) rm -f ducky-forth.o $(FORTH_KERNEL)
