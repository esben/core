RECIPE_TYPE			 = "canadian-cross"
#
RECIPE_ARCH			 = "canadian/${SDK_ARCH}--${MACHINE_ARCH}"
RECIPE_ARCH_MACHINE		 = "canadian/${SDK_ARCH}--${MACHINE}"

# Set host=sdk for architecture triplet build/sdk/target
HOST_ARCH		= "${SDK_ARCH}"
HOST_CROSS		= "${SDK_CROSS}"
HOST_CROSS_CFLAGS	= "${SDK_CROSS_CFLAGS}"
HOST_EXEEXT		= "${SDK_EXEEXT}"
HOST_PREFIX		= "${SDK_PREFIX}"
HOST_CPPFLAGS		= "${SDK_CPPFLAGS}"
HOST_CFLAGS		= "${SDK_CFLAGS}"
HOST_CXXFLAGS		= "${SDK_CXXFLAGS}"
HOST_LDFLAGS		= "${SDK_LDFLAGS}"

# Arch tuple arguments for configure (oe_runconf in autotools.bbclass)
OECONF_ARCHTUPLE = "--build=${BUILD_CROSS} --host=${HOST_CROSS} --target=${TARGET_CROSS}"
