import os
import sys
from shutil import rmtree

from setuptools import setup, Command

VERSION = "0.8.2"

HERE = os.path.abspath(os.path.dirname(__file__))


class UploadCommand(Command):
    """Support setup.py upload."""

    description = "Build and publish the package."
    user_options = []

    @staticmethod
    def status(s):
        """Prints things in bold."""
        print("\033[1m{0}\033[0m".format(s))

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        try:
            self.status("Removing previous builds…")
            rmtree(os.path.join(HERE, "dist"))
        except OSError:
            pass

        self.status("Building Source and Wheel (universal) distribution…")
        os.system("{0} setup.py sdist bdist_wheel --universal".format(sys.executable))

        self.status("Uploading the package to PyPi via Twine…")
        os.system("twine upload dist/*")

        self.status("Pushing git tags…")
        os.system("git tag v{0}".format(VERSION))
        os.system("git push --tags")

        sys.exit()


setup(
    name="django-pg-queue",
    version=VERSION,
    packages=[
        "pgq",
        "pgq.migrations",
    ],
    package_data={"pgq": ["py.typed"]},
    license="BSD",
    long_description=open("README.rst").read(),
    author="SweetProcess",
    author_email="support@sweetprocess.com",
    url="https://github.com/SweetProcess/django-pg-queue",
    install_requires=[
        "Django>=2.1",
    ],
    # $ setup.py publish support.
    cmdclass={
        "upload": UploadCommand,
    },
)
