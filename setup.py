from __future__ import annotations

from pathlib import Path

from setuptools import find_packages, setup


def _read_requirements() -> list[str]:
	# Optional: keep supporting requirements.txt for local/dev installs.
	# The file is not required for packaging/builds.
	req = Path(__file__).with_name("requirements.txt")
	if not req.exists():
		return []
	content = req.read_text(encoding="utf-8").strip()
	return [line for line in content.splitlines() if line.strip()] if content else []


install_requires = _read_requirements()

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
