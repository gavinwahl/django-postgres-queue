from setuptools import setup


setup(
    name="django-pg-queue",
    version="0.5.1",
    packages=["pgq", "pgq.migrations", "dpq_scheduler", "dpq_scheduler.migrations",],
    package_data={"pgq": ["py.typed"]},
    license="BSD",
    long_description=open("README.rst").read(),
    author="SweetProcess",
    author_email="support@sweetprocess.com",
    url="https://github.com/SweetProcess/django-pg-queue",
    install_requires=["Django>=2.1",],
)
