import setuptools

with open("Readme.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="cm2access",
    version="0.0.5",
    author="Will Dowling",
    author_email="w.dowling@elsevier.com",
    description="Package that encapsulates access to CM2 and QPE",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://gitlab.et-scm.com",
    packages=setuptools.find_packages(),
    install_requires=[
        'certifi>=2018.11.29',
        'chardet>=3.0.4',
        'idna>=2.8',
        'requests>=2.21.0',
        'urllib3>=1.24.1',
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "All rights reserved",
        "Operating System :: OS Independent",
    ],
)
