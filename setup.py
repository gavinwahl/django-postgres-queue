from setuptools import setup


setup(
    name='django-postgres-queue',
    version='1.0.1.dev0',
    packages=[
        'dpq',
        'dpq.migrations',
        'dpq_scheduler',
        'dpq_scheduler.migrations',
    ],
    license='BSD',
    long_description=open('README.rst').read(),
    author="Gavin Wahl",
    author_email="gavinwahl@gmail.com",
    url="https://github.com/gavinwahl/django-postgres-queue",
    install_requires=[
        'Django>=1.11',
    ]
)
