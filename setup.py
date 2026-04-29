from setuptools import setup, find_packages

with open('requirements.txt') as f:
    install_requires = f.read().strip().splitlines() if f.read() else []

setup(
    name='thanatos_intel',
    version='0.0.1',
    description='Intelligence Investigation Platform MVP',
    author='OneKeyCo',
    author_email='info@onekeyco.com',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
