from pathlib import Path

from setuptools import find_packages, setup

setup(
    name="mzn-bench",
    use_scm_version=True,
    setup_requires=["wheel", "setuptools_scm"],
    python_requires=">=3.6",
    author="Jip J. Dekker",
    author_email="jip.dekker@monash.edu",
    description="SLURM scheduling functionality and a collection of scripts to process the resulting data.",
    long_description=Path("README.md").read_text(encoding="UTF-8"),
    long_description_content_type="text/markdown",
    url="https://www.minizinc.org/",
    project_urls={
        "Source": "https://github.com/MiniZinc/mzn-bench",
    },
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "minizinc",
        "ruamel.yaml",
        "click>=7,<8",
    ],
    extras_require={
        "scripts": [
            "tabulate",
            "pytest>=6,<7",
        ],
        "plotting": [
            "pandas>=1.1,<2",
            "bokeh>=2.2.3",
        ],
    },
    entry_points="""
        [console_scripts]
        mzn-bench = mzn_bench_scripts.cli:main
    """,
)
