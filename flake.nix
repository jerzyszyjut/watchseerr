{
  description = "Request the films and series on Letterboxd and Serializd watchlists in Seerr";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in
    {
      packages = forAll (pkgs: rec {
        watchseerr = pkgs.callPackage ./nix/package.nix { };
        default = watchseerr;
      });

      checks = forAll (pkgs: { package = self.packages.${pkgs.system}.default; });

      nixosModules.default = { pkgs, ... }: {
        imports = [ ./nix/module.nix ];
        services.watchseerr.package =
          nixpkgs.lib.mkDefault self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      };
    };
}
