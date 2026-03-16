from setuptools import setup, find_packages

setup(
    name="daily-intel",
    version="0.1.0",
    description="AI-powered industry intelligence monitoring system",
    author="Andrew Shwetzer",
    url="https://github.com/andrew-shwetzer/daily-intel",
    packages=find_packages(),
    include_package_data=True,
    package_data={"daily_intel": ["templates/*.html", "templates/*.json"]},
    install_requires=[
        "anthropic>=0.40.0",
        "supabase>=2.0.0",
        "feedparser>=6.0.0",
        "pyyaml>=6.0",
        "jinja2>=3.1.0",
        "click>=8.1.0",
        "requests>=2.31.0",
    ],
    entry_points={
        "console_scripts": [
            "daily-intel=daily_intel.cli:cli",
        ],
    },
    python_requires=">=3.10",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
)
