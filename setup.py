import os
import itertools

import setuptools
from distutils.command.build import build
from setuptools.command.develop import develop
from setuptools.command.easy_install import easy_install
from setuptools.command.install_lib import install_lib


# Reference:
# https://github.com/pytest-dev/pytest-cov/blob/daf54e79fcb8f549699d28e691302a9251f7e54b/setup.py#L145-L151
def _copy_pth(obj, install_dir):
    path = os.path.join(os.path.dirname(__file__), "grill.pth")
    dest = os.path.join(install_dir, os.path.basename(path))
    obj.copy_file(path, dest)
    return dest


class BuildPTH(build):
    def run(self):
        super().run()
        _copy_pth(self, self.build_lib)


class DevelopPTH(develop):
    def run(self):
        super().run()
        _copy_pth(self, self.install_dir)


class EasyInstallPTH(easy_install):
    def run(self):
        super().run()
        _copy_pth(self, self.install_dir)


class InstallLibPTH(install_lib):
    def run(self):
        super().run()
        dest = _copy_pth(self, self.install_dir)
        self.outputs = [dest]

    def get_outputs(self):
        return itertools.chain(super().get_outputs(), self.outputs)


setuptools.setup(
    cmdclass={
        # Reference:
        # https://github.com/pytest-dev/pytest-cov/blob/daf54e79fcb8f549699d28e691302a9251f7e54b/setup.py#L145-L151
        "build": BuildPTH,
        "develop": DevelopPTH,
        "easy_insall": EasyInstallPTH,
        "install_lib": InstallLibPTH,
    },
)
