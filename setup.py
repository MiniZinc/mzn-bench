from pathlib import Path

from setuptools import find_packages, setup

setup(
    name="minizinc_slurm",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    python_requires=">=3.6",
    author="Jip J. Dekker",
    author_email="jip.dekker@monash.edu",
    description="SLURM scheduling functionality and a collection of scripts to process the resulting data.",
    long_description=Path("README.md").read_text(encoding="UTF-8"),
    long_description_content_type="text/markdown",
    url="https://www.minizinc.org/",
    project_urls={"Source": "https://github.com/Dekker1/minizinc-slurm",},
    packages=find_packages(where="src"),
    py_modules=["minizinc_slurm"],
    package_dir={"": "src"},
    install_requires=["minizinc", "ruamel.yaml",],
    extras_require={"scripts": ["tabulate"],},
    entry_points="""
        [console_scripts]
        collect_instances = minizinc_slurm_scripts.collect_instances:main
        collect_statistics = minizinc_slurm_scripts.collect_statistics:main
        report_status = minizinc_slurm_scripts.report_status:main [scripts]
    """,
)
