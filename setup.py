#!/usr/bin/env python3
"""BEMServer service acquisition MQTT"""

from setuptools import setup, find_packages

# Get the long description from the README file
with open("README.rst", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="bemserver-service-acquisition-mqtt",
    version="0.0.1",
    description="BEMServer service: timeseries acquisition through MQTT",
    long_description=long_description,
    # url="",
    author="Nobatek/INEF4",
    author_email="dfrederique@nobatek.inef4.com",
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
)
