from setuptools import setup, find_packages

setup(
    name="registrator",
    version="1.0.0",
    packages=find_packages(),
    install_requires=["click"],
    entry_points={
        "console_scripts": [
            "registrator=registrator_romania.__main__:main",
        ],
    },
)
