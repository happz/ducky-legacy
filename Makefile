SOURCES  := $(shell find $(CURDIR) -name '*.asm')
BINARIES := $(SOURCES:%.asm=%.bin)

FORTH_KERNEL := forth/ducky-forth.bin

all: $(BINARIES)

.PHONY: tests forth-tests forth-tests-debug docs cloc

forth/ducky-forth.bin: forth/ducky-forth.asm forth/ducky-forth-words.asm

all: $(BINARIES)

tests: tests/instructions/interrupts-basic.bin
	PYTHONPATH=$(CURDIR)/src nosetests -v --all-modules --with-coverage --cover-erase --cover-html --cover-html-dir=$(CURDIR)/coverage --with-xunit --xunit-file=$(CURDIR)/tests/nosetests.xml
ifdef CIRCLE_TEST_REPORTS
	cp $(CURDIR)/tests/nosetests.xml $(CIRCLE_TEST_REPORTS)/
endif
ifdef CIRCLE_ARTIFACTS
	cp -r $(CURDIR)/coverage $(CIRCLE_ARTIFACTS)/
endif

forth-tests: interrupts.bin $(FORTH_KERNEL)
	PYTHONUNBUFFERED=yes PYTHONPATH=$(CURDIR)/src tools/vm -i interrupts.bin --binary $(FORTH_KERNEL),entry=main --machine-in=forth/ducky-forth.f --machine-in=tests/forth/ans/tester.fr --machine-in=tests/forth/ans/core.fr --machine-out=m.out -g

forth-tests-debug: interrupts.bin $(FORTH_KERNEL)
	PYTHONUNBUFFERED=yes PYTHONPATH=$(CURDIR)/src tools/vm -i interrupts.bin --binary $(FORTH_KERNEL),entry=main --machine-in=forth/ducky-forth.f --machine-in=tests/forth/ans/tester.fr --machine-in=tests/forth/ans/core.fr --machine-out=m.out -g -d &> lse

cloc:
	cloc --skip-uniqueness src/ forth/ examples/

docs:
	sphinx-apidoc -o docs/ src/
	make -C docs clean
	make -C docs html

%.bin: %.asm
	PYTHONPATH=$(CURDIR)/src tools/as -i $< -o $@ -f

clean:
	rm -f $(BINARIES)

