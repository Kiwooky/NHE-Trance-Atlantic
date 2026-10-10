# Builds a path-B package .mk (the file for builder.mod.audio and mod-plugin-builder)
# locally, against a checkout of your repo instead of the GitHub download.
#
#   make -f tools/package_harness.mk PACKAGE=mod-plugin-builder/<name>/<name>.mk \
#        SRC=<copy of the repo> TGT=<install root> [CROSS=arm32|arm64]
#
# SRC   a scratch copy of the repo with its submodules, standing in for $(@D):
#       git clone --recursive <your repo> <SRC>  (what the builder's submodule hook does)
# TGT   where `make install DESTDIR=...` lands; the bundle ends up in
#       $(TGT)/usr/lib/lv2/<name>.lv2
#
# TARGET_DIR is set inside this file on purpose. Passed on the command line it
# would be inherited by every sub-make and override DPF's own TARGET_DIR, so
# the plugin binary lands somewhere else and the bundle step fails. (Buildroot
# doesn't pass it that way, so the real builder is unaffected.)
PKG_NAME := $(basename $(notdir $(PACKAGE)))
PKG := $(shell echo $(PKG_NAME) | tr 'a-z-' 'A-Z_')
generic-package :=
github = $(SRC)
TARGET_DIR := $(TGT)
TARGET_MAKE_ENV :=
ifeq ($(CROSS),arm32)
TARGET_CONFIGURE_OPTS := CC=arm-linux-gnueabihf-gcc CXX=arm-linux-gnueabihf-g++ AR=arm-linux-gnueabihf-ar CXXFLAGS="-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard"
endif
ifeq ($(CROSS),arm64)
TARGET_CONFIGURE_OPTS := CC=aarch64-linux-gnu-gcc CXX=aarch64-linux-gnu-g++ AR=aarch64-linux-gnu-ar
endif
include $(PACKAGE)
all: $(SRC)/.built
$(SRC)/.built:
	$($(PKG)_BUILD_CMDS)
	$($(PKG)_INSTALL_TARGET_CMDS)
