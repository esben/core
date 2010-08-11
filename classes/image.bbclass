IMAGE_NAME = "${P}-${DATETIME}"
IMAGE_SYMLINK_NAME = "${PN}"

IMAGE_EXT_tar = ".tar"
IMAGE_EXT_tgz = ".tar.gz"
IMAGE_EXT_zip = ".zip"

inherit files

FILES_${PN} = "/${IMAGE_NAME}*"

fakeroot do_image_build() {
    set -x
    #tar czf ${IMAGE_DEPLOY_DIR}/dump/${SDK_IMAGE_FILE}.tar.gz .
    create_image ${FILES_DIR} ${D}/${SDK_IMAGE_NAME}
    [ -s ${D}/${SDK_IMAGE_NAME} ] || return 1
}
EXPORT_FUNCTIONS do_image_build
addtask image_build after do_files_fixup before do_package_install
do_image_build[dirs] = "${IMAGE_DEPLOY_DIR} ${IMAGE_DEPLOY_DIR}/dump ${FILES_DIR}"

do_image_deploy() {
    cp -f ${D}/${IMAGE_FILE} ${IMAGE_DEPLOY_DIR}
    ln -fs ${IMAGE_FILE} ${IMAGE_DEPLOY_DIR}/${IMAGE_SYMLINK_FILE}
}
EXPORT_FUNCTIONS do_image_deploy
addtask image_deploy after do_image_build before do_build
do_image_deploy[dirs] = "${IMAGE_DEPLOY_DIR}"

image_build () {
    pwd
    case $1 in
        tar)
            tar -C $1 -cf $2.tar . || return 1
            ;;
        tar.gz)
            ;;
        tar.bz2)
            ;;
        zip)
            # zip do not support dangeling symlinks so remove them
            find -L . -type l -print0 | xargs -tr0 rm -f 
            zip -r $2 . || return 1
            ;;
    esac
}