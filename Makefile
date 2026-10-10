#!/usr/bin/make -f
# Path B (repo) top-level build. Path A (single .mk) doesn't use this file.
#
#   make                      build bin/<bundle>.lv2 (DSP + TTL + face)
#   make install DESTDIR=...  install into $(DESTDIR)$(PREFIX)/lib/lv2
#   make clean
#
# Cross builds take CC/CXX/CXXFLAGS from the environment, which is what
# mod-plugin-builder and builder.mod.audio pass in.

PREFIX  ?= /usr/local
NAME    := nhe-trance-atlantic
BUNDLE  := $(NAME).lv2

all: plugin bundle

plugin:
	$(MAKE) -C plugins/$(NAME)

bundle: plugin
	cp -r bundle/$(BUNDLE)/. bin/$(BUNDLE)/

install: all
	install -d $(DESTDIR)$(PREFIX)/lib/lv2/$(BUNDLE)
	cp -r bin/$(BUNDLE)/. $(DESTDIR)$(PREFIX)/lib/lv2/$(BUNDLE)/

clean:
	$(MAKE) -C plugins/$(NAME) clean
	rm -rf bin build

.PHONY: all plugin bundle install clean
