# Runs a cookbook recipe's Buildroot hooks locally, without Buildroot.
#
#   make -f harness.mk RECIPE=simple-echo.mk PREFIX=SIMPLE_ECHO SRC=$PWD/dpf-copy OUT=$PWD/out [CROSS=arm32|arm64]
#
# SRC  : a fresh copy of DPF checked out at the recipe's _VERSION SHA
#        (git clone https://github.com/DISTRHO/DPF.git && git checkout <sha> && git submodule update --init)
# OUT  : where the .lv2 bundle is installed (stands in for $($(PKG)_PKGDIR))
# CROSS: arm32 = MOD Duo (Cortex-A7, armhf; apt g++-arm-linux-gnueabihf)
#        arm64 = Duo X / Dwarf (apt g++-aarch64-linux-gnu)
#
# Trick: the recipe uses $(@D) for the source dir. Making the target live
# inside SRC ($(SRC)/.built) makes $(@D) resolve to SRC, as in Buildroot.
PKG := $(PREFIX)
generic-package :=
$(PREFIX)_PKGDIR := $(OUT)
ifeq ($(CROSS),arm32)
TARGET_CONFIGURE_OPTS := CC=arm-linux-gnueabihf-gcc CXX=arm-linux-gnueabihf-g++ AR=arm-linux-gnueabihf-ar CXXFLAGS="-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard"
endif
ifeq ($(CROSS),arm64)
TARGET_CONFIGURE_OPTS := CC=aarch64-linux-gnu-gcc CXX=aarch64-linux-gnu-g++ AR=aarch64-linux-gnu-ar
endif
include $(RECIPE)
all: $(SRC)/.built
$(SRC)/.built:
	$($(PREFIX)_CONFIGURE_CMDS)
	$($(PREFIX)_BUILD_CMDS)
	$($(PREFIX)_INSTALL_TARGET_CMDS)
