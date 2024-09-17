import os
import sh
import shutil
import requests

from absl import logging, flags
from attrs import define, field
from overrides import overrides
from morecontext import dirchanged

from .pkgmgr import PackageManager

__all__ = ["Pacman", "Yay", "Paru", "makepkg"]

FLAGS = flags.FLAGS
flags.DEFINE_bool("rank_mirrors", False, "Rank mirrors for Arch Linux")


def makepkg():
    sh.makepkg("-si", "--needed", "--noconfirm", _fg=True)


@define
class Pacman(PackageManager):
    flags: list[str] = ["--noconfirm", "--assume-installed"]

    def __attrs_post_init__(self):
        super().__attrs_post_init__()

        assert self.ctx.sudo, "Arch Linux package manager requires sudo permissions"

    @overrides
    def setup_pkgmgr(self):
        logging.info("Setting up pacman")
        with sh.sudo(_with=True):
            # check if makepkg.conf has MAKEFLAGS
            if not sh.grep(
                '^MAKEFLAGS="-j$(nproc)"', "/etc/makepkg.conf", _ok_code=[0, 1]
            ):
                logging.info("Setting MAKEFLAGS in makepkg.conf")
                # echo 'MAKEFLAGS="-j$(nproc)"' | sudo tee -a /etc/makepkg.conf
                sh.tee("-a", "/etc/makepkg.conf", _in=sh.echo('MAKEFLAGS="-j$(nproc)"'))

            # sudo pacman -Syu --noconfirm
            sh.pacman("-Sy", _fg=True)
            sh.pacman(
                "-S",
                *self.flags,
                "base-devel",
                "git",
                "pacman-contrib",
                _fg=True,
            )

            # rank mirrors
            # sudo cp /etc/pacman.d/mirrorlist /etc/pacman.d/mirrorlist.bak
            # export COUNTRY=US
            # curl -s "https://archlinux.org/mirrorlist/?country=US&protocol=http&protocol=https&ip_version=4&ip_version=6&use_mirror_status=on" |
            #   sed -e 's/^#Server/Server/' -e '/^#/d' |
            #   rankmirrors -n 5 - |
            #   sudo tee /etc/pacman.d/mirrorlist
            if FLAGS.rank_mirrors:
                logging.info("Ranking mirrors")
                sh.cp("/etc/pacman.d/mirrorlist", "/etc/pacman.d/mirrorlist.bak")
                # read COUNTRY from the environment
                country = os.getenv("COUNTRY", "US")
                url = f"https://archlinux.org/mirrorlist/?country={country}&protocol=http&protocol=https&ip_version=4&ip_version=6&use_mirror_status=on"
                response = requests.get(url)

                # 4. Filter the content using Python (replacing sed functionality)
                mirrorlist = response.text
                filtered_mirrorlist = []
                for line in mirrorlist.splitlines():
                    if line.startswith("#Server"):
                        # Uncomment lines that start with #Server
                        line = line.lstrip("#")
                    if not line.startswith("#"):
                        filtered_mirrorlist.append(line)

                filtered_mirrorlist_text = "\n".join(filtered_mirrorlist)
                # Use subprocess to run rankmirrors and pipe the output to sudo tee
                sh.tee(
                    "/etc/pacman.d/mirrorlist",
                    _in=sh.rankmirrors("-n", "5", "-", _in=filtered_mirrorlist_text),
                )

    @overrides
    def upgrade_system(self):
        sh.sudo.pacman("-Su", "--noconfirm", _fg=True)

    @overrides
    def _install_package(self, package: list[str]):
        sh.sudo.pacman("-S", *self.flags, *package, _fg=True)


class Yay(Pacman):
    @overrides
    def setup_pkgmgr(self):
        super().setup_pkgmgr()

        if not shutil.which("yay"):
            # install yay
            with dirchanged("/tmp"):
                sh.git.clone("https://aur.archlinux.org/yay.git", "--depth=1", _fg=True)
                os.chdir("yay")
                makepkg()
                os.chdir("..")
                shutil.rmtree("yay")

    @overrides
    def _install_package(self, package: list[str]):
        sh.yay("-S", *self.flags, *package, _fg=True)


class Paru(Pacman):
    @overrides
    def setup_pkgmgr(self):
        super().setup_pkgmgr()

        if not shutil.which("paru"):
            # install paru
            with dirchanged("/tmp"):
                sh.git.clone(
                    "https://aur.archlinux.org/paru.git", "--depth=1", _fg=True
                )
                os.chdir("paru")
                makepkg()
                os.chdir("..")
                shutil.rmtree("paru")

    @overrides
    def _install_package(self, package: list[str]):
        sh.paru("-S", *self.flags, *package, _fg=True)
