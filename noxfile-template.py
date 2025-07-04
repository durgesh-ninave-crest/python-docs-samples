# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
from __future__ import print_function

from collections.abc import Callable
import glob
import os
from pathlib import Path
import sys

import nox


# WARNING - WARNING - WARNING - WARNING - WARNING
# WARNING - WARNING - WARNING - WARNING - WARNING
#       BE CAREFUL WHEN EDITING THIS FILE!
# WARNING - WARNING - WARNING - WARNING - WARNING
# WARNING - WARNING - WARNING - WARNING - WARNING

# Copy `noxfile_config.py` to your directory and modify it instead.


# `TEST_CONFIG` dict is a configuration hook that allows users to
# modify the test configurations. The values here should be in sync
# with `noxfile_config.py`. Users will copy `noxfile_config.py` into
# their directory and modify it.

TEST_CONFIG = {
    # You can opt out from the test for specific Python versions.
    "ignored_versions": ["2.7", "3.7", "3.8", "3.10", "3.11", "3.12"],
    # Old samples are opted out of enforcing Python type hints
    # All new samples should feature them
    "enforce_type_hints": False,
    # An envvar key for determining the project id to use. Change it
    # to 'BUILD_SPECIFIC_GCLOUD_PROJECT' if you want to opt in using a
    # build specific Cloud project. You can also use your own string
    # to use your own Cloud project.
    "gcloud_project_env": "GOOGLE_CLOUD_PROJECT",
    # 'gcloud_project_env': 'BUILD_SPECIFIC_GCLOUD_PROJECT',
    # If you need to use a specific version of pip,
    # change pip_version_override to the string representation
    # of the version number, for example, "20.2.4"
    "pip_version_override": None,
    # A dictionary you want to inject into your test. Don't put any
    # secrets here. These values will override predefined values.
    "envs": {},
}


try:
    # Ensure we can import noxfile_config in the project's directory.
    sys.path.append(".")
    from noxfile_config import TEST_CONFIG_OVERRIDE
except ImportError as e:
    print("No user noxfile_config found: detail: {}".format(e))
    TEST_CONFIG_OVERRIDE = {}

# Update the TEST_CONFIG with the user supplied values.
TEST_CONFIG.update(TEST_CONFIG_OVERRIDE)


def get_pytest_env_vars() -> dict[str, str]:
    """Returns a dict for pytest invocation."""
    ret = {}

    # Override the GCLOUD_PROJECT and the alias.
    env_key = TEST_CONFIG["gcloud_project_env"]
    # This should error out if not set.
    ret["GOOGLE_CLOUD_PROJECT"] = os.environ[env_key]
    ret["GCLOUD_PROJECT"] = os.environ[env_key]  # deprecated

    # Apply user supplied envs.
    ret.update(TEST_CONFIG["envs"])
    return ret


# All versions used to tested samples.
ALL_VERSIONS = ["2.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.13"]

# Any default versions that should be ignored.
IGNORED_VERSIONS = TEST_CONFIG["ignored_versions"]

TESTED_VERSIONS = sorted([v for v in ALL_VERSIONS if v not in IGNORED_VERSIONS])

INSTALL_LIBRARY_FROM_SOURCE = bool(os.environ.get("INSTALL_LIBRARY_FROM_SOURCE", False))

# Use the oldest tested Python version for linting (defaults to 3.10)
LINTING_VERSION = "3.10"
if len(TESTED_VERSIONS) > 0:
    LINTING_VERSION = TESTED_VERSIONS[0]

# Error if a python version is missing
nox.options.error_on_missing_interpreters = True

#
# Style Checks
#


def _determine_local_import_names(start_dir: str) -> list[str]:
    """Determines all import names that should be considered "local".

    This is used when running the linter to ensure that import order is
    properly checked.
    """
    file_ext_pairs = [os.path.splitext(path) for path in os.listdir(start_dir)]
    return [
        basename
        for basename, extension in file_ext_pairs
        if extension == ".py"
        or os.path.isdir(os.path.join(start_dir, basename))
        and basename not in ("__pycache__")
    ]


# Linting with flake8.
#
# We ignore the following rules:
#   ANN101: missing type annotation for `self` in method
#   ANN102: missing type annotation for `cls` in method
#   E203: whitespace before ‘:’
#   E266: too many leading ‘#’ for block comment
#   E501: line too long
#   I202: Additional newline in a section of imports
#
# We also need to specify the rules which are ignored by default:
# ['E226', 'W504', 'E126', 'E123', 'W503', 'E24', 'E704', 'E121']
#
# For more information see: https://pypi.org/project/flake8-annotations
FLAKE8_COMMON_ARGS = [
    "--show-source",
    "--builtin=gettext",
    "--max-complexity=20",
    "--import-order-style=google",
    "--exclude=.nox,.cache,env,lib,generated_pb2,*_pb2.py,*_pb2_grpc.py",
    "--ignore=ANN101,ANN102,E121,E123,E126,E203,E226,E24,E266,E501,E704,W503,W504,I202",
    "--max-line-length=88",
]


