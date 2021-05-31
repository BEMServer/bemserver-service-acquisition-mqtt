#!/usr/bin/env python3
"""BEMServer service acquisition MQTT"""

from setuptools import setup, find_packages

import bemserver_service_acquisition_mqtt as svc


# Get the long description from the README file
with open("README.rst", encoding="utf-8") as f:
    long_description = f.read()


setup(
    name=svc.__binname__,
    version=svc.__version__,
    description=svc.__description__,
    long_description=long_description,
    # url="",
    author=svc.__author__,
    author_email=svc.__email__,
    # license="",
    # keywords=[
    # ],
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    python_requires=">=3.7",
    install_requires=[
        "click>=8.0.0",
        "psycopg2>=2.8.0",
        "sqlalchemy>=1.4.0",
        "paho-mqtt>=1.5.1",
        (
            "bemserver-core "
            "@ git+https://git@github.com/BEMServer/bemserver-core.git@bd573b2"
            "#egg=bemserver-core"
        ),
    ],
    packages=find_packages(exclude=["tests*"]),
    entry_points={
        "console_scripts": [
            f"{svc.__binname__} = {svc.__appname__}.__main__:main",
        ],
    },
)
