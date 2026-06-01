from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="thanatos_intel",
    version="0.1.0",
    description="Crypto intelligence & compliance tools",
    author="Thanatos",
    author_email="ops@thanatos.onekeyco.com",
    packages=find_packages(),
    install_requires=install_requires,
)
