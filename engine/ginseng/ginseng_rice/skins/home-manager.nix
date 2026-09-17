# Example home-manager module for the Ginseng coords. Not evaluated by the package tests.
# Needs nixpkgs 25.05 or newer for the per-font nerd-fonts attributes.
# Put this file next to the generated skins/ghostty folder and import it from your home config.
{ pkgs, ... }:
{
  home.packages = [
    pkgs.nerd-fonts.jetbrains-mono   # use the "Nerd Font Mono" family so icons stay one cell wide
    pkgs.sarasa-gothic               # CJK monospace: 済 and 見込 land on exact two-cell widths
  ];
  fonts.fontconfig.enable = true;

  xdg.configFile."ghostty/themes/ginseng-seifuku".source = ./ghostty/ginseng-seifuku;
  xdg.configFile."ghostty/themes/ginseng-mori".source = ./ghostty/ginseng-mori;

  programs.ghostty = {
    enable = true;
    settings = {
      theme = "light:ginseng-seifuku,dark:ginseng-mori";
      font-family = "JetBrainsMono Nerd Font Mono";
      font-size = 12;
      window-padding-x = 10;
      window-padding-balance = true;
    };
  };
}
