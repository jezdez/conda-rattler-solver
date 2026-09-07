# Copyright (C) 2026 conda
# SPDX-License-Identifier: BSD-3-Clause
"""Compare Python updates against classic and libmamba using a fixed local channel.

The package records are synthetic and platform-specific. No package archives are
needed because each solver runs the normal CLI with ``--dry-run``. Every solver
receives the same installed records, history, pin file, and available packages.

Classic updates an unrequested conda package in these fixtures, while libmamba
keeps it installed when its dependencies can still be satisfied. These cases
record both reference results and require rattler to match libmamba.
"""

import json
import os

import pytest
from conda.base.context import context

from .utils import conda_subprocess

_CLASSIC_FLOATS_PYTHON = {
    "classic": "3.14.0",
    "libmamba": "3.13.1",
    "rattler": "3.13.1",
}


def _record(name, version, depends=(), build="0"):
    return {
        "name": name,
        "version": version,
        "build": build,
        "build_number": 0,
        "depends": list(depends),
        "subdir": context.subdir,
        "timestamp": 0,
        "size": 0,
    }


@pytest.mark.parametrize(
    "scenario,command,special,pin,expected_python",
    [
        pytest.param(
            "unrequested-conda",
            ("update", "python"),
            "conda",
            None,
            _CLASSIC_FLOATS_PYTHON,
            id="keep-minor-allow-patch",
        ),
        pytest.param(
            "explicit-python-pin",
            ("update", "python"),
            "conda",
            "python=3.14",
            "3.14.0",
            id="explicit-pin",
        ),
        pytest.param(
            "update-python-and-conda",
            ("update", "python", "conda"),
            "conda",
            None,
            "3.14.0",
            id="update-python-and-conda",
        ),
        pytest.param(
            "unversioned-python-dependency",
            ("update", "python"),
            "console_shortcut",
            None,
            "3.14.0",
            id="unversioned-python-dependency",
        ),
        pytest.param(
            "explicit-python-install",
            ("install", "python=3.14"),
            "conda",
            None,
            "3.14.0",
            id="explicit-python-install",
        ),
        pytest.param(
            "no-special-package",
            ("update", "python"),
            None,
            None,
            "3.14.0",
            id="no-special-package",
        ),
        pytest.param(
            "transitive-python-dependency",
            ("update", "python"),
            "transitive-conda",
            None,
            _CLASSIC_FLOATS_PYTHON,
            id="transitive-python-dependency",
        ),
        pytest.param(
            "update-transitive-conda",
            ("update", "python", "conda"),
            "transitive-conda",
            None,
            "3.14.0",
            id="update-transitive-conda",
        ),
        pytest.param(
            "update-other-python-dependent-package",
            ("update", "python", "python-consumer"),
            "conda",
            None,
            _CLASSIC_FLOATS_PYTHON,
            id="update-other-python-dependent-package",
        ),
        pytest.param(
            "pinned-consumer-releases-conda",
            ("update", "python", "python-consumer"),
            "conda",
            "python-consumer=2.0",
            "3.14.0",
            id="conflicting-request-releases-conda",
        ),
        pytest.param(
            "conda-not-in-history",
            ("update", "python"),
            "conda",
            "python=3.14",
            "3.14.0",
            id="conda-not-in-history",
        ),
        pytest.param(
            "pinned-special-package",
            ("update", "python"),
            "conda",
            "python=3.14\nconda",
            "3.14.0",
            id="pinned-special-package",
        ),
    ],
)
def test_python_updates_match_reference_solvers(
    tmp_path, scenario, command, special, pin, expected_python
):
    channel = tmp_path / "channel"
    prefix = tmp_path / "prefix"
    metadata = prefix / "conda-meta"
    metadata.mkdir(parents=True)

    available = [
        _record("python", version, build="h_fixture_0_cpython")
        for version in ("3.13.0", "3.13.1", "3.14.0")
    ]
    installed = [available[0]]
    if special == "conda":
        available.extend(
            [
                _record("conda", "1.0", ["python >=3.13,<3.14"], "py313_0"),
                _record("conda", "1.0", ["python >=3.14,<3.15"], "py314_0"),
                _record("conda", "2.0", ["python >=3.14,<3.15"], "py314_0"),
            ]
        )
        installed.append(available[3])
    elif special == "console_shortcut":
        available.append(_record("console_shortcut", "1.0", ["python"]))
        installed.append(available[3])
    elif special == "transitive-conda":
        available.extend(
            [
                _record("conda", "1.0", ["python-helper =1.0"]),
                _record("python-helper", "1.0", ["python >=3.13,<3.14"]),
                _record("conda", "2.0", ["python-helper =2.0"]),
                _record("python-helper", "2.0", ["python >=3.14,<3.15"]),
            ]
        )
        installed.extend(available[3:5])
    if "python-consumer" in command:
        available.extend(
            [
                _record("python-consumer", "1.0", ["python >=3.13"]),
                _record("python-consumer", "2.0", ["python >=3.14"]),
            ]
        )
        installed.append(available[-2])

    def filename(record):
        return f"{record['name']}-{record['version']}-{record['build']}.tar.bz2"

    for subdir in (context.subdir, "noarch"):
        directory = channel / subdir
        directory.mkdir(parents=True)
        packages = {filename(record): record for record in available}
        (directory / "repodata.json").write_text(
            json.dumps(
                {
                    "info": {"subdir": subdir},
                    "packages": packages if subdir == context.subdir else {},
                    "packages.conda": {},
                    "repodata_version": 1,
                }
            )
        )

    for record in installed:
        name = filename(record)
        (metadata / f"{name.removesuffix('.tar.bz2')}.json").write_text(
            json.dumps(
                {
                    **record,
                    "fn": name,
                    "channel": channel.as_uri(),
                    "url": f"{channel.as_uri()}/{context.subdir}/{name}",
                    "files": [],
                }
            )
        )
    specs = [record["name"] for record in installed if record["name"] != "python-helper"]
    specs[0] = "python=3.13"
    if scenario == "conda-not-in-history":
        specs.remove("conda")
    history = ["==> 2026-01-01 00:00:00 <==", "# cmd: conda create", f"# update specs: {specs!r}"]
    history.extend(
        f"+{channel.as_uri()}/{context.subdir}::{filename(record).removesuffix('.tar.bz2')}"
        for record in installed
    )
    (metadata / "history").write_text("\n".join(history) + "\n")
    if pin:
        (metadata / "pinned").write_text(pin + "\n")

    condarc = tmp_path / "condarc"
    condarc.write_text("{}\n")
    env = {
        key: value for key, value in os.environ.items() if not key.startswith(("CONDA_", "MAMBA_"))
    }
    env.update(
        {
            "CONDARC": str(condarc),
            "CONDA_SUBDIR": context.subdir,
            "CONDA_PKGS_DIRS": str(tmp_path / "pkgs"),
            "CONDA_ENVS_PATH": str(tmp_path / "envs"),
            "CONDA_AUTO_UPDATE_CONDA": "false",
            "CONDA_ADD_PIP_AS_PYTHON_DEPENDENCY": "false",
            "CONDA_SAT_SOLVER": "pycosat",
            "CONDA_AGGRESSIVE_UPDATE_PACKAGES": "",
            "CONDA_PINNED_PACKAGES": "",
            "CONDA_REPODATA_USE_ZST": "false",
            "CONDA_REPODATA_USE_SHARDS": "false",
            "CONDA_REPORT_ERRORS": "false",
            "CONDA_NUMBER_CHANNEL_NOTICES": "0",
            "CONDA_ALWAYS_YES": "true",
        }
    )
    original_metadata = {path.name: path.read_bytes() for path in metadata.iterdir()}
    results = {}
    for solver in ("classic", "libmamba", "rattler"):
        process = conda_subprocess(
            command[0],
            "--prefix",
            prefix,
            "--solver",
            solver,
            "--dry-run",
            "--json",
            "--offline",
            "--override-channels",
            "--channel",
            channel.as_uri(),
            "--repodata-fn",
            "repodata.json",
            *command[1:],
            env=env,
            check=False,
        )
        result = json.loads(process.stdout)
        if process.returncode:
            results[solver] = {"error": result.get("exception_name", "UnknownError")}
        else:
            final = {record["name"]: record["version"] for record in installed}
            actions = result.get("actions", {})
            for record in actions.get("UNLINK", []):
                final.pop(record["name"], None)
            final.update({record["name"]: record["version"] for record in actions.get("LINK", [])})
            results[solver] = final
        assert {path.name: path.read_bytes() for path in metadata.iterdir()} == original_metadata

    print(json.dumps({"scenario": scenario, "results": results}, sort_keys=True))
    for solver, result in results.items():
        expected = (
            expected_python[solver] if isinstance(expected_python, dict) else expected_python
        )
        assert result.get("python") == expected, (solver, results)
        assert {record["name"] for record in installed} <= result.keys(), (solver, results)
        if "conda" in command[1:]:
            assert result["conda"] == "2.0", (solver, results)
        if "python-consumer" in command[1:]:
            assert result["python-consumer"] == ("2.0" if expected == "3.14.0" else "1.0"), (
                solver,
                results,
            )
