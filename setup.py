import itertools
from pathlib import Path

import setuptools
from distutils.command.build import build
from setuptools.command.develop import develop
from setuptools.command.easy_install import easy_install
from setuptools.command.install_lib import install_lib


# Hopefully all the following will not be needed after PEP 648
# Reference: https://github.com/pytest-dev/pytest-cov/blob/daf54e79fcb8f549699d28e691302a9251f7e54b/setup.py#L145-L151
def _copy_pth(obj, install_dir):
    pth_src = Path(__file__).parent / "grill.pth"
    pth_tgt = str(Path(install_dir) / pth_src.name)
    obj.copy_file(str(pth_src), pth_tgt)
    return [pth_tgt]


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
        self.outputs = _copy_pth(self, self.install_dir)

    def get_outputs(self):
        return itertools.chain(super().get_outputs(), self.outputs)


setuptools.setup(
    cmdclass={
        "build": BuildPTH,
        "develop": DevelopPTH,
        "easy_insall": EasyInstallPTH,
        "install_lib": InstallLibPTH,
    },
)
