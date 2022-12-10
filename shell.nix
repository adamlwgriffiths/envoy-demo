{ pkgs ? import <nixpkgs> {} }:

let
  # run this to determine the latest pypi revision and sha256
  latest-mach-nix-db = pkgs.writeShellScriptBin "latest-mach-nix-db" ''
    #!/usr/bin/env bash

    USER_SLASH_REPO="DavHau/pypi-deps-db"

    DATA=$(curl "https://api.github.com/repos/$USER_SLASH_REPO/commits/master" | jq '.sha, .commit.author.date' | sed 's/"//g')
    COMMIT=$(sed '1q;d' <<< "$DATA")
    DATE=$(sed '2q;d' <<< "$DATA")
    SHA256=$(nix-prefetch-url --unpack --type sha256 "https://github.com/$USER_SLASH_REPO/tarball/$COMMIT" | tail -n 1)

    echo ""
    echo "pypiDataRev = \"$COMMIT\"; # $DATE"
    echo "pypiDataSha256 = \"$SHA256\";"
  '';
  # https://github.com/DavHau/pypi-deps-db
  # commit: 2a2d29624d6d0531dc1064ac40f9a36561fcc7b7
  # Tue Aug 23 20:35:32 UTC 2022
  pypiDataRev="2a2d29624d6d0531dc1064ac40f9a36561fcc7b7";
  pypiDataSha256="0lzlj6pw1hhj5qhyqziw9qm6srib95bhzm7qr79xfc5srxgrszca";
  mach-nix = import (builtins.fetchGit {
    url = "https://github.com/DavHau/mach-nix";
    ref = "refs/tags/3.5.0";
  }) {
    inherit pypiDataRev pypiDataSha256;
  };
  pkgs =  mach-nix.nixpkgs;
  custom-python = mach-nix.mkPython {
    python = "python38Full";
    requirements = ''
      # utilities
      ipython
      fire
      toml
      memoization

      # testing
      nose

      # mach-nix fixes
      flit-core
    '';
    providers = {
      _default      = "nixpkgs,wheel,sdist";
      # fastapi doesnt work from nix
    };
    packagesExtra = [
    ];
  };
in pkgs.mkShell {
  buildInputs = with pkgs; [
    custom-python

    # mach-nix updater
    latest-mach-nix-db
    jq
  ];

  shellHook = ''
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONPATH="."
  '';
}
