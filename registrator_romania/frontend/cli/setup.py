from setuptools import setup, find_packages

setup(
    name="registrator",
    version="0.0.1",
    packages=find_packages(),
    install_requires=["click"],
    entry_points={
        "console_scripts": [
            "registrator=registrator_romania.frontend.cli.__main__:main",
        ],
    },
)
