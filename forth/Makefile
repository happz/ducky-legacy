include $(TOPDIR)/Makefile.inc

.PRECIOUS: %.o

ducky-forth.asm: ducky-forth-words.asm double-cell-ints.asm ducky-forth-defs.asm $(DEFSDIR)/ducky.asm

ducky-forth.o: ducky-forth.asm
	$(call run-as,$(if $(filter yes,$(FORTH_DEBUG)),-D FORTH_DEBUG) $(if $(filter yes,$(FORTH_DEBUG_FIND)),-D FORTH_DEBUG_FIND) $(if $(filter yes,$(FORTH_WELCOME)),-D FORTH_WELCOME))

$(FORTH_KERNEL): ducky-forth.o
	$(call run-linker,--section-base=.text=0x0000 --section-base=.userspace=0x5000)

kernel: $(FORTH_KERNEL)

clean:
	$(Q) rm -f ducky-forth.o $(FORTH_KERNEL)
