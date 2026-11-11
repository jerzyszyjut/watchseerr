{ config, lib, pkgs, ... }:

let
  cfg = config.services.watchseerr;
  toml = pkgs.formats.toml { };
  configFile = toml.generate "watchseerr.toml" (lib.recursiveUpdate cfg.settings {
    seerr.url = cfg.seerrUrl;
  });
in
{
  options.services.watchseerr = {
    enable = lib.mkEnableOption "watchseerr, Letterboxd and Serializd watchlists to Seerr requests";

    package = lib.mkOption {
      type = lib.types.package;
      description = "The watchseerr package.";
    };

    seerrUrl = lib.mkOption {
      type = lib.types.str;
      default = "http://127.0.0.1:5055";
      description = "Where Seerr (or Jellyseerr/Overseerr) answers.";
    };

    apiKeyFile = lib.mkOption {
      type = lib.types.path;
      example = "/run/secrets/seerr-api-key";
      description = ''
        File holding a Seerr API key (Settings → General). Read through a
        systemd credential, so it never enters the Nix store and the service
        user needs no access to it.
      '';
    };

    interval = lib.mkOption {
      type = lib.types.str;
      default = "hourly";
      example = "*:0/30";
      description = "How often to sync, as a systemd OnCalendar expression.";
    };

    settings = lib.mkOption {
      type = toml.type;
      default = { };
      example = lib.literalExpression ''
        {
          max_requests_per_run = 25;
          sources = [
            { type = "letterboxd"; user = "alice"; seerr_user = "alice"; }
            { type = "serializd"; user = "alice"; seerr_user = "alice"; }
          ];
        }
      '';
      description = "watchseerr.toml as Nix; see the README for every key.";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.watchseerr = {
      description = "Request watchlisted films and series in Seerr";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      environment.WATCHSEERR_CONFIG = configFile;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = lib.getExe cfg.package;
        DynamicUser = true;
        StateDirectory = "watchseerr";
        LoadCredential = "seerr-api-key:${cfg.apiKeyFile}";
        # Nothing but outbound HTTP and its own state directory.
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        NoNewPrivileges = true;
        RestrictAddressFamilies = [ "AF_INET" "AF_INET6" "AF_UNIX" ];
        SystemCallFilter = [ "@system-service" ];
        CapabilityBoundingSet = "";
      };
    };

    systemd.timers.watchseerr = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = cfg.interval;
        Persistent = true;
        RandomizedDelaySec = "5m";
      };
    };
  };
}
