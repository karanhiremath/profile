{
  description = "hostctl personal attach sandbox: Nix flakes + Devbox. No Node by default.";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-linux" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in {
          default = pkgs.mkShell {
            packages = [
              pkgs.tmux
              pkgs.git
              pkgs.devbox
              pkgs.mise
              pkgs.rustc
              pkgs.cargo
              pkgs.go
              pkgs.python3
              pkgs.elixir
            ];
          };
        });
    };
}
