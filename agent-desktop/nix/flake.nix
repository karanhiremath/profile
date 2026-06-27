{
  description = "Agent desktop environments — disposable, multi-distro, nix-declarative";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };

          # Shared agent harness closure — held CONSTANT across every base OS so
          # the matrix validates the *process*, not incidental base differences.
          # Iteration 1: minimal (prove build -> load -> run).
          # Iteration 2: + xfce + chromium + novnc + claude/pi/codex + mise + config.
          agentHarness = [ pkgs.bashInteractive pkgs.coreutils ];

          # Parametrized image builder.
          #   base = null            -> pure nix userland (NixOS-like)        [it.1-2]
          #   base = <pulled distro> -> harness layered onto a real distro    [it.3]
          mkDesktopImage =
            { name, tag ? "dev", base ? null, extraContents ? [ ] }:
            pkgs.dockerTools.buildLayeredImage {
              inherit name tag;
              fromImage = base;
              contents = agentHarness ++ extraContents;
              config = {
                Cmd = [ "${pkgs.bashInteractive}/bin/bash" ];
                Env = [ "AGENT_DESKTOP_VARIANT=${name}" ];
              };
            };
        in
        {
          # Iteration 1 target: pipeline proof (pure nix, minimal).
          desktop-min = mkDesktopImage { name = "agent-desktop-min"; };

          # Distro matrix slots in here once the harness grows (iteration 3), e.g.:
          #   desktop-ubuntu = mkDesktopImage {
          #     name = "agent-desktop-ubuntu";
          #     base = pkgs.dockerTools.pullImage { imageName = "ubuntu"; imageDigest = "sha256:..."; sha256 = "..."; };
          #   };
          # plus fedora / rocky / arch / alpine / nixos. macOS is NOT here — it is a
          # darwinConfigurations.* output (native agent user), not an OCI image.
        });
    };
}
