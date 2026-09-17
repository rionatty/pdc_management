from setuptools import setup, find_packages
setup(
    name="pdc_management",
    version="0.0.1",
    description="Post Dated Cheque Management for ERPNext",
    author="Your Name",
    author_email="your@email.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=["frappe"],
)
