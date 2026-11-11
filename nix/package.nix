{ lib, python3Packages }:

python3Packages.buildPythonApplication {
  pname = "watchseerr";
  version = (builtins.fromTOML (builtins.readFile ../pyproject.toml)).project.version or "0.1.0";
  pyproject = true;
  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [ ../pyproject.toml ../README.md ../watchseerr ../tests ];
  };
  build-system = [ python3Packages.setuptools ];
  # No dependencies beyond the standard library.
  nativeCheckInputs = [ python3Packages.pytestCheckHook ];
  pythonImportsCheck = [ "watchseerr" ];

  meta = {
    description = "Request the films and series on Letterboxd and Serializd watchlists in Seerr";
    homepage = "https://github.com/jerzyszyjut/watchseerr";
    license = lib.licenses.mit;
    mainProgram = "watchseerr";
  };
}
