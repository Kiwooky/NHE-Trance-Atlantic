######################################
#
# nhe-trance-atlantic  (path B package file)
#
# Builds the plugin from a GitHub repo at a given commit. Upload this file at
# https://builder.mod.audio/buildroot for an install link, or put it in
# mod-plugin-builder at plugins/package/nhe-trance-atlantic/nhe-trance-atlantic.mk.
#
# 1. DPF is a git submodule at dpf/; the hook below fetches it.
# 2. Push, then set NHE_TRANCE_ATLANTIC_VERSION to the FULL 40-character commit hash
#    (GitHub: Commits -> copy button, or `git rev-parse HEAD`).
# The filename must match the variable prefix: nhe-trance-atlantic.mk -> NHE_TRANCE_ATLANTIC_.
#
######################################

NHE_TRANCE_ATLANTIC_VERSION = 51389bcfc7f96466e7efbb55c1d7c4de73957f97
NHE_TRANCE_ATLANTIC_SITE = https://github.com/Kiwooky/NHE-Trance-Atlantic.git
NHE_TRANCE_ATLANTIC_SITE_METHOD = git
NHE_TRANCE_ATLANTIC_GIT_SUBMODULES = y
NHE_TRANCE_ATLANTIC_BUNDLES = nhe-trance-atlantic.lv2

# fetch git submodules (DPF), as MOD's own packages do (mod-plugin-builder)
NHE_TRANCE_ATLANTIC_PRE_DOWNLOAD_HOOKS += MOD_PLUGIN_BUILDER_DOWNLOAD_WITH_SUBMODULES

NHE_TRANCE_ATLANTIC_TARGET_MAKE = $(TARGET_MAKE_ENV) $(TARGET_CONFIGURE_OPTS) $(MAKE) NOOPT=true -C $(@D)

define NHE_TRANCE_ATLANTIC_BUILD_CMDS
	$(NHE_TRANCE_ATLANTIC_TARGET_MAKE)
endef

define NHE_TRANCE_ATLANTIC_INSTALL_TARGET_CMDS
	$(NHE_TRANCE_ATLANTIC_TARGET_MAKE) install DESTDIR=$(TARGET_DIR) PREFIX=/usr
endef

$(eval $(generic-package))