@nox.session(python=LINTING_VERSION)
def lint(session: nox.sessions.Session) -> None:
    if not TEST_CONFIG["enforce_type_hints"]:
        session.install("flake8", "flake8-import-order")
    else:
        session.install("flake8", "flake8-import-order", "flake8-annotations")

    local_names = _determine_local_import_names(".")
    args = FLAKE8_COMMON_ARGS + [
        "--application-import-names",
        ",".join(local_names),
        ".",
    ]
    session.run("flake8", *args)


#
# Black
#


@nox.session(python=LINTING_VERSION)
def blacken(session: nox.sessions.Session) -> None:
    session.install("black")
    python_files = [path for path in os.listdir(".") if path.endswith(".py")]

    session.run("black", *python_files)


#
# Sample Tests
#


PYTEST_COMMON_ARGS = ["--junitxml=sponge_log.xml"]


def _session_tests(
    session: nox.sessions.Session, post_install: Callable = None
) -> None:
    # check for presence of tests
    test_list = glob.glob("*_test.py") + glob.glob("test_*.py")
    test_list.extend(glob.glob("tests"))

    if len(test_list) == 0:
        print("No tests found, skipping directory.")
        return

    if TEST_CONFIG["pip_version_override"]:
        pip_version = TEST_CONFIG["pip_version_override"]
        session.install(f"pip=={pip_version}")
    else:
        session.install("--upgrade", "pip")

    """Runs py.test for a particular project."""
    concurrent_args = []
    if os.path.exists("requirements.txt"):
        with open("requirements.txt") as rfile:
            packages = rfile.read()
        if os.path.exists("constraints.txt"):
            session.install(
                "-r",
                "requirements.txt",
                "-c",
                "constraints.txt",
                "--only-binary",
                ":all",
            )
        elif "pyspark" in packages:
            session.install("-r", "requirements.txt", "--use-pep517")
        else:
            session.install("-r", "requirements.txt", "--only-binary", ":all")

    if os.path.exists("requirements-test.txt"):
        with open("requirements-test.txt") as rtfile:
            packages += rtfile.read()
        if os.path.exists("constraints-test.txt"):
            session.install(
                "-r",
                "requirements-test.txt",
                "-c",
                "constraints-test.txt",
                "--only-binary",
                ":all",
            )
        else:
            session.install("-r", "requirements-test.txt", "--only-binary", ":all")

    if INSTALL_LIBRARY_FROM_SOURCE:
        session.install("-e", _get_repo_root())

    if post_install:
        post_install(session)

    if "pytest-parallel" in packages:
        concurrent_args.extend(["--workers", "auto", "--tests-per-worker", "auto"])
    elif "pytest-xdist" in packages:
        concurrent_args.extend(["-n", "auto"])

    session.run(
        "pytest",
        *(PYTEST_COMMON_ARGS + session.posargs + concurrent_args),
        # Pytest will return 5 when no tests are collected. This can happen
        # on travis where slow and flaky tests are excluded.
        # See http://doc.pytest.org/en/latest/_modules/_pytest/main.html
        success_codes=[0, 5],
        env=get_pytest_env_vars(),
    )


@nox.session(python=ALL_VERSIONS)
def py(session: nox.sessions.Session) -> None:
    """Runs py.test for a sample using the specified version of Python."""
    if session.python in TESTED_VERSIONS:
        _session_tests(session)
    else:
        session.skip(
            "SKIPPED: {} tests are disabled for this sample.".format(session.python)
        )


#
# Readmegen
#


def _get_repo_root() -> str | None:
    """Returns the root folder of the project."""
    # Get root of this repository.
    # Assume we don't have directories nested deeper than 10 items.
    p = Path(os.getcwd())
    for i in range(10):
        if p is None:
            break
        if Path(p / ".git").exists():
            return str(p)
        p = p.parent
    raise Exception("Unable to detect repository root.")


GENERATED_READMES = sorted([x for x in Path(".").rglob("*.rst.in")])


@nox.session
@nox.parametrize("path", GENERATED_READMES)
def readmegen(session: nox.sessions.Session, path: str) -> None:
    """(Re-)generates the readme for a sample."""
    session.install("jinja2", "pyyaml")
    dir_ = os.path.dirname(path)

    if os.path.exists(os.path.join(dir_, "requirements.txt")):
        session.install("-r", os.path.join(dir_, "requirements.txt"))

    in_file = os.path.join(dir_, "README.rst.in")
    session.run(
        "python", _get_repo_root() + "/scripts/readme-gen/readme_gen.py", in_file
    )
