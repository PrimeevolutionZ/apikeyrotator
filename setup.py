from setuptools import setup, find_packages

setup(
    name="apikeyrotator",
    version="0.0.1",
    author="Your Name",
    description="Automatically rotate API keys to bypass free-tier limits",
    packages=find_packages(),
    install_requires=[
        "requests",
        "python-dotenv",
    ],
    python_requires=">=3.7",
)