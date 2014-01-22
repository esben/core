# -*- mode:python; -*-
SUMMARY = "A GNU collection of binary utilities"
DESCRIPTION = "The GNU Binutils are a collection of binary tools. \
The main ones are ld (GNU Linker), and as (GNU Assembler). This \
package also includes addition tools such as addr2line (Converts \
addresses into filenames and line numbers), ar (utility for creating, \
modifying and extracting archives), nm (list symbols in object \
files), objcopy (copy and translate object files), objdump (Display \
object information), and other tools and related libraries."
HOMEPAGE = "http://www.gnu.org/software/binutils/"
BUGTRACKER = "http://sourceware.org/bugzilla/"

RECIPE_TYPES = "cross sdk-cross machine"

inherit autotools make-vpath gettext

require conf/fetch/gnu.conf
SRC_URI = "${GNU_MIRROR}/binutils/binutils-${PV}.tar.bz2 "

DEPENDS = "native:flex native:bison"

C_DEPENDS_TARGET = ""

CHRPATH_DEPENDS = "host-cross:chrpath"
CHRPATH_TYPES = "HOST"

LIBTOOL_DEPENDS = "host-cross:libtool"

EXTRA_OECONF = "--enable-install-libbfd --enable-install-libiberty --enable-shared --enable-static --disable-multilib --with-float=${TARGET_ARCH}"
EXTRA_OECONF:>HOST_CPU_arm = " --disable-werror"

AR = "ar"
AS = "as"

DEPENDS += "native:mpc native:mpfr native:gmp native:isl native:cloog"

EXTRA_OECONF_SYSROOT    = " --with-sysroot=${HOST_SYSROOT}"
EXTRA_OECONF:>native    = " ${EXTRA_OECONF_SYSROOT}"
EXTRA_OECONF:>cross     = " ${EXTRA_OECONF_SYSROOT}"
EXTRA_OECONF:>sdk-cross = " ${EXTRA_OECONF_SYSROOT}"

do_configure[postfuncs] += "do_configure_check"
do_configure_check() {
	make configure-host
}

inherit auto-package-libs
AUTO_PACKAGE_LIBS = "opcodes bfd"
BINUTILS_VERSION ?= "${PV}"

AUTO_PACKAGE_LIBS_LIBDIR_PREFIX = "/${HOST_ARCH}/${TARGET_ARCH}"
AUTO_PACKAGE_LIBS_LIBDIR_PREFIX:machine = ""
AUTO_PACKAGE_LIBS_LIBDIR = "${AUTO_PACKAGE_LIBS_LIBDIR_PREFIX}${libdir}:lib::-${BINUTILS_VERSION}.so"

PACKAGES += "${PN}-libiberty ${PN}-libiberty-dev"
FILES_${PN}-libiberty = "${libdir}/libiberty.a"
FILES_${PN}-libiberty-dev = "${includedir}/libiberty.h"

FILES_${PN}-libopcodes-dev = "${AUTO_PACKAGE_LIBS_LIBDIR_PREFIX}${includedir}/dis-asm.h"
FILES_${PN}-libbfd-dev = "${AUTO_PACKAGE_LIBS_LIBDIR_PREFIX}${includedir}/"

FILES_${PN}-dbg += "${AUTO_PACKAGE_LIBS_LIBDIR_PREFIX}${libdir}/.debug"

inherit auto-package-utils
AUTO_PACKAGE_UTILS = "\
    addr2line as c++filt gprof ld nm objcopy objdump ranlib readelf elfedit \
    size strip ar strings embedspu"

do_install[postfuncs] += "do_install_libiberty"
do_install_libiberty() {
	install -d ${D}${includedir}
	cp -v ${S}/include/libiberty.h ${D}${includedir}/
}

do_install[postfuncs] += "do_install_hardlinkfixup"
def do_install_hardlinkfixup(d):
    bindir = d.get('D') + d.get('bindir')
    target_arch_bindir = os.path.join(
        d.get('D') + d.get('prefix'), d.get('TARGET_ARCH'), 'bin')
    bindir_relpath = os.path.relpath(bindir, target_arch_bindir)
    os.chdir(target_arch_bindir)
    for util in os.listdir(os.getcwd()):
        if util.startswith('.'):
            continue
        os.unlink(util)
        os.symlink(os.path.join(bindir_relpath,
                                d.get('TARGET_PREFIX') +util),
                   util)

FILES_${PN}-dbg += "${prefix}/${TARGET_ARCH}/bin/.debug"

FILES_${PN}-ar += "${prefix}/${TARGET_ARCH}/bin/ar"
FILES_${PN}-as += "${prefix}/${TARGET_ARCH}/bin/as"
FILES_${PN}-ld += "${bindir}/${AUTO_PACKAGE_UTILS_PREFIX}ld.bfd ${prefix}/${TARGET_ARCH}/bin/ld ${prefix}/${TARGET_ARCH}/bin/ld.bfd"
FILES_${PN}-nm += "${prefix}/${TARGET_ARCH}/bin/nm"
FILES_${PN}-objcopy += "${prefix}/${TARGET_ARCH}/bin/objcopy"
FILES_${PN}-objdump += "${prefix}/${TARGET_ARCH}/bin/objdump"
FILES_${PN}-ranlib += "${prefix}/${TARGET_ARCH}/bin/ranlib"
FILES_${PN}-strip += "${prefix}/${TARGET_ARCH}/bin/strip"

PACKAGES += "${PN}-ldscripts"
FILES_${PN}-ldscripts = "${prefix}/${TARGET_ARCH}/lib/ldscripts"

RDEPENDS_${PN}-addr2line = "binutils-libbfd"
RDEPENDS_${PN}-as = "libbfd libopcodes"
RDEPENDS_${PN}-c++filt = "libbfd"
RDEPENDS_${PN}-gprof = "libbfd"
RDEPENDS_${PN}-ld = "libbfd"
RDEPENDS_${PN}-nm = "libbfd"
RDEPENDS_${PN}-objcopy = "libbfd"
RDEPENDS_${PN}-objdump = "libbfd libopcodes"
RDEPENDS_${PN}-libopcodes = "binutils-libbfd"
RDEPENDS_${PN}-ranlib = "libbfd"
RDEPENDS_${PN}-readelf = "libbfd"
RDEPENDS_${PN}-elfedit = "libbfd"
RDEPENDS_${PN}-size = "libbfd"
RDEPENDS_${PN}-strip = "libbfd"
RDEPENDS_${PN}-ar = "libbfd"
RDEPENDS_${PN}-strings = "libbfd"

# The binutils package is used to pull in all provided util features
RDEPENDS_${PN} = "${AUTO_PACKAGE_UTILS_PROVIDES}"

# We need to set a different priority than the highest gcc recipe priority, so
# that we don't get into multiple provider problems with libbfd.
DEFAULT_PREFERENCE = "2"

DEPENDS_${PN} = "${AUTO_PACKAGE_UTILS_PACKAGES} ${LIBS_AUTO_PACKAGES}"
RDEPENDS_${PN} = "${AUTO_PACKAGE_UTILS_PACKAGES} ${LIBS_AUTO_RPACKAGES}"